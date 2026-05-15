"""Secret Detector — prevents API keys and PII from being stored in shared memory.

Uses high-recall regex patterns to identify potential secrets.
Memories containing secrets are marked as SENSITIVE and can be
rejected or isolated.

v0.6.0 Production hardening (A).
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Pattern for common API keys and secrets
_SECRET_PATTERNS = [
    # Generic high-entropy strings
    (
        re.compile(
            r"(?i)(?:key|secret|token|password|auth|api|pwd)[ \t]*[:=][ \t]*['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?"
        ),
        "generic_secret",
    ),
    # OpenAI
    (re.compile(r"sk-[a-zA-Z0-9]{32,}"), "openai_api_key"),
    # AWS
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key"),
    (
        re.compile(r"(?i)aws_secret_access_key[ \t]*[:=][ \t]*[a-zA-Z0-9/+=]{40}"),
        "aws_secret_key",
    ),
    # GitHub (Fine-grained and classic)
    (re.compile(r"gh[pous]_[a-zA-Z0-9]{36,}"), "github_token"),
    # Stripe
    (re.compile(r"sk_live_[0-9a-zA-Z]{24,}"), "stripe_secret_key"),
    # Google Cloud
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "google_api_key"),
    # PII: Emails (basic)
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "pii_email"),
    # PII: Phone Numbers (basic)
    (
        re.compile(r"[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}"),
        "pii_phone",
    ),
]


def scan_secrets(text: str) -> List[Tuple[str, str]]:
    """Scan text for potential secrets. Returns list of (pattern_type, match_text)."""
    found = []
    for pattern, ptype in _SECRET_PATTERNS:
        matches = pattern.findall(text)
        for m in matches:
            found.append((ptype, m))
    return found


def is_sensitive(text: str) -> bool:
    """Return True if text contains any potential secrets or PII."""
    for pattern, _ in _SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def redact_secrets(text: str) -> str:
    """Replace discovered secrets with [REDACTED]."""
    redacted = text
    for pattern, _ in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda m: (
                m.group(0).replace(m.group(1), "[REDACTED]")
                if len(m.groups()) > 0
                else "[REDACTED]"
            ),
            redacted,
        )
    return redacted
