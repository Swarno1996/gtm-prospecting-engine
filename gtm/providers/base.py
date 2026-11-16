from __future__ import annotations

from typing import Protocol

from gtm.models import Company, Contact, Person


class DataProvider(Protocol):
    name: str
    credits_used: int

    def find_people(self, company: Company) -> list[Person]:
        """People at the company, preview only. Must not spend credits."""

    def reveal(self, person: Person, country: str = "") -> Contact | None:
        """Full contact data. Spends one credit when a record is returned."""
