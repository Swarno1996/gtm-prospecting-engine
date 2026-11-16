from datetime import date

from gtm import icp as icp_mod
from gtm import normalize
from gtm.models import Company, Person, Signal
from gtm.routing import due_date
from datetime import datetime, timezone


def test_domain_normalization():
    assert normalize.domain("https://WWW.Acme.example/path?x=1") == "acme.example"
    assert normalize.domain("anna@acme.example") == "acme.example"


def test_company_name_ignores_legal_form():
    assert normalize.company_name("Main Logistik GmbH & Co. KG") == normalize.company_name("main logistik")


def test_phone_validation():
    assert normalize.phone("0171 3920001", "DE") == ("+491713920001", "mobile")
    assert normalize.phone("+49 30 23125101") == ("+493023125101", "landline")
    assert normalize.phone("0041 79 555 01 23") == ("+41795550123", "mobile")
    for bad in ("", "n/a", "0000000", "+49 171 392", "+49 111111111"):
        assert normalize.phone(bad, "DE")[0] == "", bad


def _co(**kw):
    base = dict(domain="x.example", name="X", industry="logistics", employees=2000, country="DE")
    return Company(**{**base, **kw})


def test_hard_filters(env):
    assert icp_mod.score(_co(country="GB"), env.icp) is None
    assert icp_mod.score(_co(employees=50), env.icp) is None
    assert icp_mod.score(_co(industry="government"), env.icp) is None


def test_signal_decay_and_tier(env):
    today = date(2026, 6, 1)
    fresh = icp_mod.score(_co(signals=[Signal("new_sales_leader", "2026-06-01")]), env.icp, today)
    old = icp_mod.score(_co(signals=[Signal("new_sales_leader", "2026-04-17")]), env.icp, today)
    stale = icp_mod.score(_co(signals=[Signal("new_sales_leader", "2025-06-01")]), env.icp, today)
    assert fresh.signal == 45 and round(old.signal, 1) == 22.5 and stale.signal == 0
    assert fresh.tier == "A" and stale.tier == "B"  # fit alone never reaches tier A


def test_persona_selection(env):
    people = [Person("A", "Z", "Sales Assistant", "x"), Person("B", "Y", "Head of Revenue Operations", "x"),
              Person("C", "X", "VP Sales", "x"), Person("D", "W", "Sales Director", "x")]
    picked = icp_mod.pick_people(people, env.icp)
    assert [p.first_name for p in picked] == ["C", "B"]


def test_due_date_skips_weekend():
    friday = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
    assert due_date(1, friday).startswith("2026-11-16")
