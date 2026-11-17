"""LLM access through Langdock.

Langdock exposes provider compatible completion endpoints behind one key.
This client uses the OpenAI compatible one:
    POST https://api.langdock.com/openai/{region}/v1/chat/completions
Set LANGDOCK_API_KEY to enable it. LANGDOCK_REGION defaults to eu,
LANGDOCK_MODEL to gpt-4o-mini. For a dedicated deployment set
LANGDOCK_BASE_URL to <deployment-url>/api/public.

Without a key, callers fall back to deterministic templates, so every flow
still runs and tests never depend on a model.
"""
from __future__ import annotations

from gtm import http
from gtm.settings import env


def enabled() -> bool:
    return bool(env("LANGDOCK_API_KEY"))


def complete(system: str, user: str, max_tokens: int = 500) -> str:
    base = env("LANGDOCK_BASE_URL", "https://api.langdock.com").rstrip("/")
    url = f"{base}/openai/{env('LANGDOCK_REGION', 'eu')}/v1/chat/completions"
    res = http.request("POST", url, headers={"Authorization": f"Bearer {env('LANGDOCK_API_KEY')}"},
                       body={"model": env("LANGDOCK_MODEL", "gpt-4o-mini"), "max_tokens": max_tokens,
                             "temperature": 0.2,
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}]}, timeout=60)
    return res["choices"][0]["message"]["content"].strip()
