import pytest

from gtm.flows import call_brief, call_outcome


@pytest.fixture
def ran(env, tmp_path):
    env.run()
    env.supp = tmp_path / "supp.txt"
    lena = env.crm.find_contact_by_email("lena.hartmann@hansa-fracht.example")
    return env, lena["id"]


def outcome(env, cid, outcome, **kw):
    return call_outcome.run(env.crm, env.ledger, {"crm_contact_id": cid, "outcome": outcome, **kw},
                            routing=env.routing, suppression_file=env.supp)


def test_no_answer_retries_then_stops(ran):
    env, cid = ran
    for i in (1, 2):
        res = outcome(env, cid, "no_answer", call_id=f"c{i}")
        assert any("Retry call" in a for a in res["actions"])
    res = outcome(env, cid, "no_answer", call_id="c3")
    assert "max attempts reached, sequence stopped" in res["actions"]
    assert env.crm.contact_open_tasks(cid) == []
    assert env.crm.get_contact(cid)["hs_lead_status"] == "ATTEMPTED_TO_CONTACT"


def test_same_call_id_is_ignored(ran):
    env, cid = ran
    outcome(env, cid, "no_answer", call_id="dup")
    assert outcome(env, cid, "no_answer", call_id="dup")["duplicate"] is True
    assert len(env.ledger.calls(cid)) == 1


def test_meeting_booked(ran):
    env, cid = ran
    outcome(env, cid, "meeting_booked")
    tasks = env.crm.contact_open_tasks(cid)
    assert len(tasks) == 1 and tasks[0]["subject"].startswith("Prepare discovery call")
    assert env.crm.get_contact(cid)["hs_lead_status"] == "OPEN_DEAL"


def test_do_not_call_suppresses_future_runs(ran):
    env, cid = ran
    outcome(env, cid, "do_not_call")
    assert env.crm.get_contact(cid)["phone"] == ""
    assert "lena.hartmann@hansa-fracht.example" in env.supp.read_text()


def test_callback_validates_time(ran):
    env, cid = ran
    with pytest.raises(call_outcome.OutcomeError):
        outcome(env, cid, "callback", callback_at="next tuesday")
    res = outcome(env, cid, "callback", callback_at="2026-12-01T10:00:00+01:00")
    assert env.crm.contact_open_tasks(cid)[0]["due"] == "2026-12-01T10:00:00+01:00"
    assert res["attempt"] == 1


def test_rejects_unknown_outcome_and_contact(ran):
    env, cid = ran
    with pytest.raises(call_outcome.OutcomeError):
        outcome(env, cid, "maybe")
    with pytest.raises(call_outcome.OutcomeError):
        outcome(env, "ct-0", "no_answer")


def test_call_brief_uses_ledger_facts(ran, monkeypatch):
    env, cid = ran
    monkeypatch.delenv("LANGDOCK_API_KEY", raising=False)
    outcome(env, cid, "no_answer")
    res = call_brief.run(env.crm, env.ledger, cid)
    assert res["written_by"] == "template"
    assert "New VP Sales started this month" in res["brief"]
    assert "tier A" in res["brief"] and "Previous calls: no_answer" in res["brief"]


def test_call_brief_survives_llm_failure(ran, monkeypatch):
    env, cid = ran
    monkeypatch.setenv("LANGDOCK_API_KEY", "x")

    def boom(*a, **k):
        raise TimeoutError

    monkeypatch.setattr(call_brief.llm, "complete", boom)
    res = call_brief.run(env.crm, env.ledger, cid)
    assert res["written_by"].startswith("template (langdock error")
