"""Clay handoff.

Clay has no public table API. The supported pattern is: POST JSON rows to a
table's webhook source, let Clay run its enrichment columns, and have an HTTP
API column POST the enriched row back to you (or export the table). This
module covers both directions as plain data: push rows out, read rows back.
"""
from __future__ import annotations

import json
from pathlib import Path

from gtm import http
from gtm.models import Company, Signal


def push_rows(webhook_url: str, rows: list[dict]) -> int:
    if not webhook_url.startswith("https://"):
        raise ValueError("CLAY_WEBHOOK_URL must be an https URL")
    for row in rows:
        http.request("POST", webhook_url, body=row)
    return len(rows)


def read_export(path: str | Path) -> list[Company]:
    """Read enriched rows (JSON list) exported or called back from a Clay table."""
    out = []
    for r in json.loads(Path(path).read_text()):
        signals = [Signal(s["type"], s["date"], s.get("detail", "")) for s in r.get("signals", [])]
        out.append(Company(r["domain"], r.get("name", r["domain"]), r.get("industry", ""),
                           int(r.get("employees") or 0), r.get("country", ""), r.get("city", ""),
                           signals, "clay"))
    return out
