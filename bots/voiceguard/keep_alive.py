from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
import logging

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"24/7 Discord Voice Bot is alive and running!")

    def do_HEAD(self):
        # UptimeRobot mac dinh dung phuong thuc HEAD de ping
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Tat log HTTP ra console de tranh spam terminal
        return

def run_server(port: int = 8080):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print(f"[KeepAlive] Web server dang chay tai cong {port}")
    httpd.serve_forever()

def start_keep_alive():
    if os.getenv("DISABLE_KEEP_ALIVE") or os.getenv("ORCHESTRATOR"):
        logging.info("[KeepAlive] Web server noi bo da duoc tat (Multi-Bot Orchestrator dang quan ly port cong).")
        return
    port = int(os.environ.get("PORT", 8080))
    t = threading.Thread(target=run_server, args=(port,), daemon=True)
    t.start()
