"""Small JSON HTTP client on the standard library with retry and backoff."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url}: {body[:300]}")
        self.status = status
        self.body = body


def request(method: str, url: str, *, headers: dict | None = None, params: dict | None = None,
            body: dict | list | None = None, timeout: int = 20, retries: int = 3):
    if params:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})}"
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode() or "null"
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            retryable = e.code == 429 or 500 <= e.code < 600
            if not retryable or attempt == retries:
                raise HttpError(e.code, text, url) from None
            wait = float(e.headers.get("Retry-After") or 2 ** attempt)
            time.sleep(min(wait, 30))
        except urllib.error.URLError:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
