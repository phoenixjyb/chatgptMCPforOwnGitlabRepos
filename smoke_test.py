from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx


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


def resolve_env_file() -> Path:
    explicit = os.getenv("GITLAB_AGENT_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()

    user_config = Path("~/.config/gitlab-agent/.env").expanduser()
    if user_config.is_file():
        return user_config

    return Path(__file__).resolve().with_name(".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    load_env_file(resolve_env_file())

    base = os.getenv("GITLAB_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("GITLAB_TOKEN", "").strip()
    if not base:
        print("ERROR: GITLAB_BASE_URL is not set", file=sys.stderr)
        return 2
    if not token:
        print("ERROR: GITLAB_TOKEN is not set", file=sys.stderr)
        return 2

    headers = {"PRIVATE-TOKEN": token, "Accept": "application/json"}
    verify = env_bool("GITLAB_VERIFY_SSL", True)
    timeout = float(os.getenv("GITLAB_TIMEOUT_SECONDS", "30"))
    trust_env = env_bool("GITLAB_TRUST_ENV", False)

    with httpx.Client(
        headers=headers,
        verify=verify,
        timeout=timeout,
        follow_redirects=True,
        trust_env=trust_env,
    ) as client:
        user = client.get(f"{base}/api/v4/user")
        print(f"GET /user -> {user.status_code}")
        user.raise_for_status()
        u = user.json()
        print(f"Authenticated as: {u.get('username')} ({u.get('name')})")

        projects = client.get(
            f"{base}/api/v4/projects",
            params={
                "membership": True,
                "simple": True,
                "per_page": 10,
                "order_by": "last_activity_at",
            },
        )
        print(f"GET /projects -> {projects.status_code}")
        projects.raise_for_status()
        for project in projects.json():
            print(f"- {project.get('id')}: {project.get('path_with_namespace')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
