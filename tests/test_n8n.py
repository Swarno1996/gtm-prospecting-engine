"""Structural checks on the n8n exports, and execution of their Code nodes."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted((ROOT / "n8n").glob("*.json"))
TRIGGERS = {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.webhook", "n8n-nodes-base.errorTrigger"}


def test_files_match_generator(tmp_path):
    """The committed JSON is exactly what scripts/build_n8n.py produces."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_n8n", ROOT / "scripts" / "build_n8n.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for w in (mod.W1, mod.W2, mod.W3, mod.W4):
        on_disk = next(json.loads(f.read_text()) for f in FILES if json.loads(f.read_text())["name"] == w["name"])
        assert on_disk == json.loads(json.dumps(w))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_graph(path):
    wf = json.loads(path.read_text())
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names))
    assert len({n["id"] for n in wf["nodes"]}) == len(names)
    for src, outs in wf["connections"].items():
        assert src in names
        for branch in outs["main"]:
            for c in branch:
                assert c["node"] in names
    reached = {n["name"] for n in wf["nodes"] if n["type"] in TRIGGERS}
    assert reached, "workflow has no trigger"
    changed = True
    while changed:
        changed = False
        for src in list(reached):
            for branch in wf["connections"].get(src, {}).get("main", []):
                for c in branch:
                    if c["node"] not in reached:
                        reached.add(c["node"])
                        changed = True
    assert reached == set(names), f"unreachable: {set(names) - reached}"


def _code(file, node_name):
    wf = json.loads((ROOT / "n8n" / file).read_text())
    return next(n for n in wf["nodes"] if n["name"] == node_name)["parameters"]["jsCode"]


def _run_js(js, item):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    harness = ("const $input = { first: () => ({ json: %s }) };\n"
               "const out = (() => {\n%s\n})();\nconsole.log(JSON.stringify(out));") % (json.dumps(item), js)
    p = subprocess.run([node, "-e", harness], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_summary_code_flags_zero_contacts():
    js = _code("01_scheduled_prospecting.json", "Build summary")
    rc, out, _ = _run_js(js, {"run_id": "r1", "sourced": 10, "contacts_created": 0, "credits_spent": 0,
                              "dry_run": False, "outcomes": {}, "provider_stats": {}, "contacts": []})
    assert rc == 0 and json.loads(out)[0]["json"]["alert"] is True
    rc, out, _ = _run_js(js, {"run_id": "r2", "sourced": 10, "contacts_created": 3, "credits_spent": 5,
                              "dry_run": False, "outcomes": {"created_company": 2},
                              "provider_stats": {"cognism": {"reveals": 4, "valid_phone": 3, "bad_phone": 1}},
                              "contacts": [{"name": "A B", "phone_source": "cognism"}]})
    res = json.loads(out)[0]["json"]
    assert res["alert"] is False and "cognism: 4 reveals" in res["body"]


def test_dialfire_mapping_and_contract_guard():
    js = _code("02_dialfire_call_outcome.json", "Map Dialfire fields")
    rc, out, _ = _run_js(js, {"body": {"crm_contact_id": "ct-1", "$status": "nicht_erreicht", "$call_id": "9"}})
    assert rc == 0 and json.loads(out)[0]["json"]["outcome"] == "no_answer"
    rc, _, err = _run_js(js, {"body": {"crm_contact_id": "ct-1", "$status": "something_new"}})
    assert rc != 0 and "contract broken" in err


def test_digest_code():
    js = _code("03_daily_funnel_digest.json", "Format digest")
    rc, out, _ = _run_js(js, {"runs": 1, "companies_processed": 10, "contacts_created": 7, "dialer_loaded": 4,
                              "outcomes": {}, "phone_source": {}, "contacts_dropped": {"no_valid_phone": 1}})
    assert rc == 0 and "no_valid_phone: 1" in json.loads(out)[0]["json"]["body"]
