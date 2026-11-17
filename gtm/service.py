"""One place that wires config, adapters and state for every flow.

The CLI, the HTTP server, n8n and Langdock all go through these functions,
so a flow behaves the same no matter what triggered it.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from gtm import icp as icp_mod
from gtm import settings, sources
from gtm.flows import call_brief, call_outcome, crm_lookup, dialer_sync, prospect, report
from gtm.ledger import Ledger
from gtm.routing import Router

ROOT = settings.ROOT
DEFAULTS = {
    "source": ROOT / "fixtures" / "companies.json",
    "icp": ROOT / "config" / "icp.yaml",
    "routing": ROOT / "config" / "routing.yaml",
    "suppression": ROOT / "config" / "suppression.txt",
}


def _routing(path=None) -> dict:
    return yaml.safe_load(Path(path or DEFAULTS["routing"]).read_text())


def _ledger() -> Ledger:
    return Ledger(settings.state_dir() / "ledger.jsonl")


def suppression(path=None) -> set[str]:
    return (sources.load_suppression(path or DEFAULTS["suppression"])
            | sources.load_suppression(settings.suppression_file()))


def lookup(query: str) -> dict:
    return crm_lookup.run(settings.build_crm(), query)


def prospect_run(*, source=None, icp=None, routing=None, suppression_path=None, max_credits=None,
                 dry_run=False, push_dialer=False) -> dict:
    r = _routing(routing)
    return prospect.run(
        sources.load(source or DEFAULTS["source"]), icp=icp_mod.load(icp or DEFAULTS["icp"]),
        routing=r, crm=settings.build_crm(), providers=settings.build_providers(),
        dialer=settings.build_dialer(), ledger=_ledger(),
        router=Router(r, settings.state_dir() / "roundrobin.json"),
        suppression=suppression(suppression_path), max_credits=max_credits, dry_run=dry_run,
        push_dialer=push_dialer)


def dialer(dry_run=False, routing=None) -> dict:
    return dialer_sync.run(_ledger(), settings.build_dialer(), _routing(routing), dry_run)


def outcome(payload: dict, routing=None) -> dict:
    return call_outcome.run(settings.build_crm(), _ledger(), payload, routing=_routing(routing),
                            suppression_file=settings.suppression_file())


def brief(contact_id: str) -> dict:
    return call_brief.run(settings.build_crm(), _ledger(), contact_id)


def funnel() -> dict:
    return report.run(_ledger())
