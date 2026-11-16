import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gtm import icp as icp_mod  # noqa: E402
from gtm import sources  # noqa: E402
from gtm.crm.mock import MockCRM  # noqa: E402
from gtm.dialer.mock import MockDialer  # noqa: E402
from gtm.flows import prospect  # noqa: E402
from gtm.ledger import Ledger  # noqa: E402
from gtm.providers.mock import MockProvider  # noqa: E402
from gtm.routing import Router  # noqa: E402


@pytest.fixture
def env(tmp_path):
    routing = yaml.safe_load((ROOT / "config" / "routing.yaml").read_text())

    class Env:
        icp = icp_mod.load(ROOT / "config" / "icp.yaml")
        companies = sources.load(ROOT / "fixtures" / "companies.json")
        crm = MockCRM(tmp_path / "crm.json", ROOT / "fixtures" / "crm_seed.json")
        dialer = MockDialer(tmp_path / "dialer.jsonl")
        ledger = Ledger(tmp_path / "ledger.jsonl")
        suppression = sources.load_suppression(ROOT / "config" / "suppression.txt")

        def run(self, **kw):
            providers = [MockProvider("cognism", ROOT / "fixtures" / "people.json"),
                         MockProvider("lusha", ROOT / "fixtures" / "people.json")]
            return prospect.run(self.companies, icp=self.icp, routing=routing, crm=self.crm,
                                providers=providers, dialer=self.dialer, ledger=self.ledger,
                                router=Router(routing, tmp_path / "rr.json"),
                                suppression=self.suppression, **kw)

    e = Env()
    e.routing = routing
    return e
