# ChatGPT MCP for Self-Hosted GitLab Repositories

[![CI](https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

This project now has **two complementary pieces**:

1. **Read-only ChatGPT MCP** — inspect private/self-hosted GitLab repositories from normal ChatGPT conversations.
2. **v0.2 local coding engine** — let Codex or a human create isolated worktrees, edit code, run builds/tests, commit, push, and create a Merge Request.

The v0.2 design deliberately avoids OpenAI model API calls from this project.

## Architecture

```text
Normal ChatGPT Pro
    │
    │ read/fetch MCP
    ▼
OpenAI Secure MCP Tunnel
    │
    ▼
server.py (read-only)
    │
    ▼
Self-hosted GitLab


Codex CLI / terminal
    │
    ▼
gitlab-agent
    │
    ├── isolated worktree
    ├── edit / apply patch
    ├── build / test
    ├── diff
    ├── commit
    ├── push feature branch
    └── create GitLab MR
```

The GitLab server does **not** need to be directly reachable from the public Internet for the ChatGPT read MCP. The machine running the MCP/tunnel only needs to reach GitLab plus OpenAI over outbound HTTPS.

## v0.1 read-only MCP tools

- `gitlab_whoami`
- `list_projects`
- `get_repository_tree`
- `get_file`
- `search_code`
- `get_merge_request`
- `get_merge_request_diff`
- `get_pipelines`
- `get_pipeline_jobs`
- `get_job_log`

## v0.2 local coding engine

Current alpha CLI commands:

```text
gitlab-agent config
gitlab-agent create
gitlab-agent task
gitlab-agent list
gitlab-agent status
gitlab-agent resume
gitlab-agent path
gitlab-agent files
gitlab-agent read
gitlab-agent write
gitlab-agent apply-patch
gitlab-agent diff
gitlab-agent run
gitlab-agent commit
gitlab-agent push
gitlab-agent push-update
gitlab-agent push-mr
gitlab-agent cleanup
```

### Example workflow

```bash
gitlab-agent create team/project-a \
  --base-ref main \
  --task fix-timeout
```

The command returns JSON containing a `workspace_id`.

Then:

```bash
gitlab-agent status <workspace-id>
gitlab-agent read <workspace-id> src/example.py

cat change.patch | gitlab-agent apply-patch <workspace-id>

gitlab-agent run <workspace-id> -- uv run pytest

gitlab-agent diff <workspace-id>

gitlab-agent commit <workspace-id> \
  -m "Fix timeout handling"

gitlab-agent push-mr <workspace-id> \
  --target main \
  --title "Fix timeout handling" \
  --description-file mr.md
```

The generated feature branch uses a safe prefix such as:

```text
chatgpt/fix-timeout-a1b2c3d4
```

The engine does not force-push and does not push directly to the base branch.

## Quick start

```bash
git clone https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos.git
cd chatgptMCPforOwnGitlabRepos

cp .env.example .env
chmod 600 .env
# edit .env

uv sync
```

Test GitLab connectivity:

```bash
uv run python smoke_test.py
```

Test the read MCP:

```bash
uv run mcp dev server.py
```

Test the v0.2 CLI:

```bash
uv run gitlab-agent --help
```

### Install `gitlab-agent` for use from any worktree

For Codex, install the CLI as an editable user tool:

```bash
bash scripts/install_user.sh
```

Then copy your working local configuration once:

```bash
mkdir -p ~/.config/gitlab-agent
cp .env ~/.config/gitlab-agent/.env
chmod 600 ~/.config/gitlab-agent/.env
```

After that, from any directory:

```bash
gitlab-agent --help
gitlab-agent config
```

The global CLI first uses `GITLAB_AGENT_ENV_FILE` when explicitly set, otherwise
`~/.config/gitlab-agent/.env`, then falls back to a local `.env`.

## Credentials

For the read MCP:

```text
GITLAB_TOKEN
```

Recommended scopes:

```text
read_api
read_repository
```

For v0.2 Git clone/push, a separate credential is recommended:

```text
GITLAB_GIT_TOKEN
```

For push/MR creation it needs GitLab `write_repository`.

The initial MR can be created during `git push` using GitLab push options, so the v0.2 happy path does not require broad GitLab `api` write scope.

## Zero OpenAI model API usage

This repository intentionally:

- does not depend on the OpenAI Python SDK;
- does not call OpenAI model endpoints;
- does not need `OPENAI_API_KEY` for `gitlab-agent`;
- keeps the ChatGPT read MCP separate from local coding execution.

CI checks project Python/package code to help prevent accidental model API integration.

If you use Codex and want to avoid API billing, sign Codex in with your ChatGPT subscription rather than configuring it with an API key.

## Security defaults

- `.env` is ignored by Git.
- Project allowlisting is required by default for v0.2 workspaces.
- Feature branches use a configured prefix.
- All workspace paths are anchored under a managed worktree root.
- Build/test commands use an executable allowlist and `shell=False`.
- Obvious token/secret/password/API-key environment variables are stripped from build/test subprocesses.
- The host runner is **not a full filesystem/container sandbox**; use a VM/container for untrusted repositories.
- Never commit GitLab tokens, OpenAI tunnel runtime keys, or other secrets.

## Documentation

- **English setup guide:** [docs/SETUP_TUTORIAL.md](docs/SETUP_TUTORIAL.md)
- **中文配置教程:** [docs/SETUP_TUTORIAL_CN.md](docs/SETUP_TUTORIAL_CN.md)
- **v0.2 Codex/local coding quickstart:** [docs/V0.2_CODEX_QUICKSTART.md](docs/V0.2_CODEX_QUICKSTART.md)
- **v0.2 architecture:** [docs/V0.2_WRITE_ACCESS_DESIGN.md](docs/V0.2_WRITE_ACCESS_DESIGN.md)
- **Troubleshooting:** [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- **Security:** [SECURITY.md](SECURITY.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)

## HTTP GitLab instances

The MCP/CLI-to-GitLab hop can use HTTP if that is how your internal GitLab is deployed. This is functional but not encrypted. Keep the host and GitLab on a trusted network/VPN and migrate to HTTPS when practical.

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Status

- `v0.1.0`: tagged read-only release.
- `v0.2.0-dev`: active development branch for the local Codex coding engine.
- Package version on the v0.2 branch: `0.2.0a2`.
- Alpha.2 adds global installation, Codex task/resume handoffs, and iterative pushes to an existing MR branch.
