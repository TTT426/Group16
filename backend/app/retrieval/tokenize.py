"""Tokenizer for keyword search over mixed Chinese / English text.

English / code: lowercase word tokens (also split on "_").
Chinese: single characters plus character bigrams, so "付款失敗" matches
"付款", "失敗" and the exact phrase without needing a word segmenter.
"""

import re

_TOKEN = re.compile(r"[a-z0-9_]+|[㐀-䶿一-鿿豈-﫿]+")
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for run in _TOKEN.findall((text or "").lower()):
        if _CJK.match(run):
            tokens.extend(run)
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        else:
            tokens.append(run)
            if "_" in run:
                tokens.extend(part for part in run.split("_") if part)
    return tokens
