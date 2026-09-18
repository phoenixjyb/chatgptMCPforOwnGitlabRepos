from __future__ import annotations

from .cli import main as _gitlab_main


def main(argv: list[str] | None = None) -> int:
    """Entry point for the agent-neutral CodingAgent CLI."""
    return _gitlab_main(argv, prog="codingagent")


if __name__ == "__main__":
    raise SystemExit(main())
