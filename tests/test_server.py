import json
import threading
import urllib.error
import urllib.request

import pytest

from gtm import server


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("GTM_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GTM_SERVER_SECRET", "s3cret")
    monkeypatch.setenv("GTM_SERVER_QUIET", "1")
    for k in ("GTM_CRM", "GTM_PROVIDERS", "GTM_DIALER", "LANGDOCK_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    srv = server.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def call(base, method, path, body=None, secret="s3cret"):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-GTM-Secret": secret, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_auth(base):
    assert call(base, "GET", "/health", secret="")[0] == 200
    assert call(base, "GET", "/report", secret="wrong")[0] == 401


def test_end_to_end_over_http(base):
    status, run = call(base, "POST", "/prospect", {"push_dialer": True})
    assert status == 200 and run["contacts_created"] == 7 and run["credits_spent"] == 11

    _, again = call(base, "POST", "/prospect", {"push_dialer": True})
    assert again["contacts_created"] == 0 and again["credits_spent"] == 0

    _, found = call(base, "GET", "/lookup?q=hansa-fracht.example")
    cid = found["contacts"][0]["id"]

    status, res = call(base, "POST", "/call-outcome", {"crm_contact_id": cid, "outcome": "meeting_booked"})
    assert status == 200 and any("Prepare discovery call" in a for a in res["actions"])

    status, brief = call(base, "GET", f"/call-brief?contact_id={cid}")
    assert status == 200 and "Previous calls: meeting_booked" in brief["brief"]

    _, rep = call(base, "GET", "/report")
    assert rep["contacts_created"] == 7 and rep["dialer_loaded"] == 4


def test_bad_input_is_400_not_500(base):
    assert call(base, "POST", "/call-outcome", {"crm_contact_id": "x", "outcome": "maybe"})[0] == 400
    assert call(base, "GET", "/call-brief")[0] == 400
    assert call(base, "GET", "/nope")[0] == 404
