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

@dataclass(frozen=True)
class SecretFinding:
    kind: str
    path: str | None
    line: str
    commit_sha: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": redact_sensitive_text(self.path)[0] if self.path else None,
            "line": self.line,
            "commit_sha": self.commit_sha,
        }


def scan_added_diff_for_secrets(diff_text: str) -> list[dict[str, object]]:
    """Scan added hunk lines; placeholder words never exempt credential matches."""
    findings: list[SecretFinding] = []
    current_path: str | None = None
    commit_sha: str | None = None
    in_hunk = False

    # Split on LF, not arbitrary Unicode line separators inside repository text.
    for raw_line in diff_text.split("\n"):
        if re.fullmatch(r"commit [0-9a-f]{40}(?:[0-9a-f]{24})?", raw_line):
            commit_sha = raw_line[7:]
            current_path = None
            in_hunk = False
            continue
        if raw_line.startswith("diff --git "):
            current_path = None
            in_hunk = False
            continue
        if raw_line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk and raw_line.startswith("+++ "):
            value = raw_line[4:].strip()
            current_path = value[2:] if value.startswith("b/") else value
            if value == "/dev/null":
                current_path = None
            continue
        if not in_hunk or not raw_line.startswith("+"):
            continue

        added = _ANSI_ESCAPE_RE.sub("", raw_line[1:])
        for kind, pattern in _SECRET_PATTERNS:
            if pattern.search(added):
                # Omit the entire offending source line: private-key continuation
                # lines and other unknown secret formats must not enter a preview.
                findings.append(SecretFinding(
                    kind=kind, path=current_path,
                    line=f"[REDACTED:{kind}]", commit_sha=commit_sha,
                ))

    return [finding.to_dict() for finding in findings]


_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    r"[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|\Z)"
)
_GENERIC_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)"
    r"[\"']?\s*[:=]\s*(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s'\"]+)",
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

    cleaned = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED:Private key block]", cleaned)

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
