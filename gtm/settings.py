"""Environment loading and adapter selection.

Mock mode is the default and needs no keys. Live mode is opt in per system,
so you can run a live CRM against mock data providers while you test.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def state_dir() -> Path:
    d = Path(env("GTM_STATE_DIR", str(ROOT / ".state")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_crm():
    if env("GTM_CRM", "mock") == "hubspot":
        from gtm.crm.hubspot import HubSpotCRM

        return HubSpotCRM(env("HUBSPOT_TOKEN"))
    from gtm.crm.mock import MockCRM

    return MockCRM(state_dir() / "crm.json", ROOT / "fixtures" / "crm_seed.json")


def build_providers() -> list:
    """Providers in waterfall order. GTM_PROVIDERS=cognism,lusha for live."""
    names = [n.strip() for n in env("GTM_PROVIDERS", "mock_cognism,mock_lusha").split(",") if n.strip()]
    out = []
    for n in names:
        if n.startswith("mock_"):
            from gtm.providers.mock import MockProvider

            out.append(MockProvider(n[5:], ROOT / "fixtures" / "people.json"))
        elif n == "lusha":
            from gtm.providers.lusha import LushaProvider

            out.append(LushaProvider(env("LUSHA_API_KEY")))
        elif n == "cognism":
            from gtm.providers.cognism import CognismProvider

            out.append(CognismProvider(env("COGNISM_API_KEY")))
        else:
            raise ValueError(f"unknown provider: {n}")
    return out


def build_dialer():
    if env("GTM_DIALER", "mock") == "dialfire":
        from gtm.dialer.dialfire import DialfireDialer

        return DialfireDialer(env("DIALFIRE_CAMPAIGN_ID"), env("DIALFIRE_CAMPAIGN_TOKEN"))
    from gtm.dialer.mock import MockDialer

    return MockDialer(state_dir() / "dialer.jsonl")


def suppression_file() -> Path:
    """Static list in config plus a runtime list the call outcome flow appends to."""
    return state_dir() / "suppression_runtime.txt"
