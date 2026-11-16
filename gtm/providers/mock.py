"""Fixture backed provider. Each mock provider has its own coverage and its own
bad data, so the waterfall and the phone check have something real to do."""
from __future__ import annotations

import json
from pathlib import Path

from gtm.models import Company, Contact, Person


class MockProvider:
    def __init__(self, name: str, fixtures: Path):
        self.name = name
        self.credits_used = 0
        self._people = json.loads(Path(fixtures).read_text())

    def find_people(self, company: Company) -> list[Person]:
        return [
            Person(p["first_name"], p["last_name"], p["title"], p["domain"], self.name, p["id"])
            for p in self._people
            if p["domain"] == company.domain and self.name in p["providers"]
        ]

    def reveal(self, person: Person, country: str = "") -> Contact | None:
        for p in self._people:
            if (p["domain"], p["first_name"].lower(), p["last_name"].lower()) == person.key:
                data = p["providers"].get(self.name)
                if not data:
                    return None
                self.credits_used += 1
                return Contact(p["first_name"], p["last_name"], p["title"], p["domain"],
                               email=data.get("email", ""), phone=data.get("phone", ""),
                               email_source=self.name, phone_source=self.name)
        return None
