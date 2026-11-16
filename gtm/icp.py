"""ICP fit and signal scoring. All weights live in config/icp.yaml."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from gtm.models import Company, Person, ScoredCompany


def load(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def score(company: Company, icp: dict, today: date | None = None) -> ScoredCompany | None:
    """Return a ScoredCompany, or None when a hard filter excludes the company."""
    today = today or date.today()
    hard = icp["hard_filters"]
    if hard.get("countries") and company.country not in hard["countries"]:
        return None
    if company.employees < hard.get("min_employees", 0):
        return None
    if hard.get("max_employees") and company.employees > hard["max_employees"]:
        return None
    if company.industry in hard.get("excluded_industries", []):
        return None

    reasons: list[str] = []
    fit = 0.0
    ind = icp["fit"]["industries"].get(company.industry, 0)
    if ind:
        fit += ind
        reasons.append(f"industry {company.industry} (+{ind})")
    for band in icp["fit"]["size_bands"]:
        if band["min"] <= company.employees <= band.get("max", 10**9):
            fit += band["points"]
            reasons.append(f"{company.employees} employees (+{band['points']})")
            break
    geo = icp["fit"].get("countries", {}).get(company.country, 0)
    if geo:
        fit += geo
        reasons.append(f"country {company.country} (+{geo})")
    fit = min(fit, 100.0)

    sig_cfg = icp["signals"]
    half_life = sig_cfg.get("half_life_days", 45)
    sig_total, top, top_pts = 0.0, "", 0.0
    for s in company.signals:
        weight = sig_cfg["weights"].get(s.type, 0)
        if not weight:
            continue
        age = max((today - date.fromisoformat(s.date)).days, 0)
        if age > sig_cfg.get("max_age_days", 180):
            continue
        pts = weight * 0.5 ** (age / half_life)
        sig_total += pts
        reasons.append(f"signal {s.type}, {age}d old (+{pts:.0f})")
        if pts > top_pts:
            top, top_pts = (s.detail or s.type), pts
    sig_total = min(sig_total, 100.0)

    w = icp["weights"]
    total = round(w["fit"] * fit + w["signal"] * sig_total, 1)
    tier = "C"
    for name in ("A", "B"):
        if total >= icp["tiers"][name]:
            tier = name
            break
    return ScoredCompany(company, round(fit, 1), round(sig_total, 1), total, tier, reasons, top)


def rank(companies: list[Company], icp: dict, today: date | None = None) -> list[ScoredCompany]:
    scored = [s for s in (score(c, icp, today) for c in companies) if s]
    return sorted(scored, key=lambda s: (-s.total, s.company.domain))


def persona_rank(title: str, icp: dict) -> int | None:
    """Lower is better. None means the title is not a persona we call."""
    t = (title or "").lower()
    persona = icp["persona"]
    if any(x in t for x in persona.get("exclude", [])):
        return None
    for i, group in enumerate(persona["include"]):
        if any(k in t for k in group):
            return i
    return None


def pick_people(people: list[Person], icp: dict) -> list[Person]:
    ranked = [(persona_rank(p.title, icp), p) for p in people]
    ranked = [(r, p) for r, p in ranked if r is not None]
    ranked.sort(key=lambda x: (x[0], x[1].last_name))
    return [p for _, p in ranked][: icp["persona"].get("max_per_company", 2)]
