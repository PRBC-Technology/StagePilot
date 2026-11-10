import json
from http.server import ThreadingHTTPServer
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from stagepilot.ptz import encode_pan_tilt, encode_zoom, validate_camera_host


class PtzTests(unittest.TestCase):
    def test_pan_tilt_packet_uses_visca_ip_framing(self):
        packet = encode_pan_tilt('up', pan_speed=4, tilt_speed=5)
        self.assertEqual(packet, bytes.fromhex(
            '01 00 00 09 00 00 00 00 81 01 06 01 04 05 03 01 FF'))

    def test_zoom_packet_sets_payload_length(self):
        self.assertEqual(encode_zoom('in', 2), bytes.fromhex(
            '01 00 00 06 00 00 00 00 81 01 04 07 22 FF'))
        self.assertEqual(encode_zoom('stop'), bytes.fromhex(
            '01 00 00 06 00 00 00 00 81 01 04 07 00 FF'))

    def test_camera_host_must_be_private_ipv4(self):
        self.assertEqual(validate_camera_host('192.168.10.190'), '192.168.10.190')
        for host in ('localhost', '8.8.8.8', '127.0.0.1', '::1'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_camera_host(host)

    def test_commands_reject_unknown_directions_and_out_of_range_speed(self):
        for operation in (lambda: encode_pan_tilt('forward'),
                          lambda: encode_pan_tilt('left', 25, 4),
                          lambda: encode_zoom('in', 8),
                          lambda: encode_zoom('sideways')):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                operation()


class PtzEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from stagepilot.live import Handler, TOKEN

        cls.token = TOKEN
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, body):
        port = self.server.server_port
        request = Request(
            f'http://127.0.0.1:{port}/ptz',
            data=json.dumps(body).encode(),
            headers={
                'Content-Type': 'application/json',
                'Origin': f'http://127.0.0.1:{port}',
                'X-StagePilot-Token': self.token,
            },
            method='POST',
        )
        try:
            with urlopen(request) as response:
                return response.status
        except HTTPError as error:
            return error.code

    def test_endpoint_sends_validated_camera_command(self):
        body = {
            'host': '192.168.10.190',
            'port': 52381,
            'action': 'pan_tilt',
            'direction': 'right',
            'speed': 4,
        }
        with patch('stagepilot.live.send_packet') as send:
            self.assertEqual(self.post(body), 200)
        send.assert_called_once_with('192.168.10.190', 52381, encode_pan_tilt('right', 4, 4))

    def test_endpoint_rejects_non_private_camera_address(self):
        body = {'host': '8.8.8.8', 'port': 52381, 'action': 'stop_all'}
        with patch('stagepilot.live.send_packet') as send:
            self.assertEqual(self.post(body), 400)
        send.assert_not_called()

    def test_endpoint_accepts_pan_tilt_stop_without_speed(self):
        body = {
            'host': '192.168.10.190',
            'port': 52381,
            'action': 'pan_tilt',
            'direction': 'stop',
        }
        with patch('stagepilot.live.send_packet') as send:
            self.assertEqual(self.post(body), 200)
        send.assert_called_once_with('192.168.10.190', 52381, encode_pan_tilt('stop', 12, 12))

    def test_stop_all_sends_pan_tilt_and_zoom_stops(self):
        body = {'host': '192.168.10.190', 'port': 52381, 'action': 'stop_all'}
        with patch('stagepilot.live.send_packet') as send:
            self.assertEqual(self.post(body), 200)
        self.assertEqual(send.call_count, 2)
        send.assert_any_call('192.168.10.190', 52381, encode_pan_tilt('stop'))
        send.assert_any_call('192.168.10.190', 52381, encode_zoom('stop'))


if __name__ == '__main__':
    unittest.main()
