"""Account sources: where candidate companies come from.

JSON (fixtures, Clay exports) and CSV (Sales Navigator or any list export).
Signals may carry an absolute `date` or a relative `days_ago`, which keeps the
demo fixtures meaningful on any day you run them.
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from gtm import normalize
from gtm.models import Company, Signal


def _signal(s: dict, today: date) -> Signal:
    d = s.get("date") or (today - timedelta(days=int(s.get("days_ago", 0)))).isoformat()
    return Signal(s["type"], d, s.get("detail", ""))


def load(path: str | Path, today: date | None = None) -> list[Company]:
    today = today or date.today()
    path = Path(path)
    rows: list[dict]
    if path.suffix == ".csv":
        rows = []
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                sigs = []
                for part in filter(None, (r.get("signals") or "").split("|")):
                    bits = part.split(":", 2)  # type:YYYY-MM-DD:detail
                    sigs.append({"type": bits[0], "date": bits[1], "detail": bits[2] if len(bits) > 2 else ""})
                rows.append({**r, "signals": sigs})
    else:
        rows = json.loads(path.read_text())
    seen, out = set(), []
    for r in rows:
        d = normalize.domain(r.get("domain", ""))
        if not d or d in seen:
            continue
        seen.add(d)
        out.append(Company(d, r.get("name") or d, (r.get("industry") or "").lower(),
                           int(r.get("employees") or 0), (r.get("country") or "").upper(),
                           r.get("city") or "", [_signal(s, today) for s in r.get("signals", [])],
                           path.name))
    return out


def load_suppression(path: str | Path) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    return {l.strip().lower() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")}
