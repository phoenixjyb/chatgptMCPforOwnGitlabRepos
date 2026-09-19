from __future__ import annotations

import re
from dataclasses import dataclass

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GitLab PAT", re.compile(r"\bglpat-[A-Za-z0-9_-]{8,}\b")),
    (
        "GitHub token",
        re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{10,}\b"),
    ),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{25,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "Private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    (
        "JWT",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "Credential-bearing URL",
        re.compile(r"https?://[^/\s:@]+:[^@\s/]+@"),
    ),
]

_SAFE_PLACEHOLDER_FRAGMENTS = (
    "REPLACE_ME",
    "YOUR_TOKEN",
    "YOUR_KEY",
    "EXAMPLE",
    "xxxxxxxx",
    "<token>",
    "<key>",
)


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    path: str | None
    line: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
        }


def _is_safe_placeholder(text: str) -> bool:
    upper = text.upper()
    return any(fragment.upper() in upper for fragment in _SAFE_PLACEHOLDER_FRAGMENTS)


def scan_added_diff_for_secrets(diff_text: str) -> list[dict[str, object]]:
    """Scan only added lines in a unified diff for high-signal secret formats."""

    findings: list[SecretFinding] = []
    current_path: str | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            value = raw_line[4:].strip()
            if value == "/dev/null":
                current_path = None
            elif value.startswith("b/"):
                current_path = value[2:]
            else:
                current_path = value
            continue

        if not raw_line.startswith("+") or raw_line.startswith("+++"):
            continue

        added = raw_line[1:]
        if _is_safe_placeholder(added):
            continue

        for kind, pattern in _SECRET_PATTERNS:
            if pattern.search(added):
                preview = added.strip()
                if len(preview) > 180:
                    preview = preview[:177] + "..."
                findings.append(
                    SecretFinding(
                        kind=kind,
                        path=current_path,
                        line=preview,
                    )
                )

    return [finding.to_dict() for finding in findings]


_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_GENERIC_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)"
    r"\s*[:=]\s*([^\s'\"]+)",
    re.IGNORECASE,
)


def redact_sensitive_text(text: str) -> tuple[str, list[str]]:
    """Redact high-signal credentials and obvious secret assignments from logs."""

    cleaned = _ANSI_ESCAPE_RE.sub("", text)
    redacted_kinds: list[str] = []

    # Record high-signal formats before generic NAME=value redaction can hide them.
    for kind, pattern in _SECRET_PATTERNS:
        if pattern.search(cleaned):
            redacted_kinds.append(kind)

    def _replace_assignment(match: re.Match[str]) -> str:
        name = match.group(1)
        redacted_kinds.append(f"assignment:{name}")
        return f"{name}=[REDACTED]"

    cleaned = _GENERIC_SECRET_ASSIGNMENT_RE.sub(_replace_assignment, cleaned)

    # Redact high-signal credentials that are not part of an obvious assignment.
    for kind, pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(f"[REDACTED:{kind}]", cleaned)

    unique: list[str] = []
    seen: set[str] = set()
    for item in redacted_kinds:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return cleaned, unique
