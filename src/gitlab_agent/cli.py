from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import AgentSettings
from .gitlab_api import GitLabAPI
from .runner import CommandRunner
from .workspace import WorkspaceManager


SUPPORTED_CODING_AGENTS = {
    "codex": "codex",
    "copilot": "copilot",
}


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _read_text_arg(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _agent_prompt(
    status: dict[str, object],
    goal: str = "",
    *,
    agent: str = "codex",
) -> str:
    workspace_id = str(status["workspace_id"])
    project = str(status["project"])
    worktree = str(status["worktree_path"])
    base_ref = str(status["base_ref"])
    branch = str(status["branch"])
    mr_url = status.get("merge_request_url")
    pushed = bool(status.get("pushed"))
    dirty = bool(status.get("dirty"))
    ahead = int(status.get("commits_ahead_of_base", 0))

    if dirty:
        next_step = (
            "Inspect current changes, run relevant tests, and review the final diff "
            "before committing."
        )
    elif pushed and mr_url:
        next_step = (
            "This workspace already has an MR. Make further required changes, test, "
            "commit, then run gitlab-agent push-update "
            + workspace_id
            + " to update the same MR branch."
        )
    elif ahead > 0:
        next_step = (
            "There are local commits not yet pushed. Review status/diff, then use "
            "push-mr for the first push if an MR is desired."
        )
    else:
        next_step = (
            "Follow the stated goal within this workspace. Inspect the relevant code first; "
            "only modify files if the goal requires a code change. Run relevant validation "
            "for any changes you make."
        )

    if agent not in SUPPORTED_CODING_AGENTS:
        raise ValueError(
            f"Unsupported coding agent {agent!r}. "
            f"Choose one of: {', '.join(sorted(SUPPORTED_CODING_AGENTS))}"
        )

    requested_goal = goal.strip() or "<describe the coding goal here>"
    return (
        f"You are the {agent} coding backend selected by ActualCoder.\n"
        "You are working in an isolated Git worktree managed by gitlab-agent.\n\n"
        f"Project: {project}\n"
        f"Base ref: {base_ref}\n"
        f"Feature branch: {branch}\n"
        f"Workspace ID: {workspace_id}\n"
        f"Worktree path: {worktree}\n"
        f"Existing MR: {mr_url or 'none'}\n"
        f"Goal: {requested_goal}\n\n"
        "Rules:\n"
        "- Work only inside the worktree above.\n"
        f"- Do not push directly to {base_ref}.\n"
        "- Do not force-push.\n"
        "- Do not introduce direct model API calls or model API keys into this project; use the selected CLI's existing signed-in session/entitlement.\n"
        "- Prefer gitlab-agent for status, tests, commit, push, and MR lifecycle.\n"
        "- Run relevant tests before remote writes.\n"
        f"- Review gitlab-agent diff {workspace_id} before committing/pushing.\n"
        f"- If an MR already exists, use gitlab-agent push-update {workspace_id} after new commits.\n\n"
        f"Next: {next_step}\n"
    )


def _handoff(
    manager: WorkspaceManager,
    workspace_id: str,
    goal: str = "",
    *,
    agent: str = "codex",
) -> dict[str, object]:
    if agent not in SUPPORTED_CODING_AGENTS:
        raise ValueError(
            f"Unsupported coding agent {agent!r}. "
            f"Choose one of: {', '.join(sorted(SUPPORTED_CODING_AGENTS))}"
        )

    status = manager.status(workspace_id)
    executable = SUPPORTED_CODING_AGENTS[agent]
    result: dict[str, object] = {
        "workspace": status,
        "worktree_path": status["worktree_path"],
        "agent": agent,
        "agent_command": f"cd {status['worktree_path']} && {executable}",
        "agent_prompt": _agent_prompt(status, goal, agent=agent),
    }

    # Alpha.1-alpha.3 compatibility for existing Codex integrations.
    if agent == "codex":
        result["codex_command"] = result["agent_command"]
        result["codex_prompt"] = result["agent_prompt"]

    return result


def _available_agents() -> dict[str, object]:
    agents: list[dict[str, object]] = []
    for name, executable in sorted(SUPPORTED_CODING_AGENTS.items()):
        resolved = shutil.which(executable)
        agents.append(
            {
                "agent": name,
                "executable": executable,
                "installed": resolved is not None,
                "path": resolved,
                "authentication_checked": False,
            }
        )
    return {
        "agents": agents,
        "note": (
            "Availability checks only whether the CLI executable is installed. "
            "It does not invoke the backend, verify authentication, or consume model quota."
        ),
    }


def _safe_config(settings: AgentSettings) -> dict[str, object]:
    return {
        "config_file": str(settings.config_file),
        "gitlab_base_url": settings.gitlab_base_url,
        "api_token_set": bool(settings.api_token),
        "api_verify_ssl": settings.api_verify_ssl,
        "api_trust_env": settings.api_trust_env,
        "git_token_set": bool(settings.git_token),
        "git_username": settings.git_username,
        "git_trust_env": settings.git_trust_env,
        "allowed_projects": sorted(settings.allowed_projects),
        "require_write_allowlist": settings.require_write_allowlist,
        "workspace_root": str(settings.workspace_root),
        "branch_prefix": settings.branch_prefix,
        "default_base_ref": settings.default_base_ref,
        "allowed_executables": sorted(settings.allowed_executables),
        "command_timeout_seconds": settings.command_timeout_seconds,
    }


def _build_parser(prog: str = "gitlab-agent") -> argparse.ArgumentParser:
    if prog in {"actual-coder", "codingagent"}:
        product_name = "ActualCoder" if prog == "actual-coder" else "CodingAgent (compatibility alias)"
        description = (
            f"{product_name}: agent-neutral coding orchestration for isolated GitLab "
            "worktrees. Supports Codex and GitHub Copilot CLI backends."
        )
    else:
        description = (
            "Low-level GitLab worktree/build/commit/MR controller used by ActualCoder."
        )

    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("config", help="Show effective non-secret configuration")
    sub.add_parser(
        "agents",
        help="Show supported coding backends and whether their CLI executable is installed",
    )

    p = sub.add_parser("create", help="Create an isolated worktree")
    p.add_argument("project", help="GitLab path_with_namespace, e.g. team/project")
    p.add_argument("--base-ref", default=None)
    p.add_argument("--task", default="task")

    p = sub.add_parser(
        "task",
        help="Create an isolated workspace and return a ready-to-use coding-agent handoff",
    )
    p.add_argument("project")
    p.add_argument("--base-ref", default=None)
    p.add_argument("--task", default="task")
    p.add_argument("--goal", default="")
    p.add_argument(
        "--agent",
        choices=sorted(SUPPORTED_CODING_AGENTS),
        default="codex",
        help="Coding backend to hand off to (default: codex)",
    )

    p = sub.add_parser(
        "checkout-branch",
        help="Reconstruct a managed workspace from an existing remote feature branch",
    )
    p.add_argument("project")
    p.add_argument("branch")
    p.add_argument("--base-ref", default=None)
    p.add_argument("--goal", default="")
    p.add_argument(
        "--agent",
        choices=sorted(SUPPORTED_CODING_AGENTS),
        default="codex",
    )

    p = sub.add_parser(
        "checkout-mr",
        help="Reconstruct a managed workspace from an existing GitLab Merge Request",
    )
    p.add_argument("project")
    p.add_argument("iid", type=int)
    p.add_argument("--goal", default="")
    p.add_argument(
        "--agent",
        choices=sorted(SUPPORTED_CODING_AGENTS),
        default="codex",
    )

    p = sub.add_parser("list", help="List managed workspaces")

    p = sub.add_parser("status", help="Show workspace Git status")
    p.add_argument("workspace_id")

    p = sub.add_parser(
        "resume",
        help="Return workspace status plus a coding-agent handoff prompt for an existing task",
    )
    p.add_argument("workspace_id")
    p.add_argument("--goal", default="")
    p.add_argument(
        "--agent",
        choices=sorted(SUPPORTED_CODING_AGENTS),
        default="codex",
    )

    p = sub.add_parser("path", help="Show the worktree path for a workspace")
    p.add_argument("workspace_id")
    p.add_argument("--plain", action="store_true")

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

    p = sub.add_parser(
        "diff",
        help="Show committed/staged/unstaged/untracked diff from base",
    )
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

    p = sub.add_parser(
        "push",
        help="Push the generated feature branch (also updates an existing MR branch)",
    )
    p.add_argument("workspace_id")

    p = sub.add_parser(
        "push-update",
        help="Push new commits to a branch/MR that was already created",
    )
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


def main(argv: list[str] | None = None, *, prog: str = "gitlab-agent") -> int:
    parser = _build_parser(prog=prog)
    args = parser.parse_args(argv)

    try:
        settings = AgentSettings.load()
        manager = WorkspaceManager(settings)
        runner = CommandRunner(settings, manager)
        gitlab_api = GitLabAPI(settings)

        if args.command == "config":
            result = _safe_config(settings)
        elif args.command == "agents":
            result = _available_agents()
        elif args.command == "create":
            result = manager.create_workspace(
                args.project,
                base_ref=args.base_ref,
                task_slug=args.task,
            )
        elif args.command == "task":
            created = manager.create_workspace(
                args.project,
                base_ref=args.base_ref,
                task_slug=args.task,
            )
            result = _handoff(
                manager,
                str(created["workspace_id"]),
                args.goal,
                agent=args.agent,
            )
        elif args.command == "checkout-branch":
            restored = manager.checkout_remote_branch(
                args.project,
                args.branch,
                base_ref=args.base_ref,
            )
            result = _handoff(
                manager,
                str(restored["workspace_id"]),
                args.goal,
                agent=args.agent,
            )
        elif args.command == "checkout-mr":
            mr = gitlab_api.merge_request(args.project, args.iid)
            source_project_id = mr.get("source_project_id")
            target_project_id = mr.get("target_project_id")
            if (
                source_project_id is not None
                and target_project_id is not None
                and source_project_id != target_project_id
            ):
                raise RuntimeError(
                    "checkout-mr currently supports same-project Merge Requests only"
                )
            source_branch = str(mr.get("source_branch") or "").strip()
            target_branch = str(mr.get("target_branch") or "").strip()
            web_url = str(mr.get("web_url") or "").strip() or None
            if not source_branch or not target_branch:
                raise RuntimeError("GitLab MR response is missing source/target branch")
            restored = manager.checkout_remote_branch(
                args.project,
                source_branch,
                base_ref=target_branch,
                merge_request_url=web_url,
            )
            handoff = _handoff(
                manager,
                str(restored["workspace_id"]),
                args.goal or f"Resume MR !{args.iid}: {mr.get('title', '')}",
                agent=args.agent,
            )
            result = {
                "merge_request": {
                    "iid": mr.get("iid"),
                    "title": mr.get("title"),
                    "state": mr.get("state"),
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "web_url": web_url,
                },
                **handoff,
            }
        elif args.command == "list":
            result = [manager.status(state.workspace_id) for state in manager.list_states()]
        elif args.command == "status":
            result = manager.status(args.workspace_id)
        elif args.command == "resume":
            result = _handoff(
                manager,
                args.workspace_id,
                args.goal,
                agent=args.agent,
            )
        elif args.command == "path":
            path = str(manager.status(args.workspace_id)["worktree_path"])
            if args.plain:
                print(path)
                return 0
            result = {"workspace_id": args.workspace_id, "worktree_path": path}
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
        elif args.command in {"push", "push-update"}:
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
