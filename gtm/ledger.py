"""Append only run ledger. It is the pipeline's memory: it makes reruns
idempotent and it is the single source for the funnel report."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def append(self, row: dict) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def recent_domains(self, cooldown_days: int) -> set[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
        return {r["domain"] for r in self.rows()
                if r.get("event") == "company" and datetime.fromisoformat(r["ts"]) >= cutoff}

    def dialer_pushed(self) -> set[str]:
        return {r["crm_contact_id"] for r in self.rows() if r.get("event") == "dialer_push"}

    def calls(self, crm_contact_id: str) -> list[dict]:
        return [r for r in self.rows()
                if r.get("event") == "call" and r.get("crm_contact_id") == crm_contact_id]

    def company_row(self, domain: str) -> dict | None:
        rows = [r for r in self.rows() if r.get("event") == "company" and r.get("domain") == domain]
        return rows[-1] if rows else None
