"""Check the Anthropic key in .env without printing it (final spec 6.9).

Prints the chat mode, whether the key is valid, the model id, then makes one call.
Run: python scripts/dev/check_llm.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import llm  # noqa: E402


def main() -> int:
    key_ok = llm.key_is_valid(llm.get_api_key())
    model = llm.get_model()
    print(f"chat mode: {llm.get_chat_mode()}")
    print(f"key valid: {'yes' if key_ok else 'no'}")
    print(f"model:     {model}")
    if not key_ok:
        print("No valid key in .env. Chat will use the rule parser in auto mode.")
        return 1
    try:
        llm.complete("Reply with the single word OK.", "ping", max_tokens=10)
    except llm.LLMUnavailable as e:
        print(f"FAILED: {e.reason}. Chat will use the rule parser in auto mode.")
        return 1
    print(f"OK: {model} responded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
