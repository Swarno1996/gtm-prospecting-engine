from __future__ import annotations

import argparse
import json
import shutil
import sys

from gtm import icp as icp_mod
from gtm import service, settings, sources
from gtm.flows import build_list

ROOT = settings.ROOT


def cmd_lookup(args) -> int:
    res = service.lookup(args.query)
    if not res["found"]:
        print(f"Not in CRM: {args.query}")
        return 0
    c = res["company"]
    print(f"{c['name']}  ({c['domain']})  id {c['id']}")
    print(f"  stage {c.get('lifecyclestage') or 'none'}, open deals {c.get('open_deals', 0)}, owner {c.get('owner_id') or 'unassigned'}")
    print(f"  contacts: {len(res['contacts'])}")
    for ct in res["contacts"]:
        print(f"    [{ct['id']}] {ct.get('firstname', '')} {ct.get('lastname', '')}, {ct.get('jobtitle', '')}  {ct.get('email', '')}  {ct.get('phone', '')}")
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
    res = service.prospect_run(source=args.source, icp=args.icp, routing=args.routing,
                               suppression_path=args.suppression, max_credits=args.max_credits,
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
    res = service.dialer(args.dry_run, args.routing)
    print(f"Loaded {len(res['pushed'])} contacts into the dialer, {res['skipped']} skipped"
          + (" (dry run)" if res["dry_run"] else ""))
    for n in res["pushed"]:
        print(f"  {n}")
    return 0


def cmd_report(args) -> int:
    print(json.dumps(service.funnel(), indent=2))
    return 0


def cmd_outcome(args) -> int:
    payload = {"crm_contact_id": args.contact_id, "outcome": args.outcome, "notes": args.notes,
               "callback_at": args.callback_at, "call_id": args.call_id}
    res = service.outcome({k: v for k, v in payload.items() if v}, args.routing)
    print(f"{res['outcome']} for {res['contact_id']} (attempt {res.get('attempt', '?')})"
          + (" duplicate, ignored" if res["duplicate"] else ""))
    for a in res["actions"]:
        print(f"  {a}")
    return 0


def cmd_brief(args) -> int:
    res = service.brief(args.contact_id)
    print(res["brief"])
    print(f"\n(written by {res['written_by']})")
    return 0


def cmd_serve(args) -> int:
    from gtm.server import serve

    serve(args.host, args.port)
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

    p = sub.add_parser("call-outcome", help="write a call result back to the CRM")
    common(p, source=False)
    p.add_argument("contact_id")
    p.add_argument("outcome", choices=sorted(__import__("gtm.flows.call_outcome", fromlist=["x"]).OUTCOMES))
    p.add_argument("--notes", default="")
    p.add_argument("--callback-at", default="")
    p.add_argument("--call-id", default="")
    p.set_defaults(fn=cmd_outcome)

    p = sub.add_parser("call-brief", help="one screen call prep for a CRM contact")
    p.add_argument("contact_id")
    p.set_defaults(fn=cmd_brief)

    p = sub.add_parser("serve", help="HTTP server for n8n and Langdock")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=8787)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("report", help="funnel report from the run ledger")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("reset", help="clear local state (mock CRM, ledger, dialer file)")
    p.set_defaults(fn=cmd_reset)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (KeyError, ValueError) as e:
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
