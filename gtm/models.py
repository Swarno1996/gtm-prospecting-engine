from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Signal:
    type: str
    date: str  # ISO date the signal was observed
    detail: str = ""


@dataclass
class Company:
    domain: str
    name: str
    industry: str = ""
    employees: int = 0
    country: str = ""
    city: str = ""
    signals: list[Signal] = field(default_factory=list)
    source: str = ""


@dataclass
class Person:
    """A person at a company before reveal: no email, no phone, no credit spent."""

    first_name: str
    last_name: str
    title: str
    company_domain: str
    provider: str = ""
    ref: str = ""  # provider side id used for the reveal call

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.company_domain.lower(), self.first_name.lower(), self.last_name.lower())


@dataclass
class Contact:
    first_name: str
    last_name: str
    title: str
    company_domain: str
    email: str = ""
    phone: str = ""
    phone_type: str = ""  # mobile | landline | unknown
    email_source: str = ""
    phone_source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoredCompany:
    company: Company
    fit: float
    signal: float
    total: float
    tier: str
    reasons: list[str]
    top_signal: str = ""
