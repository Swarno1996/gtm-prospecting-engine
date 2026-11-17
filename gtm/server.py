"""HTTP entry point for n8n and Langdock.

Both tools call this with their HTTP Request node. Standard library only.

    GET  /health
    GET  /report
    GET  /lookup?q=<domain or name>
    POST /prospect       {"source": "...", "max_credits": 20, "dry_run": false, "push_dialer": true}
    POST /dialer-sync    {"dry_run": false}
    POST /call-outcome   {"crm_contact_id": "...", "outcome": "no_answer", "call_id": "...", ...}
    GET  /call-brief?contact_id=<id>

Set GTM_SERVER_SECRET and send it as the X-GTM-Secret header. Without it the
server only listens on 127.0.0.1.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from gtm import service, settings
from gtm.flows.call_outcome import OutcomeError

# One flow at a time: the mock CRM and the ledger are files, and a prospecting
# run must never overlap another one.
_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "gtm-engine/0.2"

    def log_message(self, fmt, *args):  # quieter default logging
        if os.environ.get("GTM_SERVER_QUIET") != "1":
            super().log_message(fmt, *args)

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        secret = settings.env("GTM_SERVER_SECRET")
        return not secret or hmac.compare_digest(self.headers.get("X-GTM-Secret", ""), secret)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        data = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    def _route(self, method: str) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/health":
            return self._send(200, {"ok": True})
        if not self._authorized():
            return self._send(401, {"error": "missing or wrong X-GTM-Secret"})
        try:
            with _LOCK:
                if method == "GET" and url.path == "/report":
                    return self._send(200, service.funnel())
                if method == "GET" and url.path == "/lookup":
                    if not q.get("q"):
                        return self._send(400, {"error": "q is required"})
                    return self._send(200, service.lookup(q["q"]))
                if method == "GET" and url.path == "/call-brief":
                    if not q.get("contact_id"):
                        return self._send(400, {"error": "contact_id is required"})
                    return self._send(200, service.brief(q["contact_id"]))
                if method == "POST" and url.path == "/prospect":
                    b = self._body()
                    res = service.prospect_run(source=b.get("source"), max_credits=b.get("max_credits"),
                                               dry_run=bool(b.get("dry_run")),
                                               push_dialer=bool(b.get("push_dialer")))
                    return self._send(200, _summary(res))
                if method == "POST" and url.path == "/dialer-sync":
                    return self._send(200, service.dialer(bool(self._body().get("dry_run"))))
                if method == "POST" and url.path == "/call-outcome":
                    return self._send(200, service.outcome(self._body()))
        except (OutcomeError, KeyError, ValueError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # report, do not crash the server
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": f"no route {method} {url.path}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def _summary(res: dict) -> dict:
    """Flatten a prospecting run into fields an n8n IF node or a Langdock agent can read."""
    created = [c for r in res["results"] for c in r.get("contacts", [])]
    counts: dict[str, int] = {}
    for r in res["results"]:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    return {"run_id": res["run_id"], "dry_run": res["dry_run"], "sourced": res["sourced"],
            "contacts_created": len(created), "credits_spent": res["credits_spent"],
            "outcomes": counts, "provider_stats": res["provider_stats"],
            "contacts": created, "results": res["results"]}


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str | None = None, port: int = 8787) -> None:
    host = host or ("0.0.0.0" if settings.env("GTM_SERVER_SECRET") else "127.0.0.1")
    srv = make_server(host, port)
    print(f"gtm engine listening on http://{host}:{port}")
    srv.serve_forever()
