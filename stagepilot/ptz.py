"""BirdDog-compatible VISCA-over-IP command encoding and UDP transport."""

import ipaddress
import socket


_CAMERA_NETWORKS = tuple(ipaddress.ip_network(network) for network in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16'))
_PAN_TILT_DIRECTIONS = {
    'up_left': (0x01, 0x01),
    'up': (0x03, 0x01),
    'up_right': (0x02, 0x01),
    'left': (0x01, 0x03),
    'stop': (0x03, 0x03),
    'right': (0x02, 0x03),
    'down_left': (0x01, 0x02),
    'down': (0x03, 0x02),
    'down_right': (0x02, 0x02),
}
_VISCA_IP_HEADER = bytes((0x01, 0x00, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00))


def validate_camera_host(host):
    """Accept IPv4 addresses on private or link-local camera networks only."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('Camera address must be a private IPv4 address') from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(
            address in network for network in _CAMERA_NETWORKS):
        raise ValueError('Camera address must be a private IPv4 address')
    return str(address)


def _speed(value, minimum, maximum, name):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value


def encode_pan_tilt(direction, pan_speed=4, tilt_speed=4):
    """Return one VISCA-over-IP pan/tilt command packet."""
    if direction not in _PAN_TILT_DIRECTIONS:
        raise ValueError('Unsupported pan/tilt direction')
    pan_speed = _speed(pan_speed, 1, 24, 'Pan speed')
    tilt_speed = _speed(tilt_speed, 1, 24, 'Tilt speed')
    pan, tilt = _PAN_TILT_DIRECTIONS[direction]
    command = bytes((0x81, 0x01, 0x06, 0x01, pan_speed, tilt_speed, pan, tilt, 0xFF))
    return _VISCA_IP_HEADER + command


def encode_zoom(direction, speed=2):
    """Return one VISCA-over-IP zoom command packet."""
    if direction not in ('in', 'out', 'stop'):
        raise ValueError('Unsupported zoom direction')
    if direction == 'stop':
        command = bytes((0x81, 0x01, 0x04, 0x07, 0x00, 0xFF))
    else:
        speed = _speed(speed, 0, 7, 'Zoom speed')
        command = bytes((0x81, 0x01, 0x04, 0x07,
                         (0x20 if direction == 'in' else 0x30) + speed, 0xFF))
    header = bytes((0x01, 0x00, 0x00, len(command), 0x00, 0x00, 0x00, 0x00))
    return header + command


def send_packet(host, port, packet):
    """Send a single VISCA-over-IP packet via UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, (host, port))
