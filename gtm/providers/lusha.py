"""Lusha adapter (Person API v2).

Written against the public docs at docs.lusha.com: GET /v2/person with the key
in the `api_key` header, lookup by firstName + lastName + companyDomain.
Not exercised against a live account in this repo. Response parsing is
defensive because returned fields depend on plan.
"""
from __future__ import annotations

from gtm import http
from gtm.models import Company, Contact, Person

BASE = "https://api.lusha.com"


class LushaProvider:
    name = "lusha"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("LUSHA_API_KEY is not set")
        self._headers = {"api_key": api_key}
        self.credits_used = 0

    def find_people(self, company: Company) -> list[Person]:
        # Person API v2 enriches known people. List discovery comes from the
        # first provider in the waterfall or from an imported account list.
        return []

    def reveal(self, person: Person, country: str = "") -> Contact | None:
        try:
            res = http.request("GET", f"{BASE}/v2/person", headers=self._headers, params={
                "firstName": person.first_name, "lastName": person.last_name,
                "companyDomain": person.company_domain,
            })
        except http.HttpError as e:
            if e.status == 404:
                return None
            raise
        data = (res or {}).get("contact", {}).get("data") or (res or {}).get("data") or {}
        if not data:
            return None
        self.credits_used += 1
        emails = data.get("emailAddresses") or []
        phones = data.get("phoneNumbers") or []
        mobile = next((p for p in phones if p.get("phoneType") == "mobile"), None)
        best = mobile or (phones[0] if phones else {})
        return Contact(person.first_name, person.last_name, data.get("jobTitle") or person.title,
                       person.company_domain,
                       email=(emails[0].get("email", "") if emails else ""),
                       phone=best.get("number", "") or best.get("internationalNumber", ""),
                       email_source=self.name, phone_source=self.name)
