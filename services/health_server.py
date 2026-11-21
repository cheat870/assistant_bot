import os
import logging
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

HTML_PATH = Path(__file__).resolve().parent.parent / "templates" / "index.html"

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url_path = self.path.split("?")[0].rstrip("/")
        
        # Serve Telegram Mini App HTML dashboard
        if url_path in ["/app", "/webapp"] or (url_path == "" and "text/html" in self.headers.get("Accept", "")):
            if HTML_PATH.exists():
                try:
                    content = HTML_PATH.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    logger.warning(f"Error serving webapp html: {e}")
        
        # Default response for cloud health pings (Render, Koyeb, Railway)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "online", "service": "Telegram Assistant Bot", "uptime": "24/7"}')

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def log_message(self, format, *args):
        # Mute normal health ping logs to keep bot terminal logs clean
        pass

def start_health_server():
    """Start lightweight background HTTP health server for cloud platforms (Render, Koyeb, Railway)."""
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP server started on port {port} (Ready for 24/7 Cloud Hosting).")
        return server
    except Exception as e:
        logger.warning(f"Could not start health check server on port {port}: {e}")
        return None
