import re
import os
import logging
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

HTML_PATH = Path(__file__).resolve().parent.parent / "templates" / "index.html"
SITES_DIR = Path(__file__).resolve().parent.parent / "data" / "sites"
SITES_DIR.mkdir(parents=True, exist_ok=True)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url_path = self.path.split("?")[0].rstrip("/")

        # 1. Serve dynamic user landing pages: /site/<site_id> or /p/<site_id>
        if url_path.startswith("/site/") or url_path.startswith("/p/"):
            site_id = url_path.split("/")[-1].strip()
            site_id = re.sub(r'[^a-zA-Z0-9_-]', '', site_id)
            site_file = SITES_DIR / f"{site_id}.html"
            if site_file.exists():
                try:
                    content = site_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    logger.warning(f"Error serving user landing page {site_id}: {e}")
            else:
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h1>404 - រកមិនឃើញគេហទំព័រនេះទេ (Website Not Found)</h1>".encode("utf-8"))
                return
        
        # 2. Serve Telegram Mini App HTML dashboard
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
