"""Waterfall enrichment: ask providers in order, keep the first valid email and
the first valid phone, stop as soon as the contact is callable."""
from __future__ import annotations

from gtm import normalize
from gtm.models import Contact, Person


class Budget:
    def __init__(self, max_credits: int | None):
        self.max = max_credits
        self.spent = 0

    def allows(self, needed: int = 1) -> bool:
        return self.max is None or self.max - self.spent >= needed


def reveal(person: Person, providers: list, country: str, budget: Budget,
           stats: dict | None = None) -> Contact | None:
    stats = stats if stats is not None else {}
    merged: Contact | None = None
    for prov in providers:
        if not budget.allows():
            break
        before = prov.credits_used
        got = prov.reveal(person, country)
        spent = prov.credits_used - before
        budget.spent += spent
        s = stats.setdefault(prov.name, {"reveals": 0, "valid_phone": 0, "bad_phone": 0, "no_phone": 0})
        if not got:
            continue
        s["reveals"] += 1
        e164, kind = normalize.phone(got.phone, country)
        if e164:
            s["valid_phone"] += 1
        elif got.phone:
            s["bad_phone"] += 1
        else:
            s["no_phone"] += 1
        if merged is None:
            merged = Contact(got.first_name, got.last_name, got.title, got.company_domain)
        if not merged.email and normalize.email_ok(got.email):
            merged.email, merged.email_source = got.email.lower(), prov.name
        if not merged.phone and e164:
            merged.phone, merged.phone_type, merged.phone_source = e164, kind, prov.name
        if merged.email and merged.phone:
            break
    return merged
