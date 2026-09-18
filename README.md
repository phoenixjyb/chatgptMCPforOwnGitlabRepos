# ChatGPT MCP for Self-Hosted GitLab + ActualCoder

[![CI](https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A practical toolchain for working with **private/self-hosted GitLab** from ChatGPT and local coding agents without exposing GitLab directly to the public Internet.

The repository has two complementary layers:

1. **Read-only ChatGPT MCP** — lets normal ChatGPT conversations inspect GitLab repositories, merge requests, pipelines, jobs, and logs.
2. **ActualCoder** — creates isolated local Git worktrees and hands them to Codex CLI or GitHub Copilot CLI while `gitlab-agent` owns the GitLab branch/MR lifecycle.

The repository itself does **not** call OpenAI model APIs.

## Architecture

```text
Normal ChatGPT
    │
    │ read-only MCP
    ▼
Secure MCP Tunnel
    │
    ▼
server.py
    │
    ▼
Self-hosted GitLab


Codex CLI ───────┐
Copilot CLI ─────┼──► ActualCoder
future agents ───┘        │
                          ▼
                    gitlab-agent
                          │
                          ├── isolated worktree
                          ├── build / test
                          ├── diff
                          ├── commit
                          ├── push / push-update
                          ├── create Merge Request
                          └── recover existing MR/branch
                               │
                               ▼
                       Self-hosted GitLab
```

## Recommended team entry point

For team installation, configuration, daily workflow, MR recovery, security rules, and troubleshooting, use:

**[团队安装、配置与使用完整指南（中文）](docs/TEAM_GUIDE_CN.md)**

Other references:

- [ActualCoder Quickstart](docs/ACTUAL_CODER_QUICKSTART.md)
- [ChatGPT MCP setup — English](docs/SETUP_TUTORIAL.md)
- [ChatGPT MCP 配置教程 — 中文](docs/SETUP_TUTORIAL_CN.md)
- [v0.2 architecture](docs/V0.2_WRITE_ACCESS_DESIGN.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Quick start: ActualCoder

Requirements:

- macOS or Linux;
- Git;
- Python 3.10+;
- [uv](https://docs.astral.sh/uv/);
- network access to the target GitLab;
- at least one coding backend: Codex CLI or GitHub Copilot CLI.

Clone and prepare:

```bash
git clone https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos.git
cd chatgptMCPforOwnGitlabRepos

# main is the team-consumption branch
cp .env.example .env
chmod 600 .env
# edit .env

uv sync
bash scripts/install_user.sh
```

Install the stable per-user config:

```bash
mkdir -p ~/.config/gitlab-agent
cp .env ~/.config/gitlab-agent/.env
chmod 700 ~/.config/gitlab-agent
chmod 600 ~/.config/gitlab-agent/.env
```

Verify:

```bash
actual-coder --help
actual-coder config
actual-coder agents
gitlab-agent --help
```

Start a coding task:

```bash
actual-coder task team/project-a \
  --agent copilot \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

Or use Codex:

```bash
actual-coder task team/project-a \
  --agent codex \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

ActualCoder returns a managed `workspace_id`, worktree path, backend launch command, and a ready-to-use agent prompt.

## Daily GitLab workflow

After the coding backend edits the managed worktree:

```bash
WS=<workspace-id>

gitlab-agent status "$WS"
gitlab-agent run "$WS" -- <allowed-test-command>
gitlab-agent diff "$WS"
gitlab-agent commit "$WS" -m "Describe the change"
```

Create the first MR:

```bash
gitlab-agent push-mr "$WS" \
  --target main \
  --title "Describe the change" \
  --description-file /tmp/mr.md
```

Continue an existing MR:

```bash
gitlab-agent push-update "$WS"
```

Recover an MR after local cleanup or on another machine:

```bash
actual-coder checkout-mr team/project-a 123 \
  --agent copilot \
  --goal "Continue this MR and address review feedback"
```

Switch coding backend without changing Git state:

```bash
actual-coder resume "$WS" --agent copilot --goal "Continue the task"
actual-coder resume "$WS" --agent codex   --goal "Continue the task"
```

## Read-only ChatGPT MCP tools

The ChatGPT-facing MCP remains read-only and exposes:

```text
gitlab_whoami
list_projects
get_repository_tree
get_file
search_code
get_merge_request
get_merge_request_diff
get_pipelines
get_pipeline_jobs
get_job_log
```

For setup, see [docs/SETUP_TUTORIAL_CN.md](docs/SETUP_TUTORIAL_CN.md).

## Credentials and permissions

Keep credentials outside Git.

Recommended separation:

```text
GITLAB_TOKEN
  read_api + read_repository
  Used by the read MCP and GitLab metadata lookups such as checkout-mr.

GITLAB_GIT_TOKEN
  write_repository
  Used for Git clone/fetch/push.
  If unset, Git operations fall back to GITLAB_TOKEN.
```

Restrict writable projects:

```bash
GITLAB_ALLOWED_PROJECTS=team/project-a,team/project-b
GITLAB_REQUIRE_WRITE_ALLOWLIST=true
```

The engine does not force-push and does not push directly to the configured base branch.

## Secret / credential audit

Never commit:

- `.env`;
- real GitLab/GitHub/model API tokens;
- Secure MCP control-plane credentials;
- private keys/certificates;
- developer-specific deployment information that should remain private.

Run before sharing changes:

```bash
uv run python scripts/check_repo_secrets.py
```

For a release/security audit:

```bash
uv run python scripts/check_repo_secrets.py --history
```

CI checks the full available Git history.

## Security boundaries

- Explicit project allowlist by default.
- Generated/recovered branches must use the configured safe prefix.
- No direct base-branch push.
- No force push.
- No merge/approve/remote-delete operation.
- Build/test runner uses `shell=False`, executable allowlisting, timeout/output caps, and strips obvious secret variables.
- Git credentials are passed through temporary `GIT_ASKPASS`, not embedded in remote URLs.
- The host runner is **not a VM/container sandbox**. Use a container/VM for untrusted repositories.
- HTTP GitLab works, but tokens/source traffic are not encrypted on that hop. Prefer HTTPS or a trusted private network/VPN.

See [SECURITY.md](SECURITY.md) for details.

## Compatibility commands

The canonical user-facing command is now:

```bash
actual-coder
```

For backward compatibility, the older alias remains available:

```bash
codingagent
```

The low-level controller remains:

```bash
gitlab-agent
```

## Current status

- `v0.1.0`: read-only ChatGPT MCP release.
- `main`: recommended team-consumption branch.
- Current package version: `0.2.0`.
- Real deployment validation has covered:
  - isolated workspace creation;
  - controlled edit/test/diff;
  - commit and MR creation;
  - repeated pushes to the same MR;
  - cleanup and MR reconstruction;
  - switching Codex/Copilot handoffs;
  - a real C++ coding task completed through GitHub Copilot CLI.

## License

Apache License 2.0. See [LICENSE](LICENSE).
