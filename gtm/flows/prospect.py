"""Flow 3: the full prospecting run.

source -> ICP and signal score -> cooldown -> suppression -> CRM dedupe ->
people preview (free) -> name dedupe -> waterfall reveal (credits) ->
email dedupe -> create company, contacts, SDR call tasks -> optional dialer load.

Order matters: every check that can stop a company runs before the first
credit is spent on it.
"""
from __future__ import annotations

import uuid
from datetime import date

from gtm import icp as icp_mod
from gtm.ledger import Ledger
from gtm.models import Company
from gtm.providers import waterfall
from gtm.routing import Router, due_date

BLOCKED_STAGES = {"customer", "opportunity", "evangelist"}


def run(companies: list[Company], *, icp: dict, routing: dict, crm, providers: list, dialer,
        ledger: Ledger, router: Router, suppression: set[str], max_credits: int | None = None,
        dry_run: bool = False, push_dialer: bool = False, today: date | None = None) -> dict:
    run_id = uuid.uuid4().hex[:8]
    budget = waterfall.Budget(max_credits)
    stats: dict = {}
    results: list[dict] = []
    cooled = ledger.recent_domains(routing["cooldown_days"])
    scored = icp_mod.rank(companies, icp, today)
    filtered_out = len(companies) - len(scored)

    def done(s, outcome: str, **extra) -> None:
        row = {"event": "company", "run_id": run_id, "domain": s.company.domain,
               "name": s.company.name, "tier": s.tier, "score": s.total, "outcome": outcome, **extra}
        results.append(row)
        # Only finished decisions enter the ledger. A company stopped by the
        # credit budget is retried on the next run.
        if not dry_run and outcome not in ("skipped_cooldown", "budget_exhausted"):
            ledger.append(row)

    for s in scored:
        c = s.company
        if s.tier not in routing["prospect_tiers"]:
            results.append({"event": "company", "domain": c.domain, "name": c.name, "tier": s.tier,
                            "score": s.total, "outcome": "below_tier"})
            continue
        if c.domain in cooled:
            done(s, "skipped_cooldown")
            continue
        if c.domain in suppression:
            done(s, "skipped_suppressed")
            continue

        existing = crm.find_company(c.domain, c.name)
        if existing and (existing.get("lifecyclestage") in BLOCKED_STAGES or existing.get("open_deals", 0) > 0):
            done(s, "skipped_customer_or_open_deal", company_id=existing["id"])
            continue

        known = crm.company_contacts(existing["id"]) if existing else []
        known_names = {(k.get("firstname", "").lower(), k.get("lastname", "").lower()) for k in known}

        people = []
        for prov in providers:
            people = prov.find_people(c)
            if people:
                break
        targets = [p for p in icp_mod.pick_people(people, icp)
                   if (p.first_name.lower(), p.last_name.lower()) not in known_names]
        if not targets:
            done(s, "no_new_persona", company_id=existing["id"] if existing else "")
            continue

        if dry_run:
            done(s, "would_prospect", company_exists=bool(existing),
                 would_reveal=[f"{p.first_name} {p.last_name}, {p.title}" for p in targets])
            continue
        # Worst case is every provider charging for every target. Starting a
        # company only when that fits means the cap is never exceeded and no
        # company is left half prospected.
        if not budget.allows(len(targets) * len(providers)):
            done(s, "budget_exhausted")
            continue

        contacts, dropped = [], []
        for p in targets:
            ct = waterfall.reveal(p, providers, c.country, budget, stats)
            who = f"{p.first_name} {p.last_name}"
            if not ct:
                dropped.append({"name": who, "why": "not_found"})
            elif ct.email and ct.email in suppression:
                dropped.append({"name": who, "why": "suppressed_email"})
            elif ct.email and crm.find_contact_by_email(ct.email):
                dropped.append({"name": who, "why": "email_already_in_crm"})
            elif routing.get("require_phone", True) and not ct.phone:
                dropped.append({"name": who, "why": "no_valid_phone"})
            else:
                contacts.append(ct)
        if not contacts:
            done(s, "no_callable_contact", dropped=dropped,
                 company_id=existing["id"] if existing else "")
            continue

        if existing:
            company_id = existing["id"]
            owner_id = existing.get("owner_id") or router.assign(c.country)["owner_id"]
            outcome = "added_to_existing_company"
        else:
            owner_id = router.assign(c.country)["owner_id"]
            company_id = crm.create_company({
                "name": c.name, "domain": c.domain, "owner_id": owner_id, "industry": c.industry,
                "numberofemployees": c.employees, "country": c.country, "city": c.city,
                "icp_tier": s.tier, "icp_score": s.total, "top_signal": s.top_signal})["id"]
            outcome = "created_company"

        tcfg = routing["task"]
        written = []
        for ct in contacts:
            rec = crm.create_contact({
                "email": ct.email, "firstname": ct.first_name, "lastname": ct.last_name,
                "jobtitle": ct.title, "phone": ct.phone, "phone_type": ct.phone_type,
                "owner_id": owner_id, "source": f"prospecting:{ct.phone_source or ct.email_source}"},
                company_id)
            task = crm.create_task({
                "subject": tcfg["subject"].format(first_name=ct.first_name, last_name=ct.last_name,
                                                  title=ct.title, company=c.name),
                "body": (f"Tier {s.tier}, score {s.total}. Why now: {s.top_signal or 'ICP fit'}. "
                         f"Scoring: {'; '.join(s.reasons)}. Phone via {ct.phone_source} ({ct.phone_type})."),
                "due": due_date(tcfg["due_in_business_days"]),
                "priority": tcfg["priority_by_tier"].get(s.tier, "MEDIUM"), "owner_id": owner_id},
                rec["id"], company_id)
            entry = {"crm_contact_id": rec["id"], "task_id": task["id"],
                     "name": f"{ct.first_name} {ct.last_name}", "phone": ct.phone,
                     "phone_source": ct.phone_source}
            written.append(entry)
            if push_dialer and s.tier in routing["dialer"]["tiers"]:
                _push(dialer, ledger, routing, run_id, entry, c, s, owner_id)
        done(s, outcome, company_id=company_id, owner_id=owner_id, contacts=written, dropped=dropped)

    return {"run_id": run_id, "dry_run": dry_run, "sourced": len(companies),
            "filtered_out": filtered_out, "results": results, "credits_spent": budget.spent,
            "provider_stats": stats}


def _push(dialer, ledger, routing, run_id, entry, company, scored, owner_id) -> None:
    dialer.push(routing["dialer"]["campaign_task"], {
        "phone": entry["phone"], "crm_contact_id": entry["crm_contact_id"], "name": entry["name"],
        "company": company.name, "tier": scored.tier, "why_now": scored.top_signal,
        "owner_id": owner_id})
    ledger.append({"event": "dialer_push", "run_id": run_id,
                   "crm_contact_id": entry["crm_contact_id"], "domain": company.domain})
