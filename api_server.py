"""HFT-Engine API server — thin HTTP router over the api.handlers package.

Serves the dashboard/ front end and dispatches JSON endpoints to
api.handlers (backtest, portfolio, strategies, orderflow, live).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from api import backtest, live, orderflow, portfolio, strategies

DASH = Path(__file__).parent / "dashboard"


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n))

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(200, {"ok": True, "engine": "hft-engine"})
        # static files
        rel = self.path.split("?")[0].lstrip("/")
        if not rel:
            rel = "index.html"
        target = (DASH / rel).resolve()
        if DASH not in target.parents and target != DASH:
            return self._json(404, {"error": "not found"})
        if not target.exists() or not target.is_file():
            return self._json(404, {"error": "not found"})
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            cfg = self._read_body()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return self._json(400, {"error": f"bad body: {exc}"})
        try:
            if self.path == "/api/backtest":
                return self._json(200, backtest(cfg))
            if self.path == "/api/portfolio":
                return self._json(200, portfolio(cfg))
            if self.path == "/api/strategies":
                return self._json(200, strategies(cfg))
            if self.path == "/api/orderflow":
                return self._json(200, orderflow(cfg))
            if self.path.startswith("/api/live"):
                return self._json(200, live(cfg))
            return self._json(404, {"error": f"unknown endpoint {self.path}"})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return self._json(500, {"error": str(exc)})

    def log_message(self, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"HFT-Engine API + dashboard on http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
