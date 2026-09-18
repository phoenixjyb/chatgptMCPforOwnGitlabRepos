# Troubleshooting

## `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed`

The host likely has `ALL_PROXY`, `HTTP_PROXY`, or `HTTPS_PROXY` set and `httpx` is trying to use it.

This project defaults to:

```bash
GITLAB_TRUST_ENV=false
```

which tells `httpx` not to inherit those proxy variables for GitLab traffic.

Inspect your shell:

```bash
env | grep -i proxy
```

Do **not** install SOCKS support just to access an internal GitLab unless that GitLab genuinely must be reached through the proxy.

## Smoke test succeeds but MCP Inspector tool calls fail

Check that the current `server.py` loads `.env` and that the token is present without printing it:

```bash
uv run python - <<'PY'
import os
from server import gitlab
print("base_url =", gitlab.base_url)
print("token_set =", bool(gitlab.token))
print("token_len =", len(gitlab.token))
print("trust_env =", gitlab.trust_env)
PY
```

Then retest:

```bash
uv run mcp dev server.py
```

## Inspector opens but shows `Disconnected`

Toggle/connect the stdio server in MCP Inspector. Seeing the tool list proves `tools/list` works; execute `gitlab_whoami` to verify the full MCP → GitLab call path.

## `tunnel-client doctor` reports `SKIP` for stdio reachability or OAuth metadata

That is expected for a stdio target. The important line is:

```text
RESULT ok
```

## ChatGPT says `No tunnels yet`

Check:

1. The tunnel exists in the same OpenAI Platform organization you are using.
2. It is associated/available to the target ChatGPT workspace/account.
3. Your account has Tunnel Read + Use permission.
4. `tunnel-client run --profile ...` is actually running.
5. Refresh the ChatGPT app/plugin creation screen after association changes.

## Tunnel is healthy but ChatGPT cannot read GitLab

Work from the inside out:

```text
GitLab API smoke test
  ↓
MCP Inspector
  ↓
tunnel-client doctor
  ↓
tunnel-client run
  ↓
ChatGPT tool scan
```

Do not debug all layers at once.

## `401` / `403` from GitLab

Typical causes:

- token expired or revoked;
- missing `read_api` / `read_repository` scope;
- token owner cannot access the project;
- project is not allowed by `GITLAB_ALLOWED_PROJECTS`.

## Project allowlist errors

`GITLAB_ALLOWED_PROJECTS` requires exact values, e.g.:

```bash
GITLAB_ALLOWED_PROJECTS=123,group/project-a,group/project-b
```

Use either the numeric project ID or exact `path_with_namespace`.


## `actual-coder: command not found`

From the tool repository:

```bash
bash scripts/install_user.sh
```

If the command is still missing:

```bash
uv tool update-shell
```

Open a new terminal and verify:

```bash
which actual-coder
actual-coder --help
```

## ActualCoder cannot find configuration

The recommended per-user config is:

```text
~/.config/gitlab-agent/.env
```

Check the effective non-secret configuration:

```bash
actual-coder config
```

The config lookup order is `GITLAB_AGENT_ENV_FILE`, then `~/.config/gitlab-agent/.env`, then a local `.env`.

## Git clone/fetch/push returns 502 on an internal GitLab

A machine-wide proxy is a common cause. For a GitLab that should be reached directly:

```bash
GITLAB_TRUST_ENV=false
GITLAB_GIT_TRUST_ENV=false
```

The Git setting also clears Git's configured `http.proxy` for managed clone/fetch/push operations.

## Build/test command is rejected

`gitlab-agent run` only allows executables listed in `GITLAB_ALLOWED_EXECUTABLES`.

Inspect:

```bash
actual-coder config
```

Add only the commands your project genuinely needs (for example `colcon` or `ctest` for some ROS/C++ projects).

## Codex usage is exhausted

Do not rebuild the workspace. Switch the same workspace to another backend:

```bash
actual-coder resume "$WS" \
  --agent copilot \
  --goal "Continue the current task"
```

Git state and any existing MR remain unchanged.

## Local workspace was cleaned up but the MR still exists

Reconstruct it:

```bash
actual-coder checkout-mr team/project-a 123 \
  --agent copilot \
  --goal "Continue this MR"
```

After further commits, use:

```bash
gitlab-agent push-update "$WS"
```

For the full team workflow, see [TEAM_GUIDE_CN.md](TEAM_GUIDE_CN.md).
