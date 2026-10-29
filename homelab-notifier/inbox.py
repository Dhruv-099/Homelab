import html, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import alertdb

MAX_BODY = 1024 * 1024


def parse_json(raw: bytes):
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def format_watchtower(raw: bytes) -> str:
    data = parse_json(raw)
    if data is not None:
        report = data.get('report', data.get('message', data.get('body', 'Updates completed.')))
    else:
        report = raw.decode('utf-8', errors='replace') or 'Updates completed (empty payload).'
    return f"<b>Nightly Update Report</b>\n\n{html.escape(str(report))}"


def format_scrutiny(raw: bytes) -> str:
    # Scrutiny sends a shoutrrr "generic" webhook (template=json -> {title, message})
    data = parse_json(raw)
    if data is not None:
        title = data.get('title', 'Scrutiny')
        body = data.get('message', data.get('body', ''))
    else:
        title = 'Scrutiny'
        body = raw.decode('utf-8', errors='replace') or '(empty payload)'
    return f"<b>Drive Health Alert — {html.escape(str(title))}</b>\n\n{html.escape(str(body))}"


ROUTES = {
    "/watchtower": ("watchtower", format_watchtower),
    "/scrutiny": ("scrutiny", format_scrutiny),
}


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: bytes = b'{"status":"ok"}'):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            return self._reply(404, b'{"status":"not found"}')
        try:
            alertdb.init()
        except Exception as e:
            print(f"health check failed: {e}", flush=True)
            return self._reply(500, b'{"status":"db error"}')
        self._reply(200)

    def do_POST(self):
        route = ROUTES.get(self.path.split("?")[0])
        if route is None:
            return self._reply(404, b'{"status":"not found"}')
        source, fmt = route
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
            raw = self.rfile.read(length)
            # Reply 200 only after the row is committed, so a sender never believes an unsaved alert was kept
            alert_id = alertdb.enqueue(source, fmt(raw), raw.decode("utf-8", errors="replace"))
        except Exception as e:
            print(f"failed to store {source} alert: {e}", flush=True)
            return self._reply(500, b'{"status":"error"}')
        print(f"stored {source} alert #{alert_id} ({len(raw)} bytes)", flush=True)
        self._reply(200)


if __name__ == "__main__":
    alertdb.init()
    print("inbox listening on :8000", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
