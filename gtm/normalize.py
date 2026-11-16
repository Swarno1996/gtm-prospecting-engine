"""Normalization used for dedupe: domains, company names, phone numbers."""
from __future__ import annotations

import re

LEGAL_SUFFIXES = {
    "gmbh", "ag", "se", "kg", "kgaa", "ohg", "ug", "mbh", "co", "ltd", "limited", "inc",
    "llc", "plc", "bv", "nv", "sa", "sarl", "sas", "srl", "spa", "ab", "as", "oy", "group",
    "holding", "holdings",
}


def domain(value: str) -> str:
    v = (value or "").strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/")[0].split("?")[0].split(":")[0]
    if "@" in v:
        v = v.split("@")[-1]
    return re.sub(r"^www\.", "", v).strip(".")


def company_name(value: str) -> str:
    v = (value or "").lower().replace("&", " ")
    v = re.sub(r"[^\w\s]", " ", v)
    tokens = [t for t in v.split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


# Country calling codes with (national number min length, max length, mobile prefixes).
PHONE_RULES = {
    "49": (7, 11, ("15", "16", "17")),
    "43": (7, 12, ("65", "66", "67", "68", "69")),
    "41": (9, 9, ("74", "75", "76", "77", "78", "79")),
}
DEFAULT_CC = {"DE": "49", "AT": "43", "CH": "41"}


def phone(value: str, country: str = "DE") -> tuple[str, str]:
    """Return (E.164 number, type) or ("", "invalid").

    This is a format check. It proves the number is well formed, not that the
    line is connected or belongs to the person.
    """
    raw = (value or "").strip()
    if not raw:
        return "", "invalid"
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        cc = DEFAULT_CC.get(country.upper())
        if not cc or not digits.startswith("0"):
            return "", "invalid"
        digits = "+" + cc + digits[1:]
    body = digits[1:]
    if not body.isdigit():
        return "", "invalid"
    for cc, (lo, hi, mobile) in PHONE_RULES.items():
        if body.startswith(cc):
            national = body[len(cc):].lstrip("0")
            if not lo <= len(national) <= hi:
                return "", "invalid"
            if len(set(national)) == 1:
                return "", "invalid"
            kind = "mobile" if national.startswith(mobile) else "landline"
            return "+" + cc + national, kind
    if 8 <= len(body) <= 15:
        return "+" + body, "unknown"
    return "", "invalid"


def email_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", (value or "").strip().lower()))
