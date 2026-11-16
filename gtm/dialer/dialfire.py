"""Dialfire adapter.

Per the Dialfire support portal: contacts are created with
POST https://api.dialfire.com/api/campaigns/{campaign_id}/tasks/{task_name}/contacts/create
authenticated with a campaign token as `Authorization: Bearer <token>`.
`$phone` is the dial field. Other keys must match the campaign's form fields.
Not exercised against a live campaign in this repo.
"""
from __future__ import annotations

from gtm import http

BASE = "https://api.dialfire.com/api"


class DialfireDialer:
    def __init__(self, campaign_id: str, token: str):
        if not campaign_id or not token:
            raise ValueError("DIALFIRE_CAMPAIGN_ID and DIALFIRE_CAMPAIGN_TOKEN must be set")
        self.campaign_id = campaign_id
        self._h = {"Authorization": f"Bearer {token}"}

    def loaded_refs(self) -> set[str]:
        return set()  # idempotency for live runs comes from the run ledger

    def push(self, task_name: str, record: dict) -> None:
        payload = {"$phone": record["phone"], **{k: v for k, v in record.items() if k != "phone"}}
        http.request("POST", f"{BASE}/campaigns/{self.campaign_id}/tasks/{task_name}/contacts/create",
                     headers=self._h, body=payload)
