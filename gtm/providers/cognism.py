"""Cognism adapter (Search API plus Redeem API).

Flow per the Cognism help centre: search returns previews with a redeemId and
costs nothing, redeem returns the full record and consumes a credit.
Endpoint paths and auth follow the public docs. The filter field names in the
search body depend on your API entitlement, so confirm them in the Cognism
developer portal before a live run. Not exercised against a live account here.
"""
from __future__ import annotations

from gtm import http
from gtm.models import Company, Contact, Person

BASE = "https://app.cognism.com/api/search"


class CognismProvider:
    name = "cognism"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("COGNISM_API_KEY is not set")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.credits_used = 0

    def find_people(self, company: Company) -> list[Person]:
        res = http.request("POST", f"{BASE}/contact/search", headers=self._headers,
                           params={"indexSize": 20},
                           body={"account": {"domains": [company.domain]}})
        out = []
        for r in (res or {}).get("results", []):
            out.append(Person(r.get("firstName", ""), r.get("lastName", ""), r.get("jobTitle", ""),
                              company.domain, self.name, r.get("redeemId", "")))
        return out

    def reveal(self, person: Person, country: str = "") -> Contact | None:
        ref = person.ref if person.provider == self.name else ""
        if not ref:
            res = http.request("POST", f"{BASE}/contact/enrich", headers=self._headers, body={
                "firstName": person.first_name, "lastName": person.last_name,
                "account": {"domain": person.company_domain},
            })
            results = (res or {}).get("results", [])
            ref = results[0].get("redeemId", "") if results else ""
        if not ref:
            return None
        res = http.request("POST", f"{BASE}/contact/redeem", headers=self._headers,
                           body={"redeemIds": [ref]})
        results = (res or {}).get("results", [])
        if not results:
            return None
        self.credits_used += 1
        r = results[0]
        mobiles = r.get("mobilePhoneNumbers") or []
        directs = r.get("directPhoneNumbers") or []
        best = (mobiles or directs or [{}])[0]
        email = r.get("email") or {}
        return Contact(person.first_name, person.last_name, r.get("jobTitle") or person.title,
                       person.company_domain,
                       email=email.get("address", "") if isinstance(email, dict) else str(email),
                       phone=best.get("number", ""),
                       email_source=self.name, phone_source=self.name)
