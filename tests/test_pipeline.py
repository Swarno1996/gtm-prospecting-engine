from gtm.flows import dialer_sync, report


def outcomes(res):
    return {r["domain"]: r["outcome"] for r in res["results"]}


def test_full_run(env):
    res = env.run(push_dialer=True)
    o = outcomes(res)
    assert o["hansa-fracht.example"] == "created_company"
    assert o["alpenwerk-maschinenbau.example"] == "added_to_existing_company"
    assert o["optout-logistik.example"] == "skipped_suppressed"
    assert o["nordlicht-retail.example"] == "skipped_customer_or_open_deal"   # www. domain in CRM
    assert o["donau-fertigung.example"] == "skipped_customer_or_open_deal"    # matched by name
    assert o["westfalen-transport.example"] == "no_callable_contact"
    assert o["baltic-software.example"] == "below_tier"
    assert "uk-freight.example" not in o and res["filtered_out"] == 3

    # Waterfall: the first provider had a malformed number, the second one fixed it.
    hansa = next(r for r in res["results"] if r["domain"] == "hansa-fracht.example")
    kern = next(c for c in hansa["contacts"] if c["name"] == "Tobias Kern")
    assert kern["phone_source"] == "lusha" and kern["phone"] == "+4917604069012"

    # Existing account keeps its owner and its existing contact is not revealed again.
    alpen = env.crm.find_company("alpenwerk-maschinenbau.example")
    names = {c["lastname"] for c in env.crm.company_contacts(alpen["id"])}
    assert names == {"Moser", "Gruber"}
    assert all(t["owner_id"] == "1003" for t in env.crm.open_tasks(alpen["id"]))

    # Email already in the CRM is never duplicated.
    assert sum(1 for c in env.crm.db["contacts"] if c["email"] == "j.brandt@spree-handel.example") == 1

    # One call task per created contact, dialer gets tier A only.
    assert len(env.crm.db["tasks"]) == 7
    assert len(env.dialer.loaded_refs()) == 4


def test_rerun_is_idempotent(env):
    env.run()
    before = (len(env.crm.db["companies"]), len(env.crm.db["contacts"]), len(env.crm.db["tasks"]))
    res = env.run()
    assert res["credits_spent"] == 0
    assert before == (len(env.crm.db["companies"]), len(env.crm.db["contacts"]), len(env.crm.db["tasks"]))


def test_dry_run_writes_nothing(env):
    res = env.run(dry_run=True)
    assert res["credits_spent"] == 0 and env.ledger.rows() == []
    assert len(env.crm.db["companies"]) == 4 and env.crm.db["tasks"] == []
    assert "would_prospect" in outcomes(res).values()


def test_credit_budget_stops_and_resumes(env):
    first = env.run(max_credits=3)
    assert first["credits_spent"] <= 3
    assert "budget_exhausted" in outcomes(first).values()
    second = env.run()
    assert "created_company" in outcomes(second).values()
    final = report.run(env.ledger)
    assert final["contacts_created"] == 7


def test_dialer_sync_loads_once(env):
    env.run(push_dialer=False)
    assert dialer_sync.run(env.ledger, env.dialer, env.routing)["pushed"].__len__() == 4
    assert dialer_sync.run(env.ledger, env.dialer, env.routing)["pushed"] == []
