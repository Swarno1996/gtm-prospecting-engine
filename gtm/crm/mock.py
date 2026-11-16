"""JSON file CRM with the same surface as the HubSpot adapter."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from gtm import normalize


class MockCRM:
    def __init__(self, path: Path, seed: Path):
        self.path = Path(path)
        if not self.path.exists():
            shutil.copy(seed, self.path)
        self.db = json.loads(self.path.read_text())

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.db, indent=2))

    def _next_id(self, kind: str) -> str:
        self.db["seq"] = self.db.get("seq", 9000) + 1
        return f"{kind}-{self.db['seq']}"

    def find_company(self, domain: str, name: str = "") -> dict | None:
        d = normalize.domain(domain)
        for c in self.db["companies"]:
            if d and normalize.domain(c.get("domain", "")) == d:
                return c
        n = normalize.company_name(name)
        if n:
            for c in self.db["companies"]:
                if normalize.company_name(c.get("name", "")) == n:
                    return c
        return None

    def company_contacts(self, company_id: str) -> list[dict]:
        return [c for c in self.db["contacts"] if c.get("company_id") == company_id]

    def find_contact_by_email(self, email: str) -> dict | None:
        e = (email or "").lower()
        return next((c for c in self.db["contacts"] if e and c.get("email", "").lower() == e), None)

    def create_company(self, props: dict) -> dict:
        rec = {"id": self._next_id("co"), "lifecyclestage": "lead", "open_deals": 0, **props}
        self.db["companies"].append(rec)
        self._save()
        return rec

    def create_contact(self, props: dict, company_id: str) -> dict:
        rec = {"id": self._next_id("ct"), "company_id": company_id, **props}
        self.db["contacts"].append(rec)
        self._save()
        return rec

    def create_task(self, props: dict, contact_id: str, company_id: str) -> dict:
        rec = {"id": self._next_id("task"), "contact_id": contact_id, "company_id": company_id,
               "status": "NOT_STARTED", **props}
        self.db["tasks"].append(rec)
        self._save()
        return rec

    def open_tasks(self, company_id: str) -> list[dict]:
        return [t for t in self.db["tasks"]
                if t.get("company_id") == company_id and t.get("status") != "COMPLETED"]
