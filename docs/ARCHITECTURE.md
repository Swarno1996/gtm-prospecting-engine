# Architecture

## Ports and adapters

The flows only know three interfaces. Everything vendor specific sits behind them.

| Port | Methods | Adapters |
|---|---|---|
| Data provider | `find_people(company)` free preview, `reveal(person)` paid | mock, Cognism, Lusha |
| CRM | `find_company`, `company_contacts`, `find_contact_by_email`, `create_company`, `create_contact`, `create_task`, `open_tasks` | mock (JSON file), HubSpot |
| Dialer | `push(task_name, record)`, `loaded_refs()` | mock (JSONL file), Dialfire |

Adding Salesforce, Apollo or Aircall means one new file that implements the port and one line in `gtm/settings.py`.

## Order of checks in `prospect`

1. Hard filters and scoring (`icp.py`). Free.
2. Tier gate from `routing.yaml`. Free.
3. Cooldown from the ledger. Free.
4. Suppression by domain. Free.
5. CRM account lookup by domain, then by normalized name. One CRM read.
6. Stage gate: customers, opportunities and accounts with open deals stop here.
7. People preview from the first provider that returns any. Free.
8. Persona selection, then removal of people already on the account by name.
9. Budget gate: the worst case for this company must fit the remaining cap.
10. Waterfall reveal with phone and email validation. Credits are spent here.
11. Suppression and CRM lookup by revealed email.
12. Writes: company (if new), contacts, one call task per contact, optional dialer load.
13. Ledger line.

## Scoring

`total = 0.6 * fit + 0.4 * signal`, both on a 0 to 100 scale.

Fit is industry points plus size band points plus country points. Each signal contributes `weight * 0.5 ^ (age_days / half_life_days)`.

Tier A needs 65. Maximum fit contributes 60, so tier A is unreachable without a live signal.

## Dedupe keys

| Object | Key | Fallback |
|---|---|---|
| Company | normalized domain (scheme, `www.`, path removed) | company name with legal forms removed (GmbH, AG, SE, KG and others) |
| Contact before reveal | first and last name on the matched account | none |
| Contact after reveal | email | none |
| Dialer record | CRM contact id in the ledger | dialer side reference |

## Known limits

- Phone validation is a format check for DE, AT and CH numbers. It does not prove that a line is connected.
- Name based company matching is exact after normalization. It will not match "Hansa Fracht" to "HFL Group".
- The Dialfire adapter relies on the ledger for idempotency and does not query the campaign.
- Signals arrive with the account source. Nothing in this repo detects signals on its own.
