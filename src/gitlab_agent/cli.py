from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import AgentSettings
from .runner import CommandRunner
from .workspace import WorkspaceManager


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _read_text_arg(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitlab-agent",
        description=(
            "Local worktree/build/commit/MR engine for self-hosted GitLab. "
            "Designed for Codex or direct terminal use; no OpenAI model API calls."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="Create an isolated worktree")
    p.add_argument("project", help="GitLab path_with_namespace, e.g. team/project")
    p.add_argument("--base-ref", default=None)
    p.add_argument("--task", default="task")

    p = sub.add_parser("list", help="List managed workspaces")

    p = sub.add_parser("status", help="Show workspace Git status")
    p.add_argument("workspace_id")

    p = sub.add_parser("files", help="List files in a workspace")
    p.add_argument("workspace_id")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--max-entries", type=int, default=500)

    p = sub.add_parser("read", help="Read a UTF-8 file from a workspace")
    p.add_argument("workspace_id")
    p.add_argument("path")

    p = sub.add_parser("write", help="Replace/create a UTF-8 file in a workspace")
    p.add_argument("workspace_id")
    p.add_argument("path")
    p.add_argument(
        "--content-file",
        default="-",
        help="File containing complete new content; '-' reads stdin",
    )

    p = sub.add_parser("apply-patch", help="Apply a unified diff with git apply")
    p.add_argument("workspace_id")
    p.add_argument(
        "--patch-file",
        default="-",
        help="Patch file; '-' reads stdin",
    )

    p = sub.add_parser("diff", help="Show committed/staged/unstaged diff from base")
    p.add_argument("workspace_id")

    p = sub.add_parser("run", help="Run an allowlisted build/test command")
    p.add_argument("workspace_id")
    p.add_argument("--timeout", type=int, default=None)
    p.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="Command after '--', e.g. gitlab-agent run ID -- uv run pytest",
    )

    p = sub.add_parser("commit", help="Stage all workspace changes and commit")
    p.add_argument("workspace_id")
    p.add_argument("-m", "--message", required=True)

    p = sub.add_parser("push", help="Push the generated feature branch")
    p.add_argument("workspace_id")

    p = sub.add_parser(
        "push-mr",
        help="First-push feature branch and ask GitLab to create an MR",
    )
    p.add_argument("workspace_id")
    p.add_argument("--target", required=True)
    p.add_argument("--title", required=True)
    p.add_argument(
        "--description-file",
        default=None,
        help="Optional MR description file; '-' reads stdin",
    )

    p = sub.add_parser("cleanup", help="Remove a managed worktree")
    p.add_argument("workspace_id")
    p.add_argument("--force", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        settings = AgentSettings.load()
        manager = WorkspaceManager(settings)
        runner = CommandRunner(settings, manager)

        if args.command == "create":
            result = manager.create_workspace(
                args.project,
                base_ref=args.base_ref,
                task_slug=args.task,
            )
        elif args.command == "list":
            result = [manager.status(state.workspace_id) for state in manager.list_states()]
        elif args.command == "status":
            result = manager.status(args.workspace_id)
        elif args.command == "files":
            result = manager.list_files(
                args.workspace_id,
                args.path,
                recursive=args.recursive,
                max_entries=args.max_entries,
            )
        elif args.command == "read":
            result = manager.read_file(args.workspace_id, args.path)
        elif args.command == "write":
            result = manager.write_file(
                args.workspace_id,
                args.path,
                _read_text_arg(args.content_file),
            )
        elif args.command == "apply-patch":
            result = manager.apply_patch(
                args.workspace_id,
                _read_text_arg(args.patch_file),
            )
        elif args.command == "diff":
            result = manager.diff(args.workspace_id)
        elif args.command == "run":
            command_argv = list(args.argv)
            if command_argv and command_argv[0] == "--":
                command_argv = command_argv[1:]
            result = runner.run(
                args.workspace_id,
                command_argv,
                timeout_seconds=args.timeout,
            )
        elif args.command == "commit":
            result = manager.commit(args.workspace_id, args.message)
        elif args.command == "push":
            result = manager.push(args.workspace_id)
        elif args.command == "push-mr":
            description = (
                _read_text_arg(args.description_file)
                if args.description_file is not None
                else ""
            )
            result = manager.push_and_create_mr(
                args.workspace_id,
                target_branch=args.target,
                title=args.title,
                description=description,
            )
        elif args.command == "cleanup":
            result = manager.cleanup(args.workspace_id, force=args.force)
        else:
            parser.error(f"Unhandled command {args.command}")
            return 2

        _print(result)
        return 0
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        _print({"ok": False, "error": str(exc), "type": type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
