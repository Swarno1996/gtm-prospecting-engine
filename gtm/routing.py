from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path


class Router:
    """Round robin SDR assignment per country, persisted between runs."""

    def __init__(self, cfg: dict, state: Path):
        self.sdrs = cfg["sdrs"]
        self.state = Path(state)
        self.pos = json.loads(self.state.read_text()) if self.state.exists() else {}

    def assign(self, country: str, persist: bool = True) -> dict:
        pool = [s for s in self.sdrs if country in s["countries"]] or self.sdrs
        i = self.pos.get(country, 0) % len(pool)
        if persist:
            self.pos[country] = i + 1
            self.state.write_text(json.dumps(self.pos))
        return pool[i]

    def name_for(self, owner_id: str) -> str:
        return next((s["name"] for s in self.sdrs if s["owner_id"] == owner_id), f"owner {owner_id}")


def due_date(business_days: int, now: datetime | None = None) -> str:
    d = (now or datetime.now(timezone.utc)).date()
    left = business_days
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return datetime.combine(d, time(8, 0), timezone.utc).isoformat().replace("+00:00", "Z")
