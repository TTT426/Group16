"""Pull a JSON object out of a model reply.

We ask models to answer in JSON instead of relying on provider-specific
structured-output features, so the same prompt works for CLI and API providers.
Replies may still wrap the JSON in a ```json fence or add a sentence around it.
"""

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json_object(text: str) -> dict:
    """Return the first JSON object found in `text`, or raise ValueError."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        start = candidate.find("{")
        while start != -1:
            try:
                value, _ = json.JSONDecoder().raw_decode(candidate[start:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
            start = candidate.find("{", start + 1)
    raise ValueError("No JSON object found in model reply.")
