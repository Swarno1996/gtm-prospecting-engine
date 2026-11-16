"""Flow 1: pull up what the CRM already knows about an account."""
from __future__ import annotations


def run(crm, query: str) -> dict:
    is_domain = "." in query and " " not in query
    company = crm.find_company(query if is_domain else "", "" if is_domain else query)
    if not company:
        return {"found": False, "query": query}
    return {"found": True, "company": company,
            "contacts": crm.company_contacts(company["id"]),
            "open_tasks": crm.open_tasks(company["id"])}
