import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
