"""HubSpot adapter on the CRM v3 object and search APIs.

Needs a private app token with scopes for companies, contacts and tasks
(crm.objects.companies.read/write, crm.objects.contacts.read/write).
Association type ids are HubSpot defined: contact to company 279,
task to contact 204, task to company 192.
"""
from __future__ import annotations

import os

from gtm import http, normalize

BASE = "https://api.hubapi.com/crm/v3/objects"
COMPANY_PROPS = ["name", "domain", "hubspot_owner_id", "lifecyclestage", "hs_num_open_deals"]
CONTACT_PROPS = ["email", "firstname", "lastname", "jobtitle", "phone", "mobilephone"]


def _assoc(to_id: str, type_id: int) -> dict:
    return {"to": {"id": to_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}]}


class HubSpotCRM:
    def __init__(self, token: str):
        if not token:
            raise ValueError("HUBSPOT_TOKEN is not set")
        self._h = {"Authorization": f"Bearer {token}"}

    def _search(self, obj: str, filters: list[dict], props: list[str], limit: int = 10) -> list[dict]:
        res = http.request("POST", f"{BASE}/{obj}/search", headers=self._h, body={
            "filterGroups": [{"filters": filters}], "properties": props, "limit": limit})
        return (res or {}).get("results", [])

    @staticmethod
    def _company(r: dict) -> dict:
        p = r.get("properties", {})
        return {"id": r["id"], "name": p.get("name") or "", "domain": p.get("domain") or "",
                "owner_id": p.get("hubspot_owner_id") or "",
                "lifecyclestage": p.get("lifecyclestage") or "",
                "open_deals": int(float(p.get("hs_num_open_deals") or 0))}

    @staticmethod
    def _contact(r: dict, company_id: str = "") -> dict:
        p = r.get("properties", {})
        return {"id": r["id"], "email": p.get("email") or "", "firstname": p.get("firstname") or "",
                "lastname": p.get("lastname") or "", "jobtitle": p.get("jobtitle") or "",
                "phone": p.get("mobilephone") or p.get("phone") or "", "company_id": company_id}

    def find_company(self, domain: str, name: str = "") -> dict | None:
        d = normalize.domain(domain)
        if d:
            hits = self._search("companies", [{"propertyName": "domain", "operator": "EQ", "value": d}],
                                COMPANY_PROPS, 1)
            if hits:
                return self._company(hits[0])
        if name:
            hits = self._search("companies", [{"propertyName": "name", "operator": "CONTAINS_TOKEN",
                                               "value": normalize.company_name(name)}], COMPANY_PROPS, 5)
            want = normalize.company_name(name)
            for h in hits:
                if normalize.company_name(h.get("properties", {}).get("name", "")) == want:
                    return self._company(h)
        return None

    def company_contacts(self, company_id: str) -> list[dict]:
        hits = self._search("contacts", [{"propertyName": "associations.company", "operator": "EQ",
                                          "value": company_id}], CONTACT_PROPS, 100)
        return [self._contact(h, company_id) for h in hits]

    def find_contact_by_email(self, email: str) -> dict | None:
        hits = self._search("contacts", [{"propertyName": "email", "operator": "EQ",
                                          "value": email.lower()}], CONTACT_PROPS, 1)
        return self._contact(hits[0]) if hits else None

    def create_company(self, props: dict) -> dict:
        body = {"name": props["name"], "domain": props["domain"],
                "hubspot_owner_id": props.get("owner_id", "")}
        body = {k: v for k, v in body.items() if v}
        for k in ("numberofemployees", "country", "city"):
            if props.get(k):
                body[k] = props[k]
        if os.environ.get("HUBSPOT_ICP_PROPS") == "1":
            # Needs custom company properties icp_tier, icp_score, top_signal in the portal.
            for k in ("icp_tier", "icp_score", "top_signal"):
                if props.get(k) not in (None, ""):
                    body[k] = props[k]
        r = http.request("POST", f"{BASE}/companies", headers=self._h, body={"properties": body})
        return {"id": r["id"], "lifecyclestage": "lead", "open_deals": 0, **props}

    def create_contact(self, props: dict, company_id: str) -> dict:
        body = {"email": props.get("email", ""), "firstname": props["firstname"],
                "lastname": props["lastname"], "jobtitle": props.get("jobtitle", ""),
                "hubspot_owner_id": props.get("owner_id", "")}
        key = "mobilephone" if props.get("phone_type") == "mobile" else "phone"
        body[key] = props.get("phone", "")
        r = http.request("POST", f"{BASE}/contacts", headers=self._h, body={
            "properties": {k: v for k, v in body.items() if v},
            "associations": [_assoc(company_id, 279)]})
        return {"id": r["id"], "company_id": company_id, **props}

    def create_task(self, props: dict, contact_id: str, company_id: str) -> dict:
        r = http.request("POST", f"{BASE}/tasks", headers=self._h, body={
            "properties": {"hs_timestamp": props["due"], "hs_task_subject": props["subject"],
                           "hs_task_body": props["body"], "hubspot_owner_id": props.get("owner_id", ""),
                           "hs_task_status": "NOT_STARTED", "hs_task_type": "CALL",
                           "hs_task_priority": props.get("priority", "MEDIUM")},
            "associations": [_assoc(contact_id, 204), _assoc(company_id, 192)]})
        return {"id": r["id"], **props}

    def open_tasks(self, company_id: str) -> list[dict]:
        hits = self._search("tasks", [
            {"propertyName": "associations.company", "operator": "EQ", "value": company_id},
            {"propertyName": "hs_task_status", "operator": "NEQ", "value": "COMPLETED"},
        ], ["hs_task_subject", "hs_timestamp", "hubspot_owner_id"], 50)
        return [{"id": h["id"], "subject": h["properties"].get("hs_task_subject", ""),
                 "due": h["properties"].get("hs_timestamp", ""),
                 "owner_id": h["properties"].get("hubspot_owner_id", "")} for h in hits]
