"""Détection et masquage de secrets avant tout appel distant."""
from __future__ import annotations

import re

from ..models import AgentProfile

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]+"), "[REDACTED_API_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"jev_[A-Za-z0-9_-]{8,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-+=/]+"), "[REDACTED_BEARER]"),
    (re.compile(r"(?i)(password|passwd|secret)\s*[:=]\s*\S+"), r"\1=[REDACTED_PASSWORD]"),
)


def redact_text(text: str) -> str:
    """Remplace les secrets connus par des marqueurs stables."""
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_agent(agent: AgentProfile) -> AgentProfile:
    """Retourne une copie dont la description a été masquée."""
    redacted = redact_text(agent.description)
    if redacted == agent.description:
        return agent
    return agent.with_description(redacted)
