#!/usr/bin/env python3
"""Fail if tracked files or Git history contain likely credentials/private keys.

This is intentionally dependency-free so it can run in CI and on developer machines.
It detects high-signal credential formats, private-key blocks, credential-bearing URLs,
real-looking Secure MCP tunnel IDs, and developer-specific absolute home paths.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
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
    (
        "Real-looking Secure MCP tunnel ID",
        re.compile(r"\btunnel_[0-9a-f]{20,}\b", re.IGNORECASE),
    ),
    (
        "Developer-specific macOS home path",
        re.compile(r"/Users/(?!USERNAME\b|yourname\b|example\b)[A-Za-z0-9._-]+/"),
    ),
    (
        "Developer-specific Windows home path",
        re.compile(
            r"C:\\Users\\(?!USERNAME\\|yourname\\|example\\)[A-Za-z0-9._-]+\\",
            re.IGNORECASE,
        ),
    ),
]

TEXT_SUFFIX_ALLOWLIST = {
    ".md", ".py", ".toml", ".yml", ".yaml", ".json", ".sh", ".txt",
    ".cfg", ".ini", ".example", ".gitignore",
}
TEXT_FILENAMES = {".gitignore", ".env.example", "LICENSE"}


def run_git(*args: str) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: "
            + proc.stderr.decode("utf-8", errors="replace")
        )
    return proc.stdout


def is_text_candidate(path: Path) -> bool:
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_SUFFIX_ALLOWLIST


SAFE_EXAMPLE_VALUES = {
    "tunnel_0123456789abcdef0123456789abcdef",
}


def scan_text(label: str, text: str) -> list[str]:
    findings: list[str] = []
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if match.group(0) in SAFE_EXAMPLE_VALUES:
                continue
            line = text.count("\n", 0, match.start()) + 1
            preview = match.group(0)
            if len(preview) > 120:
                preview = preview[:117] + "..."
            findings.append(f"{label}:{line}: {name}: {preview}")
    return findings


def scan_worktree() -> list[str]:
    raw = run_git("ls-files", "-z")
    findings: list[str] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        path = Path(item.decode("utf-8", errors="strict"))
        if not is_text_candidate(path) or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        findings.extend(scan_text(str(path), text))
    return findings


def scan_history() -> list[str]:
    # Full-history patch scan catches secrets that were later deleted from HEAD.
    data = run_git(
        "log",
        "HEAD",
        "--full-history",
        "--no-ext-diff",
        "--no-color",
        "-p",
    )
    text = data.decode("utf-8", errors="replace")
    return scan_text("git-history", text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        action="store_true",
        help="also scan all available Git history patches",
    )
    args = parser.parse_args()

    findings = scan_worktree()
    if args.history:
        findings.extend(scan_history())

    if findings:
        print("Potential secrets/private deployment details detected:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\nIf this is a real credential, revoke/rotate it first, then remove it "
            "from Git history before sharing the repository.",
            file=sys.stderr,
        )
        return 1

    scope = "tracked files + full available Git history" if args.history else "tracked files"
    print(f"Secret scan passed: {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
