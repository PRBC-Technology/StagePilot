"""Local browser preview. This program cannot issue PTZ camera commands."""
import argparse
import json
import importlib.util
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import cv2

from .live_detector import PersonDetector

ROOT = Path(__file__).resolve().parent
MODEL = ROOT.parent / 'yolox.onnx'
TOKEN = secrets.token_urlsafe(32)
lock = threading.Lock()
state = {'status': 'idle', 'message': 'Ready to connect', 'frame': None, 'frame_id': 0,
         'fps_limit': 2.0, 'confidence': 0.75, 'backend': 'cpu', 'actual_fps': 0, 'inference_ms': 0, 'people': 0}
worker = None
stop_event = None


def set_state(**values):
    with lock:
        state.update(values)


def run_preview(url, cancel, backend='cpu'):
    capture = None
    try:
        set_state(status='connecting', message='Loading detector and opening video…')
        detector = PersonDetector(MODEL, backend)
        if cancel.is_set():
            return
        # Explicit open/read timeouts keep a disconnected stream from hanging indefinitely.
        options = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]
        capture = cv2.VideoCapture(str(url), cv2.CAP_FFMPEG, options)
        if not capture.isOpened():
            set_state(status='error', message='Could not open video. Check address, credentials and network access.')
            return
        label = 'DirectML requested' if backend == 'directml' else 'CPU'
        set_state(status='running', message=f'Detection active · {label} · no camera control')
        latest = {'frame': None, 'version': 0, 'ended': False}
        frame_lock = threading.Lock()

        def read_frames():
            while not cancel.is_set():
                ok, frame = capture.read()
                with frame_lock:
                    if not ok:
                        latest['ended'] = True
                        break
                    latest['frame'] = frame
                    latest['version'] += 1

        reader = threading.Thread(target=read_frames, daemon=True)
        reader.start()
        last_start = 0.0
        last_complete = 0.0
        last_version = 0
        while not cancel.is_set():
            with frame_lock:
                frame, version, ended = latest['frame'], latest['version'], latest['ended']
            if ended:
                set_state(status='error', message='Video ended or the stream was interrupted. Reconnect to try again.')
                break
            if frame is None or version == last_version:
                cancel.wait(.02)
                continue
            now = time.monotonic()
            with lock:
                interval = 1.0 / state['fps_limit']
                confidence = state['confidence']
            if now - last_start < interval:
                cancel.wait(min(.05, interval - (now - last_start)))
                continue
            last_version = version
            last_start = now
            view, count, inference = detector.detect(frame, confidence)
            now = time.monotonic()
            ok, jpeg = cv2.imencode('.jpg', view, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok and not cancel.is_set():
                with lock:
                    state.update(frame=jpeg.tobytes(), frame_id=state['frame_id'] + 1,
                                 people=count, inference_ms=round(inference * 1000),
                                 actual_fps=round(1 / (now - last_complete), 1) if last_complete else 0)
            last_complete = now
    except Exception:
        # OpenCV/network exceptions can contain credentials. Never return or log them.
        set_state(status='error', message='The preview failed. Check the model and stream, then try again.')
    finally:
        if capture is not None:
            cancel.set()
            if 'reader' in locals():
                reader.join(timeout=6)
            capture.release()
        if state['status'] == 'stopping':
            set_state(status='idle', message='Preview stopped', frame=None, actual_fps=0)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, code, data, mime='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, b'{}')
        if self.path == '/':
            html = (ROOT / 'live_ui.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            return self.reply(200, html.encode(), 'text/html; charset=utf-8')
        if self.path == '/app.js':
            return self.reply(200, (ROOT / 'live_ui.js').read_bytes(), 'text/javascript')
        if self.path == '/style.css':
            return self.reply(200, (ROOT / 'live_ui.css').read_bytes(), 'text/css')
        if self.headers.get('X-StagePilot-Token') != TOKEN:
            return self.reply(403, b'{}')
        with lock:
            if self.path == '/frame':
                frame = state['frame']
                return self.reply(200, frame, 'image/jpeg') if frame else self.reply(404, b'{}')
            if self.path == '/status':
                return self.reply(200, json.dumps({k: v for k, v in state.items() if k != 'frame'}).encode())
        self.reply(404, b'{}')

    def do_POST(self):
        global worker, stop_event
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if not self.allowed_host() or self.headers.get('Origin') != origin or self.headers.get('X-StagePilot-Token') != TOKEN:
            return self.reply(403, b'{}')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if self.path == '/stop':
                if stop_event:
                    stop_event.set()
                    set_state(status='stopping', message='Stopping preview…')
                return self.reply(200, b'{}')
            if self.path == '/fps':
                fps = float(body['fps'])
                if not 1 <= fps <= 30:
                    raise ValueError()
                set_state(fps_limit=fps)
                return self.reply(200, b'{}')
            if self.path == '/confidence':
                confidence = float(body['confidence'])
                if not 0.3 <= confidence <= 0.95:
                    raise ValueError()
                set_state(confidence=confidence)
                return self.reply(200, b'{}')
            if self.path != '/start' or (worker and worker.is_alive()):
                return self.reply(409, b'{"error":"Stop the existing preview first."}')
            url = body['url'].strip()
            parsed = urlsplit(url)
            if parsed.scheme.lower() not in ('rtsp', 'rtsps') or not parsed.hostname or len(url) > 2048:
                raise ValueError()
            fps = float(body['fps'])
            if not 1 <= fps <= 30 or not MODEL.is_file():
                raise ValueError()
            backend = body.get('backend', 'cpu')
            if backend not in ('cpu', 'directml'):
                raise ValueError()
            if backend == 'directml' and importlib.util.find_spec('onnxruntime') is None:
                return self.reply(400, b'{"error":"DirectML is not installed. See README for setup."}')
            set_state(frame=None, frame_id=0, fps_limit=fps, backend=backend, actual_fps=0, people=0, inference_ms=0)
            stop_event = threading.Event()
            worker = threading.Thread(target=run_preview, args=(url, stop_event, backend), daemon=True)
            worker.start()
            return self.reply(200, b'{}')
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self.reply(400, b'{"error":"Check the RTSP URL, frame rate and model file."}')


def main():
    parser = argparse.ArgumentParser(description='Run the StagePilot local preview')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    cv2.setLogLevel(0)
    if not MODEL.is_file():
        raise SystemExit('Missing yolox.onnx in the workspace root.')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('StagePilot preview:', url, flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if stop_event:
            stop_event.set()
        server.server_close()


if __name__ == '__main__':
    main()
