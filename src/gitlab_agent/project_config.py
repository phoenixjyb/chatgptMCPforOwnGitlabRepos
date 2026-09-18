from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

from .config import AgentSettings

PROJECT_CONFIG_FILENAME = ".actualcoder.yaml"
PROJECT_CONFIG_VERSION = 1
KNOWN_BACKENDS = {"codex", "copilot"}


@dataclass(frozen=True)
class ProjectConfigResult:
    found: bool
    valid: bool
    source_ref: str
    source_path: str
    contract: dict[str, object]
    effective: dict[str, object]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "found": self.found,
            "valid": self.valid,
            "source": {
                "ref": self.source_ref,
                "path": self.source_path,
            },
            "contract": self.contract,
            "effective": self.effective,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _expect_mapping(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must be a mapping")
        return {}
    return value


def _unknown_keys(
    data: dict[str, Any],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    for key in sorted(set(data) - allowed):
        errors.append(f"Unknown key {label}.{key}")


def _string_list(
    value: Any,
    label: str,
    errors: list[str],
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        out.append(item.strip())
    return out


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    if path.is_absolute():
        return False
    if any(part in {"..", ""} for part in path.parts):
        return False
    return True


def parse_project_config(
    text: str | None,
    *,
    settings: AgentSettings,
    source_ref: str,
    source_path: str = PROJECT_CONFIG_FILENAME,
) -> ProjectConfigResult:
    """Parse and policy-check a repository-owned ActualCoder contract."""

    errors: list[str] = []
    warnings: list[str] = []

    if text is None:
        effective = {
            "base_branch": settings.default_base_ref,
            "preferred_agents": [],
            "validation_commands": [],
            "protected_paths": [],
            "instructions": [],
            "required_executables": [],
            "mr": {
                "target_branch": settings.default_base_ref,
                "title_prefix": "",
            },
        }
        warnings.append(
            f"{source_path} not found; user/default configuration will be used"
        )
        return ProjectConfigResult(
            found=False,
            valid=True,
            source_ref=source_ref,
            source_path=source_path,
            contract={},
            effective=effective,
            errors=errors,
            warnings=warnings,
        )

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        errors.append(f"Invalid YAML: {exc}")
        loaded = {}

    root = _expect_mapping(loaded, "root", errors)
    _unknown_keys(
        root,
        {
            "version",
            "project",
            "agents",
            "validation",
            "protected_paths",
            "instructions",
            "executables",
            "mr",
        },
        "root",
        errors,
    )

    version = root.get("version")
    if version != PROJECT_CONFIG_VERSION:
        errors.append(
            f"version must be {PROJECT_CONFIG_VERSION}; got {version!r}"
        )

    project = _expect_mapping(root.get("project"), "project", errors)
    _unknown_keys(project, {"base_branch"}, "project", errors)
    base_branch = project.get("base_branch", settings.default_base_ref)
    if not isinstance(base_branch, str) or not base_branch.strip():
        errors.append("project.base_branch must be a non-empty string")
        base_branch = settings.default_base_ref
    else:
        base_branch = base_branch.strip()

    agents = _expect_mapping(root.get("agents"), "agents", errors)
    _unknown_keys(agents, {"preferred"}, "agents", errors)
    preferred_agents = _string_list(
        agents.get("preferred"),
        "agents.preferred",
        errors,
    )
    for agent in preferred_agents:
        if agent not in KNOWN_BACKENDS:
            warnings.append(
                f"agents.preferred contains unsupported backend {agent!r}; "
                "current supported backends are codex and copilot"
            )

    validation = _expect_mapping(root.get("validation"), "validation", errors)
    _unknown_keys(validation, {"commands"}, "validation", errors)
    raw_commands = validation.get("commands", [])
    commands: list[dict[str, object]] = []
    if raw_commands is None:
        raw_commands = []
    if not isinstance(raw_commands, list):
        errors.append("validation.commands must be a list")
        raw_commands = []

    for index, raw_command in enumerate(raw_commands):
        label = f"validation.commands[{index}]"
        command = _expect_mapping(raw_command, label, errors)
        _unknown_keys(
            command,
            {"name", "argv", "required", "timeout_seconds"},
            label,
            errors,
        )

        name = command.get("name", f"command-{index + 1}")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name must be a non-empty string")
            name = f"command-{index + 1}"
        else:
            name = name.strip()

        argv = command.get("argv")
        if not isinstance(argv, list) or not argv:
            errors.append(f"{label}.argv must be a non-empty list of strings")
            argv = []
        normalized_argv: list[str] = []
        for arg_index, arg in enumerate(argv):
            if not isinstance(arg, str) or not arg:
                errors.append(f"{label}.argv[{arg_index}] must be a non-empty string")
                continue
            normalized_argv.append(arg)

        if normalized_argv:
            executable = normalized_argv[0]
            if "/" in executable or "\\" in executable:
                errors.append(
                    f"{label}.argv[0] must be a bare executable name, not a path"
                )
            elif executable not in settings.allowed_executables:
                errors.append(
                    f"{label} requires executable {executable!r}, which is not approved "
                    "by GITLAB_ALLOWED_EXECUTABLES"
                )

        required = command.get("required", True)
        if not isinstance(required, bool):
            errors.append(f"{label}.required must be true/false")
            required = True

        timeout = command.get("timeout_seconds", settings.command_timeout_seconds)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            errors.append(f"{label}.timeout_seconds must be a positive integer")
            timeout = settings.command_timeout_seconds
        effective_timeout = min(timeout, settings.command_timeout_seconds)
        if timeout > settings.command_timeout_seconds:
            warnings.append(
                f"{label}.timeout_seconds={timeout} exceeds the user maximum "
                f"{settings.command_timeout_seconds}; it will be capped"
            )

        commands.append(
            {
                "name": name,
                "argv": normalized_argv,
                "required": required,
                "timeout_seconds": effective_timeout,
            }
        )

    protected_paths = _string_list(
        root.get("protected_paths"),
        "protected_paths",
        errors,
    )
    for path in protected_paths:
        if not _safe_relative_path(path):
            errors.append(
                f"protected_paths entry {path!r} must be a safe repository-relative path"
            )

    instructions = _string_list(
        root.get("instructions"),
        "instructions",
        errors,
    )

    executables = _expect_mapping(root.get("executables"), "executables", errors)
    _unknown_keys(executables, {"required"}, "executables", errors)
    required_executables = _string_list(
        executables.get("required"),
        "executables.required",
        errors,
    )
    for executable in required_executables:
        if "/" in executable or "\\" in executable:
            errors.append(
                f"executables.required entry {executable!r} must be a bare executable"
            )
        elif executable not in settings.allowed_executables:
            errors.append(
                f"executables.required entry {executable!r} is not approved by "
                "GITLAB_ALLOWED_EXECUTABLES"
            )

    mr = _expect_mapping(root.get("mr"), "mr", errors)
    _unknown_keys(mr, {"target_branch", "title_prefix"}, "mr", errors)
    target_branch = mr.get("target_branch", base_branch)
    if not isinstance(target_branch, str) or not target_branch.strip():
        errors.append("mr.target_branch must be a non-empty string")
        target_branch = base_branch
    else:
        target_branch = target_branch.strip()

    title_prefix = mr.get("title_prefix", "")
    if not isinstance(title_prefix, str):
        errors.append("mr.title_prefix must be a string")
        title_prefix = ""
    elif len(title_prefix) > 100:
        errors.append("mr.title_prefix must be <= 100 characters")

    contract: dict[str, object] = {
        "version": version,
        "project": {"base_branch": base_branch},
        "agents": {"preferred": preferred_agents},
        "validation": {"commands": commands},
        "protected_paths": protected_paths,
        "instructions": instructions,
        "executables": {"required": required_executables},
        "mr": {
            "target_branch": target_branch,
            "title_prefix": title_prefix,
        },
    }

    effective = {
        "base_branch": base_branch,
        "preferred_agents": preferred_agents,
        "validation_commands": commands,
        "protected_paths": protected_paths,
        "instructions": instructions,
        "required_executables": required_executables,
        "mr": {
            "target_branch": target_branch,
            "title_prefix": title_prefix,
        },
    }

    return ProjectConfigResult(
        found=True,
        valid=not errors,
        source_ref=source_ref,
        source_path=source_path,
        contract=contract,
        effective=effective,
        errors=errors,
        warnings=warnings,
    )
