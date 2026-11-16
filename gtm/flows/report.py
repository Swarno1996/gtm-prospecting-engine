"""Flow 5: funnel report from the ledger."""
from __future__ import annotations

from collections import Counter

from gtm.ledger import Ledger


def run(ledger: Ledger) -> dict:
    rows = ledger.rows()
    companies = [r for r in rows if r.get("event") == "company"]
    outcomes = Counter(r["outcome"] for r in companies)
    contacts = [c for r in companies for c in r.get("contacts", [])]
    dropped = Counter(d["why"] for r in companies for d in r.get("dropped", []))
    return {"runs": len({r["run_id"] for r in companies}), "companies_processed": len(companies),
            "outcomes": dict(outcomes), "contacts_created": len(contacts),
            "phone_source": dict(Counter(c.get("phone_source", "") for c in contacts)),
            "contacts_dropped": dict(dropped),
            "dialer_loaded": sum(1 for r in rows if r.get("event") == "dialer_push")}
