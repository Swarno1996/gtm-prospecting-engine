# Langdock layer

Langdock connects to the engine in both directions.

**Langdock calls the engine.** Langdock workflows use an HTTP Request node to call the engine's server (`python -m gtm serve`). The engine does the deterministic work: scoring, dedupe, reveals, CRM writes. Langdock adds a schedule, a form for SDRs, and an Agent node where judgment on text is needed.

**The engine calls Langdock.** `gtm/llm.py` uses Langdock's OpenAI compatible completion API for the call brief text. With `LANGDOCK_API_KEY` set, model usage runs through the same workspace, keys and model policy as the rest of the company. Without it, a template writes the brief.

| Workflow | Trigger | What Langdock adds | Engine endpoint |
|---|---|---|---|
| L1 Weekly prospecting summary | Scheduled Trigger | Agent turns run JSON into a short update for the sales lead | `POST /prospect` |
| L2 Call prep on demand | Form Trigger | A form any SDR can use without touching the CRM | `GET /call-brief` |
| L3 Call notes triage | Webhook Trigger | Agent classifies free text call notes into an outcome, with a confidence gate before any CRM write | `POST /call-outcome` |

The split is deliberate: numbers come from code, the model only writes or classifies text, and nothing the model produces reaches the CRM without passing the engine's validation (`call_outcome.run` rejects unknown outcomes and malformed callback times).

## Files

- `workflows/*.yaml`: node by node build specs. Langdock workflows are built in the editor; these files list every node and setting so a workflow can be rebuilt exactly. They are not an import format.
- `agents/*.md`: the instructions for each Agent node, including the structured output schema for L3.

## Setup

1. Run the engine where Langdock can reach it, with `GTM_SERVER_SECRET` set.
2. Build each workflow from its spec. Store the secret in the HTTP Request node headers.
3. For L3, enable a webhook secret on the trigger and point your dialer or SDR tool at the webhook URL.
4. Optional: set `LANGDOCK_API_KEY` (and `LANGDOCK_REGION`, `LANGDOCK_MODEL`) in the engine's `.env` so call briefs are written by a model.
