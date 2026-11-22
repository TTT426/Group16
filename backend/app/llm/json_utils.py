"""Pull a JSON object out of a model reply, and prepare JSON schemas for strict structured output.

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


def strict_schema(schema: dict) -> dict:
    """A copy of `schema` in the strict form API structured outputs require.

    Every object gets `additionalProperties: false` and lists all its properties as required.
    """
    if not isinstance(schema, dict):
        return schema
    out = {key: (strict_schema(value) if key == "items" else value) for key, value in schema.items()}
    if schema.get("type") == "object":
        props = {key: strict_schema(value) for key, value in schema.get("properties", {}).items()}
        out.update(properties=props, required=list(props), additionalProperties=False)
    return out
