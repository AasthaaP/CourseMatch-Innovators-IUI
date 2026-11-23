"""The single place that reads the Anthropic key and calls the API. Final spec Section 6.1.

The key, model and chat mode are read fresh on every call (process environment first, then ROOT/.env), so
pasting a key into .env switches chat to Claude on the next message without a restart. Never prints the key.
"""
import sys
from pathlib import Path

import os

from dotenv import dotenv_values

PLACEHOLDER = "sk-ant-REPLACE_ME"
DEFAULT_MODEL = "claude-sonnet-5-5"
TIMEOUT_S = 10.0
MAX_RETRIES = 1
CHAT_MODES = ("auto", "rules", "claude")

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"  # tests point this at a temporary file

REASONS = ("no_api_key", "auth_error", "model_not_found", "rate_limited", "timeout", "api_error")


class LLMUnavailable(Exception):
    def __init__(self, reason: str, detail: str = ""):
        # reason is one of REASONS
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _dotenv() -> dict:
    try:
        return {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}
    except OSError:
        return {}


def _setting(name: str) -> str:
    """Process environment first, else .env read fresh, else ''."""
    value = os.environ.get(name, "").strip()
    return value or _dotenv().get(name, "").strip()


def key_is_valid(key: str) -> bool:
    return bool(key) and key.startswith("sk-ant-") and "REPLACE_ME" not in key


def get_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key_is_valid(env_key):
        return env_key
    return _dotenv().get("ANTHROPIC_API_KEY", "").strip()


def get_model() -> str:
    return _setting("COURSEMATCH_LLM_MODEL") or DEFAULT_MODEL


def get_chat_mode() -> str:
    mode = _setting("COURSEMATCH_CHAT").lower()
    return mode if mode in CHAT_MODES else "auto"


_clients: dict = {}


def _client(key: str):
    import anthropic

    cache_key = (key, anthropic.Anthropic)
    if cache_key not in _clients:
        _clients[cache_key] = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_S, max_retries=MAX_RETRIES)
    return _clients[cache_key]


def _reason(exc: Exception) -> str:
    import anthropic

    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "auth_error"
    if isinstance(exc, anthropic.NotFoundError):
        return "model_not_found"
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limited"
    if isinstance(exc, anthropic.APITimeoutError):
        return "timeout"
    return "api_error"


def complete(system: str, user: str, max_tokens: int = 300) -> str:
    key = get_api_key()
    if not key_is_valid(key):
        raise LLMUnavailable("no_api_key")
    try:
        resp = _client(key).messages.create(
            model=get_model(), max_tokens=max_tokens, temperature=0, system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:  # noqa: BLE001
        reason = _reason(e)
        print(f"[llm] {reason}: {type(e).__name__}", file=sys.stderr)
        raise LLMUnavailable(reason, type(e).__name__) from None
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
