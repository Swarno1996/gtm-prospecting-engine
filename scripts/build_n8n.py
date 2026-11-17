"""Generate the n8n workflow exports in n8n/ from one source of truth.

Run: python scripts/build_n8n.py
The JSON files are committed; this script keeps them consistent (ids,
positions, connections) when a workflow changes.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "n8n"
NS = uuid.UUID("6f1f6b2e-5d0a-4c2e-9a51-0b7d3c1e2a90")


def nid(wf: str, name: str) -> str:
    return str(uuid.uuid5(NS, f"{wf}/{name}"))


def node(wf, name, type_, version, params, x, y, **extra):
    n = {"parameters": params, "id": nid(wf, name), "name": name, "type": f"n8n-nodes-base.{type_}",
         "typeVersion": version, "position": [x, y]}
    n.update(extra)
    return n


def config(wf, x=220, y=300, extra=()):
    items = [("engineUrl", "http://localhost:8787"), ("alertEmail", "you@example.com"), *extra]
    return node(wf, "Config", "set", 3.4, {
        "assignments": {"assignments": [
            {"id": nid(wf, f"cfg/{k}"), "name": k, "value": v, "type": "string"} for k, v in items]},
        "options": {}}, x, y)


def engine(wf, name, method, path, x, y, body=None):
    p = {"method": method, "url": f"={{{{ $('Config').item.json.engineUrl }}}}{path}",
         "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
         "options": {"timeout": 300000}}
    if body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return node(wf, name, "httpRequest", 4.2, p, x, y)


def gmail(wf, name, subject, message, x, y):
    return node(wf, name, "gmail", 2.1, {
        "sendTo": "={{ $('Config').item.json.alertEmail }}", "subject": subject,
        "emailType": "text", "message": message, "options": {}}, x, y)


def if_true(wf, name, expr, x, y):
    return node(wf, name, "if", 2, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
            "conditions": [{"id": nid(wf, f"{name}/c1"), "leftValue": expr, "rightValue": "",
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and"},
        "options": {}}, x, y)


def chain(*names):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}


def workflow(name, nodes, connections, tags):
    return {"name": name, "nodes": nodes, "connections": connections, "active": False,
            "settings": {"executionOrder": "v1"}, "pinData": {},
            "meta": {"templateCredsSetupCompleted": False},
            "tags": [{"name": t} for t in tags]}


# ---------------------------------------------------------------- 01 prospecting
wf = "01"
SUMMARY_JS = r"""// Turn the engine's run result into one alert decision and one readable email.
const r = $input.first().json;
const o = r.outcomes || {};
const providers = Object.entries(r.provider_stats || {})
  .map(([n, s]) => `${n}: ${s.reveals} reveals, ${s.valid_phone} valid phone, ${s.bad_phone} bad phone`)
  .join('\n');
const contacts = (r.contacts || []).map(c => `${c.name} (${c.phone_source})`).join('\n');
const alert = r.sourced === 0 || (r.contacts_created === 0 && !r.dry_run);
return [{ json: {
  alert,
  subject: alert
    ? `ALERT prospecting run ${r.run_id}: ${r.contacts_created} contacts created`
    : `Prospecting run ${r.run_id}: ${r.contacts_created} new contacts, ${r.credits_spent} credits`,
  body: [
    `Accounts sourced: ${r.sourced}`,
    `Contacts created with SDR call tasks: ${r.contacts_created}`,
    `Credits spent: ${r.credits_spent}`,
    `Outcomes: ${JSON.stringify(o)}`,
    '', 'Provider quality:', providers || 'no reveals',
    '', 'New contacts:', contacts || 'none',
  ].join('\n'),
}}];"""
nodes = [
    node(wf, "Weekdays 07:00", "scheduleTrigger", 1.2,
         {"rule": {"interval": [{"field": "cronExpression", "expression": "0 7 * * 1-5"}]}}, 0, 300),
    config(wf, extra=[("maxCredits", "50")]),
    engine(wf, "Run prospecting", "POST", "/prospect", 440, 300,
           body="={{ JSON.stringify({ max_credits: Number($('Config').item.json.maxCredits), "
                "push_dialer: true, dry_run: false }) }}"),
    node(wf, "Build summary", "code", 2, {"jsCode": SUMMARY_JS}, 660, 300),
    if_true(wf, "Needs attention?", "={{ $json.alert }}", 880, 300),
    gmail(wf, "Send ALERT", "={{ $json.subject }}", "={{ $json.body }}", 1100, 200),
    gmail(wf, "Send run summary", "={{ $json.subject }}", "={{ $json.body }}", 1100, 400),
]
conn = chain("Weekdays 07:00", "Config", "Run prospecting", "Build summary", "Needs attention?")
conn["Needs attention?"] = {"main": [[{"node": "Send ALERT", "type": "main", "index": 0}],
                                     [{"node": "Send run summary", "type": "main", "index": 0}]]}
W1 = workflow("GTM 01: Scheduled prospecting run", nodes, conn, ["gtm", "prospecting"])

# ---------------------------------------------------------------- 02 call outcome
wf = "02"
MAP_JS = r"""// Map a Dialfire webhook task payload onto the engine's call outcome contract.
// Dialfire sends the contact's campaign fields. crm_contact_id is one of them because
// the engine writes it when it loads the contact. The status values are defined per
// campaign: edit STATUS_MAP to match yours, then check against a real execution.
const STATUS_MAP = {
  success: 'meeting_booked', termin: 'meeting_booked',
  declined: 'not_interested', kein_interesse: 'not_interested',
  no_answer: 'no_answer', nicht_erreicht: 'no_answer',
  callback: 'callback', wiedervorlage: 'callback',
  wrong_number: 'wrong_number', falsche_nummer: 'wrong_number',
  dnc: 'do_not_call', sperre: 'do_not_call',
};
const b = $input.first().json.body || {};
const status = String(b.$status || b.status || '').toLowerCase();
const outcome = STATUS_MAP[status];
if (!b.crm_contact_id || !outcome) {
  throw new Error(`Call outcome contract broken: crm_contact_id=${b.crm_contact_id} status=${status}`);
}
return [{ json: {
  crm_contact_id: String(b.crm_contact_id),
  outcome,
  call_id: String(b.$call_id || b.call_id || b.$id || ''),
  callback_at: b.callback_at || '',
  notes: b.notes || b.comment || '',
  agent: b.$user || b.agent || '',
}}];"""
nodes = [
    node(wf, "Dialfire webhook", "webhook", 2,
         {"httpMethod": "POST", "path": "gtm-call-outcome", "responseMode": "responseNode", "options": {}},
         0, 300, webhookId=nid(wf, "webhook")),
    config(wf),
    node(wf, "Map Dialfire fields", "code", 2, {"jsCode": MAP_JS}, 440, 300),
    engine(wf, "Write outcome to CRM", "POST", "/call-outcome", 660, 300, body="={{ JSON.stringify($json) }}"),
    node(wf, "Respond", "respondToWebhook", 1.1,
         {"respondWith": "json", "responseBody": "={{ JSON.stringify({ ok: true, actions: $json.actions }) }}",
          "options": {}}, 880, 300),
]
W2 = workflow("GTM 02: Dialfire call outcome to CRM", nodes,
              chain("Dialfire webhook", "Config", "Map Dialfire fields", "Write outcome to CRM", "Respond"),
              ["gtm", "dialer"])

# ---------------------------------------------------------------- 03 digest
wf = "03"
DIGEST_JS = r"""// Daily funnel digest. ALERT when the funnel has gone quiet.
const r = $input.first().json;
const o = r.outcomes || {};
const dropped = Object.entries(r.contacts_dropped || {}).map(([k, v]) => `  ${k}: ${v}`).join('\n');
const alert = (r.contacts_created || 0) === 0;
return [{ json: {
  subject: `${alert ? 'ALERT ' : ''}GTM funnel: ${r.contacts_created} contacts, ${r.dialer_loaded} in dialer`,
  body: [
    `Runs: ${r.runs}`, `Accounts processed: ${r.companies_processed}`,
    `Contacts created: ${r.contacts_created}`, `Loaded into dialer: ${r.dialer_loaded}`,
    `Outcomes: ${JSON.stringify(o)}`, `Phone source mix: ${JSON.stringify(r.phone_source || {})}`,
    'Dropped contacts:', dropped || '  none',
  ].join('\n'),
}}];"""
nodes = [
    node(wf, "Daily 09:00", "scheduleTrigger", 1.2,
         {"rule": {"interval": [{"field": "cronExpression", "expression": "0 9 * * *"}]}}, 0, 300),
    config(wf),
    engine(wf, "Get funnel report", "GET", "/report", 440, 300),
    node(wf, "Format digest", "code", 2, {"jsCode": DIGEST_JS}, 660, 300),
    gmail(wf, "Send digest", "={{ $json.subject }}", "={{ $json.body }}", 880, 300),
]
W3 = workflow("GTM 03: Daily funnel digest", nodes,
              chain("Daily 09:00", "Config", "Get funnel report", "Format digest", "Send digest"),
              ["gtm", "monitoring"])

# ---------------------------------------------------------------- 04 errors
wf = "04"
nodes = [
    node(wf, "On workflow error", "errorTrigger", 1, {}, 0, 300),
    node(wf, "Send error alert", "gmail", 2.1, {
        "sendTo": "you@example.com",
        "subject": "=n8n FAILED: {{ $json.workflow.name }} / {{ $json.execution.lastNodeExecuted }}",
        "emailType": "text",
        "message": "={{ $json.execution.error.message }}\n\nExecution: {{ $json.execution.url }}",
        "options": {}}, 240, 300),
]
W4 = workflow("GTM 04: Error alerts", nodes, chain("On workflow error", "Send error alert"),
              ["gtm", "monitoring"])

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fname, w in [("01_scheduled_prospecting.json", W1), ("02_dialfire_call_outcome.json", W2),
                     ("03_daily_funnel_digest.json", W3), ("04_error_alerts.json", W4)]:
        (OUT / fname).write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote n8n/{fname}")
