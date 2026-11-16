from __future__ import annotations

import argparse
import json
import shutil
import sys

import yaml

from gtm import icp as icp_mod
from gtm import settings, sources
from gtm.flows import build_list, crm_lookup, dialer_sync, prospect, report
from gtm.ledger import Ledger
from gtm.routing import Router

ROOT = settings.ROOT


def _routing(args) -> dict:
    return yaml.safe_load(open(args.routing))


def cmd_lookup(args) -> int:
    res = crm_lookup.run(settings.build_crm(), args.query)
    if not res["found"]:
        print(f"Not in CRM: {args.query}")
        return 0
    c = res["company"]
    print(f"{c['name']}  ({c['domain']})  id {c['id']}")
    print(f"  stage {c.get('lifecyclestage') or 'none'}, open deals {c.get('open_deals', 0)}, owner {c.get('owner_id') or 'unassigned'}")
    print(f"  contacts: {len(res['contacts'])}")
    for ct in res["contacts"]:
        print(f"    {ct.get('firstname', '')} {ct.get('lastname', '')}, {ct.get('jobtitle', '')}  {ct.get('email', '')}  {ct.get('phone', '')}")
    print(f"  open tasks: {len(res['open_tasks'])}")
    for t in res["open_tasks"]:
        print(f"    {t.get('subject', '')}  due {t.get('due', '')}")
    return 0


def cmd_list(args) -> int:
    scored = build_list.run(sources.load(args.source), icp_mod.load(args.icp))
    build_list.write_csv(scored, args.out)
    print(f"{'#':>2}  tier  score  fit  sig  company")
    for i, s in enumerate(scored, 1):
        print(f"{i:>2}  {s.tier:<4}  {s.total:>5}  {s.fit:>3.0f}  {s.signal:>3.0f}  {s.company.name}"
              + (f"  [{s.top_signal}]" if s.top_signal else ""))
    print(f"\n{len(scored)} companies in ICP, written to {args.out}")
    return 0


def cmd_prospect(args) -> int:
    routing = _routing(args)
    state = settings.state_dir()
    res = prospect.run(
        sources.load(args.source), icp=icp_mod.load(args.icp), routing=routing,
        crm=settings.build_crm(), providers=settings.build_providers(), dialer=settings.build_dialer(),
        ledger=Ledger(state / "ledger.jsonl"), router=Router(routing, state / "roundrobin.json"),
        suppression=sources.load_suppression(args.suppression), max_credits=args.max_credits,
        dry_run=args.dry_run, push_dialer=args.push_dialer)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"Mode: providers {settings.env('GTM_PROVIDERS', 'mock_cognism,mock_lusha')}, "
          f"crm {settings.env('GTM_CRM', 'mock')}, dialer {settings.env('GTM_DIALER', 'mock')}")
    print(f"Run {res['run_id']}{' (dry run, nothing written)' if res['dry_run'] else ''}: "
          f"{res['sourced']} sourced, {res['filtered_out']} outside ICP hard filters")
    for r in res["results"]:
        line = f"  {r['tier']} {r['score']:>5}  {r['name']:<34} {r['outcome']}"
        if r.get("contacts"):
            line += ": " + ", ".join(f"{c['name']} via {c['phone_source']}" for c in r["contacts"])
        if r.get("would_reveal"):
            line += ": " + "; ".join(r["would_reveal"])
        if r.get("dropped"):
            line += "  (dropped: " + ", ".join(f"{d['name']} {d['why']}" for d in r["dropped"]) + ")"
        print(line)
    print(f"Credits spent: {res['credits_spent']}")
    for name, s in res["provider_stats"].items():
        print(f"  {name}: {s['reveals']} reveals, {s['valid_phone']} valid phone, "
              f"{s['bad_phone']} bad phone, {s['no_phone']} no phone")
    return 0


def cmd_dialer(args) -> int:
    res = dialer_sync.run(Ledger(settings.state_dir() / "ledger.jsonl"), settings.build_dialer(),
                          _routing(args), args.dry_run)
    print(f"Loaded {len(res['pushed'])} contacts into the dialer, {res['skipped']} skipped"
          + (" (dry run)" if res["dry_run"] else ""))
    for n in res["pushed"]:
        print(f"  {n}")
    return 0


def cmd_report(args) -> int:
    print(json.dumps(report.run(Ledger(settings.state_dir() / "ledger.jsonl")), indent=2))
    return 0


def cmd_reset(args) -> int:
    shutil.rmtree(settings.state_dir(), ignore_errors=True)
    print("Local state cleared. The mock CRM reseeds on the next run.")
    return 0


def main(argv: list[str] | None = None) -> int:
    settings.load_env()
    ap = argparse.ArgumentParser(prog="gtm", description="GTM prospecting engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, source=True):
        if source:
            p.add_argument("--source", default=str(ROOT / "fixtures" / "companies.json"),
                           help="account list: JSON or CSV")
            p.add_argument("--icp", default=str(ROOT / "config" / "icp.yaml"))
        p.add_argument("--routing", default=str(ROOT / "config" / "routing.yaml"))

    p = sub.add_parser("lookup", help="pull up an account in the CRM by domain or name")
    p.add_argument("query")
    p.set_defaults(fn=cmd_lookup)

    p = sub.add_parser("list", help="score and rank accounts by ICP fit and signals")
    common(p)
    p.add_argument("--out", default=str(ROOT / "out" / "ranked_list.csv"))
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("prospect", help="full run: dedupe, reveal, write to CRM, create SDR tasks")
    common(p)
    p.add_argument("--suppression", default=str(ROOT / "config" / "suppression.txt"))
    p.add_argument("--max-credits", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--push-dialer", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_prospect)

    p = sub.add_parser("dialer-sync", help="load callable contacts from earlier runs into the dialer")
    common(p, source=False)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_dialer)

    p = sub.add_parser("report", help="funnel report from the run ledger")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("reset", help="clear local state (mock CRM, ledger, dialer file)")
    p.set_defaults(fn=cmd_reset)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
