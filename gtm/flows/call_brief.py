"""Flow 7: a one screen call brief for the SDR before dialing.

Facts come from the CRM and the run ledger: why the account was picked, who
the person is, what happened on earlier calls. The LLM only writes the
opener and the questions. With no LLM configured a template does it, so the
brief is always there and the facts in it are never generated.
"""
from __future__ import annotations

import json

from gtm import llm
from gtm.ledger import Ledger

SYSTEM = (
    "You write call prep for B2B SDRs. Use only the facts given. Do not invent "
    "numbers, names or events. Output exactly two sections: 'Opener' (two sentences, "
    "references the signal) and 'Questions' (three short discovery questions)."
)


def facts(crm, ledger: Ledger, contact_id: str) -> dict:
    contact = crm.get_contact(contact_id)
    if not contact:
        raise KeyError(f"contact {contact_id} not found")
    company = crm.get_company(contact.get("company_id", "")) or {}
    row = ledger.company_row(company.get("domain", "")) or {}
    return {
        "contact": {k: contact.get(k, "") for k in ("firstname", "lastname", "jobtitle", "phone")},
        "company": {k: company.get(k, "") for k in ("name", "domain", "lifecyclestage")},
        "tier": row.get("tier", ""), "score": row.get("score", ""),
        "why_now": row.get("top_signal") or "",
        "previous_calls": [{"attempt": c["attempt"], "outcome": c["outcome"], "at": c["at"]}
                           for c in ledger.calls(contact_id)],
    }


def template(f: dict) -> str:
    c, co = f["contact"], f["company"]
    reason = (f"I'm calling because of a recent change at {co['name']}: {f['why_now']}."
              if f["why_now"] else f"I'm calling because {co['name']} looks like the teams we work with.")
    return (f"Opener: Hi {c['firstname']}, this is <name>. {reason} "
            "That is often the moment sales leaders rethink how pipeline gets built.\n"
            "Questions:\n"
            "1. How is outbound pipeline generated today, and who owns it?\n"
            "2. What slows your reps down between finding an account and the first call?\n"
            "3. If that changed next quarter, how would you measure it?")


def run(crm, ledger: Ledger, contact_id: str) -> dict:
    f = facts(crm, ledger, contact_id)
    source = "template"
    text = template(f)
    if llm.enabled():
        try:
            text = llm.complete(SYSTEM, json.dumps(f, ensure_ascii=False))
            source = "langdock"
        except Exception as e:  # the brief must not fail because the model did
            source = f"template (langdock error: {type(e).__name__})"
    c, co = f["contact"], f["company"]
    header = (f"{c['firstname']} {c['lastname']}, {c['jobtitle']} at {co['name']}\n"
              f"Phone {c['phone'] or 'missing'} | tier {f['tier'] or '?'} | score {f['score'] or '?'}\n"
              f"Why now: {f['why_now'] or 'ICP fit, no live signal'}\n"
              f"Previous calls: {', '.join(p['outcome'] for p in f['previous_calls']) or 'none'}\n")
    return {"contact_id": contact_id, "facts": f, "brief": header + "\n" + text, "written_by": source}
