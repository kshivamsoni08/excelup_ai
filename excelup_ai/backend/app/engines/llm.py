"""Single LLM wrapper - provider switch Gemini → Groq → disabled.

Enhancement-only: the platform is 100% functional with no key present.
Every call has a 10s timeout and never raises into core flows.
"""
import json
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT_S = 10
GEMINI_MODEL = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"


def llm_enabled() -> bool:
    return bool(settings.gemini_api_key or settings.groq_api_key)


def provider_name() -> str:
    if settings.gemini_api_key:
        return "gemini"
    if settings.groq_api_key:
        return "groq"
    return "disabled"


def _gemini_call(prompt: str, system: Optional[str]) -> Optional[str]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={settings.gemini_api_key}"
    )
    contents = [{"parts": [{"text": prompt}]}]
    if system:
        contents = [{"parts": [{"text": system + "\n\n" + prompt}]}]
    body = {"contents": contents, "generationConfig": {"temperature": 0.2}}
    r = httpx.post(url, json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def _groq_call(prompt: str, system: Optional[str]) -> Optional[str]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1500,
        },
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def llm_text(prompt: str, system: Optional[str] = None) -> Optional[str]:
    """Return text or None on any failure. NEVER raises."""
    try:
        if settings.gemini_api_key:
            return _gemini_call(prompt, system)
        if settings.groq_api_key:
            return _groq_call(prompt, system)
    except Exception as exc:  # network, quota, parse - anything
        logger.warning("LLM call failed (%s): %s", provider_name(), exc)
    return None


def llm_json(prompt: str, system: Optional[str] = None):
    """Ask the LLM for JSON; returns parsed object or None on any failure."""
    text = llm_text(prompt, system)
    if text is None:
        return None
    # strip markdown fences if present
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    try:
        start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
        if start > 0:
            t = t[start:]
        return json.loads(t)
    except Exception:
        return None
