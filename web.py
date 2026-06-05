"""Minimal HTTP server + SSE for the Art-Net Repeater dashboard."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import load

_STATIC = os.path.join(os.path.dirname(__file__), "static")


def make_handler(engine):
    """Return a handler class bound to the given Engine instance."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # silence access log

        # ---- routing -------------------------------------------------- #

        def do_GET(self):
            if self.path == "/":
                self._serve_file(os.path.join(_STATIC, "index.html"), "text/html")
            elif self.path == "/events":
                self._sse()
            elif self.path == "/config":
                body = engine.config_text.encode()
                self._respond(200, "text/plain; charset=utf-8", body)
            else:
                self._respond(404, "text/plain", b"Not found")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            if self.path == "/control":
                try:
                    action = json.loads(body).get("action", "")
                except Exception:
                    self._respond(400, "text/plain", b"Bad JSON")
                    return
                if action == "pause":
                    engine.pause()
                elif action == "resume":
                    engine.resume()
                else:
                    self._respond(400, "text/plain", b"Unknown action")
                    return
                self._respond(200, "text/plain", b"ok")

            elif self.path == "/config":
                text = body.decode("utf-8", errors="replace")
                # Validate before writing
                import tempfile, os as _os
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".toml", delete=False
                    ) as tf:
                        tf.write(text)
                        tmp = tf.name
                    load(tmp, {})          # raises ValueError on bad config
                    _os.replace(tmp, engine._config_path)
                    engine.reload()
                    self._respond(200, "text/plain", b"ok")
                except ValueError as e:
                    try:
                        _os.unlink(tmp)
                    except Exception:
                        pass
                    self._respond(400, "text/plain", str(e).encode())
                except Exception as e:
                    self._respond(500, "text/plain", str(e).encode())
            else:
                self._respond(404, "text/plain", b"Not found")

        # ---- SSE ------------------------------------------------------ #

        def _sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    payload = {
                        **engine.status,
                        "levels": engine.levels,
                    }
                    data = json.dumps(payload)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        # ---- helpers -------------------------------------------------- #

        def _serve_file(self, path: str, content_type: str):
            try:
                with open(path, "rb") as f:
                    body = f.read()
                self._respond(200, content_type, body)
            except FileNotFoundError:
                self._respond(404, "text/plain", b"Not found")

        def _respond(self, code: int, content_type: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def start(engine, port: int) -> ThreadingHTTPServer:
    """Start the web server in a daemon thread. Returns the server instance."""
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(engine))
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
