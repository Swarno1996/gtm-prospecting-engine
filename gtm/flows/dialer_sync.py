"""Flow 4: load callable contacts from earlier runs into the dialer, once."""
from __future__ import annotations

from gtm.ledger import Ledger


def run(ledger: Ledger, dialer, routing: dict, dry_run: bool = False) -> dict:
    already = ledger.dialer_pushed() | dialer.loaded_refs()
    pushed, skipped = [], 0
    for row in ledger.rows():
        if row.get("event") != "company" or row.get("tier") not in routing["dialer"]["tiers"]:
            continue
        for ct in row.get("contacts", []):
            if ct["crm_contact_id"] in already or not ct.get("phone"):
                skipped += 1
                continue
            if not dry_run:
                dialer.push(routing["dialer"]["campaign_task"], {
                    "phone": ct["phone"], "crm_contact_id": ct["crm_contact_id"], "name": ct["name"],
                    "company": row["name"], "tier": row["tier"], "owner_id": row.get("owner_id", "")})
                ledger.append({"event": "dialer_push", "run_id": row["run_id"],
                               "crm_contact_id": ct["crm_contact_id"], "domain": row["domain"]})
            already.add(ct["crm_contact_id"])
            pushed.append(ct["name"])
    return {"pushed": pushed, "skipped": skipped, "dry_run": dry_run}
