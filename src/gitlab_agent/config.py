from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ALLOWED_EXECUTABLES = {
    "python",
    "python3",
    "pytest",
    "uv",
    "node",
    "npm",
    "pnpm",
    "yarn",
    "make",
    "cmake",
    "ninja",
    "cargo",
    "go",
    "mvn",
    "gradle",
}


def load_env_file(path: Path) -> None:
    """Load a simple .env file without overwriting already-exported variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def csv_set(name: str, default: set[str] | None = None) -> set[str]:
    raw = os.getenv(name)
    if raw is None:
        return set(default or set())
    return {item.strip() for item in raw.split(",") if item.strip()}


def resolve_env_file() -> Path:
    """Resolve config for global CLI use while keeping local .env compatibility."""
    explicit = os.getenv("GITLAB_AGENT_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()

    user_config = Path("~/.config/gitlab-agent/.env").expanduser()
    if user_config.is_file():
        return user_config

    return Path(".env")


@dataclass(frozen=True)
class AgentSettings:
    config_file: Path
    gitlab_base_url: str
    api_token: str
    api_verify_ssl: bool
    api_trust_env: bool
    git_token: str
    git_username: str
    git_trust_env: bool
    allowed_projects: set[str]
    require_write_allowlist: bool
    workspace_root: Path
    branch_prefix: str
    default_base_ref: str
    allowed_executables: set[str]
    command_timeout_seconds: int
    max_output_bytes: int
    max_file_bytes: int
    git_author_name: str | None
    git_author_email: str | None

    @classmethod
    def load(cls) -> "AgentSettings":
        env_file = resolve_env_file()
        load_env_file(env_file)

        base_url = os.getenv("GITLAB_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("GITLAB_BASE_URL is required")
        if not base_url.startswith(("http://", "https://")):
            raise RuntimeError("GITLAB_BASE_URL must start with http:// or https://")

        api_token = os.getenv("GITLAB_TOKEN", "").strip()
        git_token = os.getenv("GITLAB_GIT_TOKEN", "").strip() or api_token

        root = Path(
            os.getenv(
                "GITLAB_WORKSPACE_ROOT",
                "~/.local/share/chatgpt-gitlab-mcp",
            )
        ).expanduser()

        branch_prefix = os.getenv("GITLAB_BRANCH_PREFIX", "chatgpt/").strip()
        if not branch_prefix or " " in branch_prefix:
            raise RuntimeError("GITLAB_BRANCH_PREFIX must be a non-empty branch prefix")

        return cls(
            config_file=env_file.resolve() if env_file.exists() else env_file.expanduser(),
            gitlab_base_url=base_url,
            api_token=api_token,
            api_verify_ssl=env_bool("GITLAB_VERIFY_SSL", True),
            api_trust_env=env_bool("GITLAB_TRUST_ENV", False),
            git_token=git_token,
            git_username=os.getenv("GITLAB_GIT_USERNAME", "oauth2").strip() or "oauth2",
            git_trust_env=env_bool("GITLAB_GIT_TRUST_ENV", False),
            allowed_projects=csv_set("GITLAB_ALLOWED_PROJECTS"),
            require_write_allowlist=env_bool("GITLAB_REQUIRE_WRITE_ALLOWLIST", True),
            workspace_root=root,
            branch_prefix=branch_prefix,
            default_base_ref=os.getenv("GITLAB_DEFAULT_BASE_REF", "main").strip() or "main",
            allowed_executables=csv_set(
                "GITLAB_ALLOWED_EXECUTABLES",
                DEFAULT_ALLOWED_EXECUTABLES,
            ),
            command_timeout_seconds=int(
                os.getenv("GITLAB_COMMAND_TIMEOUT_SECONDS", "300")
            ),
            max_output_bytes=int(os.getenv("GITLAB_COMMAND_MAX_OUTPUT_BYTES", "120000")),
            max_file_bytes=int(os.getenv("GITLAB_MAX_WRITE_FILE_BYTES", "1000000")),
            git_author_name=os.getenv("GITLAB_GIT_AUTHOR_NAME") or None,
            git_author_email=os.getenv("GITLAB_GIT_AUTHOR_EMAIL") or None,
        )

    def assert_project_allowed_for_workspace(self, project: str) -> None:
        if self.allowed_projects:
            if project not in self.allowed_projects:
                raise RuntimeError(
                    f"Project {project!r} is not in GITLAB_ALLOWED_PROJECTS"
                )
            return
        if self.require_write_allowlist:
            raise RuntimeError(
                "GITLAB_ALLOWED_PROJECTS is empty. For v0.2 local/write workflows, "
                "configure an explicit project allowlist or set "
                "GITLAB_REQUIRE_WRITE_ALLOWLIST=false intentionally."
            )
