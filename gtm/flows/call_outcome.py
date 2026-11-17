"""Flow 6: write a dialer call outcome back to the CRM.

The dialer (Dialfire webhook task, or any dialer) posts one result per call.
This flow closes the SDR task, logs a note, and decides the next step, so the
CRM reflects what happened on the phone without anyone typing it in.

Outcomes:
    meeting_booked     close task, lead status to OPEN_DEAL, prep task for the meeting
    not_interested     close task, lead status UNQUALIFIED, no further tasks
    no_answer          close task, retry next business day, stop after max_attempts
    callback           close task, new task due at the time the prospect asked for
    wrong_number       close task, clear the phone, task to find a new number
    do_not_call        close task, clear the phone, suppress the email for every future run
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gtm.ledger import Ledger
from gtm.routing import due_date

OUTCOMES = {"meeting_booked", "not_interested", "no_answer", "callback", "wrong_number", "do_not_call"}


class OutcomeError(ValueError):
    pass


def run(crm, ledger: Ledger, payload: dict, *, routing: dict, suppression_file: Path) -> dict:
    contact_id = str(payload.get("crm_contact_id") or "").strip()
    outcome = str(payload.get("outcome") or "").strip()
    if not contact_id or outcome not in OUTCOMES:
        raise OutcomeError(f"need crm_contact_id and outcome in {sorted(OUTCOMES)}")
    contact = crm.get_contact(contact_id)
    if not contact:
        raise OutcomeError(f"contact {contact_id} not found in CRM")

    call_id = str(payload.get("call_id") or "")
    if call_id and any(r.get("call_id") == call_id for r in ledger.calls(contact_id)):
        return {"contact_id": contact_id, "outcome": outcome, "duplicate": True, "actions": []}

    cfg = routing.get("calls", {})
    attempt = len(ledger.calls(contact_id)) + 1
    who = f"{contact.get('firstname', '')} {contact.get('lastname', '')}".strip()
    owner = payload.get("owner_id") or ""
    company_id = contact.get("company_id", "")
    actions: list[str] = []

    for t in crm.contact_open_tasks(contact_id):
        crm.complete_task(t["id"])
        actions.append(f"completed task {t['id']}")

    note = f"Call attempt {attempt}: {outcome}."
    if payload.get("agent"):
        note += f" Agent: {payload['agent']}."
    if payload.get("notes"):
        note += f" Notes: {payload['notes']}"
    crm.add_note(contact_id, note)
    actions.append("logged note")

    def task(subject: str, due: str, priority: str = "MEDIUM") -> None:
        crm.create_task({"subject": subject, "body": note, "due": due, "priority": priority,
                         "owner_id": owner}, contact_id, company_id)
        actions.append(f"created task: {subject}")

    if outcome == "meeting_booked":
        crm.update_contact(contact_id, {"hs_lead_status": "OPEN_DEAL"})
        task(f"Prepare discovery call with {who}", due_date(1), "HIGH")
    elif outcome == "not_interested":
        crm.update_contact(contact_id, {"hs_lead_status": "UNQUALIFIED"})
    elif outcome == "no_answer":
        if attempt < cfg.get("max_attempts", 3):
            task(f"Retry call {attempt + 1} to {who}", due_date(cfg.get("retry_after_business_days", 1)))
        else:
            crm.update_contact(contact_id, {"hs_lead_status": "ATTEMPTED_TO_CONTACT"})
            actions.append("max attempts reached, sequence stopped")
    elif outcome == "callback":
        when = payload.get("callback_at") or due_date(1)
        try:
            datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError as e:
            raise OutcomeError(f"callback_at is not ISO 8601: {when}") from e
        task(f"Callback {who} as agreed", when, "HIGH")
    elif outcome == "wrong_number":
        crm.update_contact(contact_id, {"phone": ""})
        task(f"Find a new number for {who}", due_date(2), "LOW")
    elif outcome == "do_not_call":
        crm.update_contact(contact_id, {"phone": "", "hs_lead_status": "UNQUALIFIED"})
        email = (contact.get("email") or "").lower()
        if email:
            with Path(suppression_file).open("a") as f:
                f.write(email + "\n")
            actions.append(f"suppressed {email}")

    ledger.append({"event": "call", "crm_contact_id": contact_id, "call_id": call_id,
                   "outcome": outcome, "attempt": attempt,
                   "at": payload.get("at") or datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"contact_id": contact_id, "outcome": outcome, "attempt": attempt, "duplicate": False,
            "actions": actions}
