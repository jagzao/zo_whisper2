"""Best-effort secret redaction before content leaves the machine.

This is regex-based pattern matching, not a DLP system: it catches
well-known credential shapes (API keys, tokens, connection strings) but
cannot detect secrets with no recognizable format, nor anything embedded
in a screenshot's pixels rather than its accompanying text. See
`PRIVACY.md` for the documented limitations — treat this as defense in
depth on top of `ALLOW_EXTERNAL_LLM`/`data_classification`, not a
guarantee.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.=]{10,}")),
    ("connection_string", re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/@]+:[^\s@]+@[^\s]+")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9\-_/+=]{8,}['\"]?"
        ),
    ),
]


def redact_secrets(text: str) -> str:
    """Replaces recognizable secret patterns with `[REDACTED:<kind>]`."""
    if not text:
        return text
    redacted = text
    for name, pattern in _PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{name}]", redacted)
    return redacted
