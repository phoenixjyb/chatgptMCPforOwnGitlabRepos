from __future__ import annotations

import hashlib
import json

from typing import Any

from .config import AgentSettings
from .project_config import (
    PROJECT_CONFIG_FILENAME,
    PROJECT_CONFIG_MAX_BYTES,
    parse_project_config,
)
from .runner import CommandRunner
from .secret_scan import scan_added_diff_for_secrets
from .workspace import WorkspaceManager


_BUILTIN_PROTECTED_PATHS = {PROJECT_CONFIG_FILENAME}


def _path_is_protected(path: str, protected: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    for rule in protected:
        item = rule.replace("\\", "/").lstrip("./")
        if not item:
            continue
        if item.endswith("/"):
            if normalized.startswith(item):
                return True
        elif normalized == item or normalized.startswith(item + "/"):
            return True
    return False


def _load_base_contract(
    settings: AgentSettings,
    manager: WorkspaceManager,
    workspace_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    state = manager.get_state(workspace_id)
    remote = manager.read_remote_text_file(
        state.project,
        PROJECT_CONFIG_FILENAME,
        ref=state.base_sha,
        refresh_remote=False,
        max_bytes=PROJECT_CONFIG_MAX_BYTES,
    )
    parsed = parse_project_config(
        remote["content"] if remote["exists"] else None,
        settings=settings,
        source_ref=str(remote["ref"]),
        source_path=PROJECT_CONFIG_FILENAME,
    )
    if not parsed.valid:
        raise RuntimeError(
            "Workspace base .actualcoder.yaml is invalid: "
            + "; ".join(parsed.errors)
        )

    metadata = {
        "found": parsed.found,
        "source": {
            "ref": parsed.source_ref,
            "path": parsed.source_path,
        },
        "commit_sha": remote["commit_sha"],
        "warnings": parsed.warnings,
    }
    return dict(parsed.effective), metadata


def build_finish_plan(
    *,
    settings: AgentSettings,
    manager: WorkspaceManager,
    runner: CommandRunner,
    workspace_id: str,
    commit_message: str | None = None,
    mr_title: str | None = None,
    mr_description: str = "",
    allow_protected: bool = False,
    allow_secret_match: bool = False,
) -> dict[str, object]:
    """Validate a workspace and produce the controlled finish plan."""

    state = manager.get_state(workspace_id)
    project_context, project_metadata = _load_base_contract(
        settings,
        manager,
        workspace_id,
    )

    protected_rules = sorted(
        {
            *[
                str(item)
                for item in project_context.get("protected_paths", [])
                if isinstance(item, str)
            ],
            *_BUILTIN_PROTECTED_PATHS,
        }
    )

    validations: list[dict[str, object]] = []
    validation_blocked = False
    for raw_command in project_context.get("validation_commands", []):
        if not isinstance(raw_command, dict):
            continue
        argv = [
            str(item)
            for item in raw_command.get("argv", [])
            if isinstance(item, str)
        ]
        if not argv:
            continue

        timeout_raw = raw_command.get(
            "timeout_seconds",
            settings.command_timeout_seconds,
        )
        timeout = (
            int(timeout_raw)
            if isinstance(timeout_raw, int) and not isinstance(timeout_raw, bool)
            else settings.command_timeout_seconds
        )
        required = bool(raw_command.get("required", True))
        result = runner.run(
            workspace_id,
            argv,
            timeout_seconds=timeout,
        )
        passed = (
            not bool(result.get("timed_out"))
            and result.get("returncode") == 0
        )
        blocked = required and not passed
        validation_blocked = validation_blocked or blocked
        validations.append(
            {
                "name": str(raw_command.get("name") or argv[0]),
                "argv": argv,
                "required": required,
                "passed": passed,
                "blocking": blocked,
                "result": result,
            }
        )

    # Re-read the exact workspace state after validations. Validation commands may
    # create/update files, so the reviewed diff and safety scan must reflect the
    # post-validation state that could actually be committed/pushed.
    status = manager.status(workspace_id)
    changed_paths = manager.changed_paths(workspace_id)
    reviewability = manager.reviewability(workspace_id, changed_paths)

    if bool(reviewability.get("ok")):
        diff_result = manager.diff(workspace_id)
        security_diff = manager.security_diff(workspace_id)
        secret_findings = scan_added_diff_for_secrets(security_diff)
    else:
        security_diff = ""
        secret_findings = []
        diff_result = {
            "workspace_id": workspace_id,
            "base_sha": status.get("base_sha"),
            "truncated": True,
            "original_bytes": None,
            "diff": (
                "Full diff/security scan skipped because one or more changed "
                "paths are not safely reviewable as bounded UTF-8 text."
            ),
        }

    protected_changes = [
        path
        for path in changed_paths
        if _path_is_protected(path, protected_rules)
    ]

    dirty = bool(status["dirty"])
    ahead = int(status["commits_ahead_of_base"])
    blockers: list[str] = []
    warnings: list[str] = []

    if dirty and not (commit_message or "").strip():
        blockers.append(
            "Workspace has uncommitted changes; --message is required for finish."
        )

    if not dirty and ahead <= 0:
        blockers.append("Workspace has no changes or commits to finish.")

    if validation_blocked:
        blockers.append("One or more required project validation commands failed.")

    if not bool(reviewability.get("ok")):
        blockers.append(
            "One or more changed paths cannot be fully reviewed/secret-scanned "
            "by ActualCoder; inspect the reviewability issues and use the low-level "
            "workflow intentionally if this change must be handled."
        )

    if bool(reviewability.get("ok")) and bool(diff_result.get("truncated")):
        blockers.append(
            "The human-facing review diff was truncated by the configured output cap. "
            "Increase GITLAB_COMMAND_MAX_OUTPUT_BYTES or split the change before finish."
        )

    if protected_changes and not allow_protected:
        blockers.append(
            "Protected paths changed; review them and rerun with --allow-protected "
            "only when the scope is intentional."
        )

    if secret_findings and not allow_secret_match:
        blockers.append(
            "Potential credentials/secrets were detected in added diff lines; "
            "remove them or rerun with --allow-secret-match after explicit review."
        )

    if state.pushed and not state.merge_request_url:
        blockers.append(
            "This branch was already pushed without a recorded Merge Request. "
            "finish will not silently create or guess an MR after the first push."
        )

    mr_config = project_context.get("mr", {})
    if not isinstance(mr_config, dict):
        mr_config = {}
    target_branch = str(
        mr_config.get("target_branch")
        or status["base_ref"]
    ).strip()
    title_prefix = str(mr_config.get("title_prefix") or "")

    subject = ""
    if dirty and (commit_message or "").strip():
        subject = str(commit_message).strip()
    elif ahead > 0:
        subject = manager.latest_commit_subject(workspace_id)

    title = (mr_title or "").strip()
    if not title and subject:
        title = title_prefix + subject
    elif title_prefix and title and not title.startswith(title_prefix):
        title = title_prefix + title

    push_action = "push-update" if state.pushed else "push-mr"
    if push_action == "push-mr" and not title:
        blockers.append(
            "A Merge Request title could not be derived; provide --title or --message."
        )

    if not validations:
        warnings.append(
            "No project validation commands are configured in the workspace base contract."
        )
    if not project_metadata["found"]:
        warnings.append(
            "No .actualcoder.yaml was present at the workspace base; finish is using default project policy."
        )

    if protected_changes and allow_protected:
        warnings.append(
            "Protected-path changes were explicitly allowed for this finish invocation."
        )
    if secret_findings and allow_secret_match:
        warnings.append(
            "Secret-scan findings were explicitly overridden for this finish invocation."
        )

    snapshot_payload = {
        "head": status.get("head"),
        "dirty": bool(status.get("dirty")),
        "status_porcelain": str(status.get("status_porcelain") or ""),
        "commits_ahead_of_base": int(status.get("commits_ahead_of_base", 0)),
        "pushed": bool(state.pushed),
        "merge_request_url": state.merge_request_url,
        "remote_branch": state.remote_branch,
        "security_diff_sha256": hashlib.sha256(
            security_diff.encode("utf-8", errors="replace")
        ).hexdigest(),
    }
    snapshot_digest = hashlib.sha256(
        json.dumps(
            snapshot_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "ok": not blockers,
        "workspace": status,
        "project_config": {
            **project_metadata,
            "effective": project_context,
        },
        "changed_paths": changed_paths,
        "reviewability": reviewability,
        "protected_paths": protected_rules,
        "protected_path_changes": protected_changes,
        "secret_scan": {
            "ok": bool(reviewability.get("ok")) and not secret_findings,
            "coverage_complete": bool(reviewability.get("ok")),
            "findings": secret_findings,
            "overridden": bool(secret_findings and allow_secret_match),
        },
        "validations": validations,
        "review_diff": diff_result,
        "snapshot": {
            "digest": snapshot_digest,
            **snapshot_payload,
        },
        "plan": {
            "commit_required": dirty,
            "commit_message": (
                str(commit_message).strip()
                if commit_message is not None
                else None
            ),
            "push_action": push_action,
            "target_branch": target_branch,
            "mr_title": title or None,
            "mr_description": mr_description,
            "existing_mr": state.merge_request_url,
        },
        "warnings": warnings,
        "blockers": blockers,
    }


def execute_finish(
    *,
    manager: WorkspaceManager,
    workspace_id: str,
    plan: dict[str, object],
) -> dict[str, object]:
    if not bool(plan.get("ok")):
        raise RuntimeError("Cannot execute a blocked finish plan")

    action = plan["plan"]
    if not isinstance(action, dict):
        raise RuntimeError("Invalid finish plan")

    expected_snapshot = plan.get("snapshot")
    if not isinstance(expected_snapshot, dict):
        raise RuntimeError("Finish plan is missing its reviewed workspace snapshot")

    current_status = manager.status(workspace_id)
    current_state = manager.get_state(workspace_id)
    current_security_diff = manager.security_diff(workspace_id)
    current_payload = {
        "head": current_status.get("head"),
        "dirty": bool(current_status.get("dirty")),
        "status_porcelain": str(current_status.get("status_porcelain") or ""),
        "commits_ahead_of_base": int(
            current_status.get("commits_ahead_of_base", 0)
        ),
        "pushed": bool(current_state.pushed),
        "merge_request_url": current_state.merge_request_url,
        "remote_branch": current_state.remote_branch,
        "security_diff_sha256": hashlib.sha256(
            current_security_diff.encode("utf-8", errors="replace")
        ).hexdigest(),
    }
    current_digest = hashlib.sha256(
        json.dumps(
            current_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if current_digest != expected_snapshot.get("digest"):
        raise RuntimeError(
            "Workspace changed after the finish plan was reviewed. "
            "No Git write was performed; rerun actual-coder finish."
        )

    commit_result: dict[str, object] | None = None
    if bool(action.get("commit_required")):
        message = str(action.get("commit_message") or "").strip()
        commit_result = manager.commit(workspace_id, message)

    push_action = str(action.get("push_action"))
    if push_action == "push-mr":
        push_result = manager.push_and_create_mr(
            workspace_id,
            target_branch=str(action.get("target_branch") or ""),
            title=str(action.get("mr_title") or ""),
            description=str(action.get("mr_description") or ""),
        )
    elif push_action == "push-update":
        push_result = manager.push(workspace_id)
    else:
        raise RuntimeError(f"Unknown finish push action: {push_action}")

    return {
        "workspace_id": workspace_id,
        "commit": commit_result,
        "push": push_result,
        "final_workspace": manager.status(workspace_id),
    }
