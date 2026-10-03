"""Thin Groq wrapper. Every call degrades gracefully to None if no key / error,
so the agents can fall back to deterministic logic."""
import json
import re

from .config import GROQ_API_KEY, LLM_MODEL

_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:  # pragma: no cover
        print("Groq init error:", e)
        _client = None


def available() -> bool:
    return _client is not None


def complete(system: str, user: str, max_tokens: int = 500) -> str | None:
    if not _client:
        return None
    try:
        resp = _client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("LLM error:", e)
        return None


def complete_json(system: str, user: str) -> dict | None:
    text = complete(system + "\nReturn ONLY a JSON object, no prose, no code fences.", user, 400)
    if not text:
        return None
    try:
        return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
    except Exception:
        return None
