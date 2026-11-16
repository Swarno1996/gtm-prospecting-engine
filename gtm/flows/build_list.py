"""Flow 2: turn an account source into a ranked, tiered list using ICP fit and signals."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from gtm import icp as icp_mod
from gtm.models import Company, ScoredCompany


def run(companies: list[Company], icp: dict, today: date | None = None) -> list[ScoredCompany]:
    return icp_mod.rank(companies, icp, today)


def write_csv(scored: list[ScoredCompany], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "tier", "score", "fit", "signal", "domain", "name", "industry",
                    "employees", "country", "top_signal", "why"])
        for i, s in enumerate(scored, 1):
            c = s.company
            w.writerow([i, s.tier, s.total, s.fit, s.signal, c.domain, c.name, c.industry,
                        c.employees, c.country, s.top_signal, "; ".join(s.reasons)])
