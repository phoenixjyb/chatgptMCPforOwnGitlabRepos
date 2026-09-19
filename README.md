# ReasonFirst

> **Reasoning-first coding orchestration**
>
> **Use your strongest reasoning model for reasoning. Let coding agents do the coding.**

[![CI](https://github.com/phoenixjyb/reasonFirst/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenixjyb/reasonFirst/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

ReasonFirst connects **high-capability conversational reasoning** with **replaceable coding agents** inside a controlled software-engineering workflow.

The core idea is to separate two different jobs:

- **Reasoning** — research, architecture, task decomposition, debugging strategy, review, and interpreting real engineering evidence.
- **Execution** — repository inspection, file edits, build/test iterations, and implementation work.

A strong chat/reasoning model can lead the work while coding agents such as **Codex CLI** and **GitHub Copilot CLI** handle high-volume implementation. **ActualCoder** is the execution/orchestration engine that connects those layers to isolated worktrees, validation, Git state, Merge Requests, and CI feedback.

This lets users make deliberate use of the subscriptions and tools they already have:

```text
high-value reasoning capacity
        ↓
architecture / planning / debugging / review

coding-agent entitlement / quota
        ↓
inspection / editing / tests / iteration

local tools + SCM + CI
        ↓
deterministic execution and evidence
```

> **Spend reasoning capacity on reasoning. Spend coding-agent quota on coding.**

ReasonFirst is **not a model proxy** and does not call OpenAI model inference APIs. Each reasoning/coding backend continues to use the user's own authenticated experience, CLI session, subscription, or entitlement.

For the full rationale, see **[ReasonFirst Design Philosophy](docs/DESIGN_PHILOSOPHY.md)**.

## Architecture

ReasonFirst separates software work into four planes:

```text
                         Human
                           │
                           ▼
                 ┌───────────────────┐
                 │  Reasoning Plane  │
                 │                   │
                 │ ChatGPT / other   │
                 │ strong reasoning  │
                 │                   │
                 │ research          │
                 │ architecture      │
                 │ planning          │
                 │ debugging         │
                 │ review            │
                 └─────────┬─────────┘
                           │ task / constraints
                           ▼
                 ┌───────────────────┐
                 │   Control Plane   │
                 │                   │
                 │   ReasonFirst     │
                 │   ActualCoder     │
                 │   gitlab-agent    │
                 └─────────┬─────────┘
                           │ controlled handoff
              ┌────────────┴────────────┐
              ▼                         ▼
        ┌───────────┐             ┌───────────┐
        │ Codex CLI │             │ Copilot   │
        │           │             │ CLI       │
        └─────┬─────┘             └─────┬─────┘
              │      Execution Plane     │
              └────────────┬─────────────┘
                           ▼
                   isolated worktree
                           │
                    edit / build / test
                           │
                           ▼
                    Git / MR / CI
                           │
                           ▼
                 ┌───────────────────┐
                 │  Feedback Plane   │
                 │                   │
                 │ diff / tests / CI │
                 │ review evidence   │
                 └─────────┬─────────┘
                           │
                           └──────────────► reason again
```

### Current implementation

Today, GitLab is the first fully implemented SCM/CI adapter:

```text
Reasoning Plane
  ChatGPT
      │
      ├── optional read-only GitLab MCP bridge
      │
      ▼
ReasonFirst
  ActualCoder
      │
      ├── Codex CLI
      ├── GitHub Copilot CLI
      └── future coding backends
      │
      ▼
gitlab-agent
      │
      ├── isolated worktree
      ├── build / test
      ├── diff / review gates
      ├── commit
      ├── push / push-update
      ├── Merge Request lifecycle
      └── GitLab CI feedback
```

GitLab is an implementation target, **not the product identity**. The architectural goal is to keep reasoning interfaces, coding backends, and SCM/CI adapters replaceable.

## Naming / components

- **ReasonFirst** — the project and product: reasoning-first coding orchestration.
- **ActualCoder / `actual-coder`** — the high-level local coding orchestration engine and CLI.
- **`gitlab-agent`** — the lower-level workspace/Git/GitLab control plane.
- **Codex / Copilot** — current coding backends; replaceable execution workers.
- **Read-only GitLab MCP** — optional bridge that lets the reasoning interface inspect private/self-hosted GitLab.

### Compatibility names kept in v0.3

The public product/repository name becomes **ReasonFirst**, but several internal names intentionally remain unchanged for compatibility with existing installations:

- CLI: `actual-coder` and `gitlab-agent`;
- Python package/module: `gitlab_agent`;
- Python distribution name: `chatgpt-selfhosted-gitlab-mcp`;
- user config: `~/.config/gitlab-agent/`;
- existing workspace root defaults such as `~/.local/share/chatgpt-gitlab-mcp/`.

Renaming those would require state/install migration and is better handled as an explicit later compatibility change rather than mixed into the repository-brand rename.

## Onboarding

For installation, configuration, daily workflow, MR recovery, security rules, and troubleshooting, start here:

**[ReasonFirst Onboarding Guide（中文）](docs/ONBOARDING_GUIDE_CN.md)**

For team members using ChatGPT Pro + Secure MCP Tunnel, including Tunnel ID / Runtime API Key setup and OS-specific credential storage:

**[团队 OpenAI Secure MCP Tunnel 配置指南（中文）](docs/OPENAI_TUNNEL_TEAM_SETUP_CN.md)**

Other references:

- [ReasonFirst Design Philosophy](docs/DESIGN_PHILOSOPHY.md)
- [ActualCoder Quickstart](docs/ACTUAL_CODER_QUICKSTART.md)
- [ChatGPT MCP setup — English](docs/SETUP_TUTORIAL.md)
- [ChatGPT MCP 配置教程 — 中文](docs/SETUP_TUTORIAL_CN.md)
- [v0.2 architecture](docs/V0.2_WRITE_ACCESS_DESIGN.md)
- [v0.3 分块开发路线](docs/V0.3_ROADMAP_CN.md)
- [v0.3 发布前架构与安全审计](docs/V0.3_RELEASE_AUDIT_CN.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Quick start: ReasonFirst / ActualCoder

Requirements:

- macOS, Linux, or Windows 10/11;
- Git;
- Python 3.10+;
- [uv](https://docs.astral.sh/uv/);
- network access to the target GitLab;
- at least one coding backend: Codex CLI or GitHub Copilot CLI.

Existing clones created before the ReasonFirst rename should update their remote once:

```bash
git remote set-url origin https://github.com/phoenixjyb/reasonFirst.git
git remote -v
```

GitHub redirects the previous repository URL, but updating the remote keeps local/team documentation unambiguous.

Clone and prepare on macOS/Linux:

```bash
git clone https://github.com/phoenixjyb/reasonFirst.git
cd reasonFirst

cp .env.example .env
chmod 600 .env
# edit .env

uv sync
bash scripts/install_user.sh
```

On native Windows PowerShell:

```powershell
git clone https://github.com/phoenixjyb/reasonFirst.git
Set-Location reasonFirst

Copy-Item .env.example .env
# edit .env

uv sync
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_user.ps1
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
actual-coder doctor
gitlab-agent --help
```

For diagnostics without touching the GitLab API:

```bash
actual-coder doctor --offline
```

`doctor` is non-destructive: it does not modify GitLab and does not invoke Codex/Copilot models. It checks the local runtime, config safety, project allowlist, GitLab API authentication (unless `--offline`), proxy policy, workspace state, disk space, coding-backend availability, and optional tunnel-client setup.

### Repository-local project contract

A target repository may optionally contain:

```text
.actualcoder.yaml
```

Validate it without creating a worktree:

```bash
actual-coder project-config team/project-a --validate
```

Validate a local candidate before committing it:

```bash
actual-coder project-config team/project-a \
  --file .actualcoder.example.yaml \
  --validate
```

Use another ref:

```bash
actual-coder project-config team/project-a --ref develop --validate
```

The contract can declare base branch, preferred backends, validation argv, protected paths, project instructions, required executables, and MR conventions. Repository configuration **cannot grant itself new executable permissions**: every requested executable must already be present in the developer's `GITLAB_ALLOWED_EXECUTABLES`.

See [`.actualcoder.example.yaml`](.actualcoder.example.yaml).

### High-level start workflow

The v0.3 high-level entry point is:

```bash
actual-coder start team/project-a \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

`start` defaults to `--agent auto` and performs:

```text
doctor preflight
→ read/validate .actualcoder.yaml
→ resolve effective base branch
→ select an installed backend
→ create isolated worktree
→ inject project instructions/protected paths/validation context
→ launch the selected coding CLI interactively
```

To validate everything without invoking a coding model:

```bash
actual-coder start team/project-a \
  --task inspect \
  --goal "Inspect the workspace only" \
  --no-launch
```

The launcher does not enable broad automatic-approval modes. Codex receives the generated handoff as its initial interactive prompt; Copilot is launched in interactive mode with the generated initial prompt.

### GitLab CI feedback loop

After an MR/branch has a pipeline, inspect it without invoking a model:

```bash
actual-coder ci <workspace-id>
```

ActualCoder selects the pipeline matching the current workspace HEAD when available, summarizes jobs, fetches only failed-job trace tails, removes ANSI control codes, redacts high-signal credentials/secret assignments, and reports whether the result is stale for the current workspace.

To create a coding handoff grounded in that CI evidence:

```bash
actual-coder resume <workspace-id> \
  --agent auto \
  --from-ci \
  --goal "Fix the CI failure at its root cause"
```

`resume --from-ci` refuses stale CI when the latest pipeline SHA does not match the current workspace HEAD. CI logs are injected into the prompt under an explicit **untrusted diagnostic data** boundary; log text cannot override the user goal or ActualCoder safety rules.

This command does not automatically edit, commit, push, retry a pipeline, approve, or merge anything. After a repair, use the normal `actual-coder finish` workflow again.

### Controlled finish workflow

After the coding backend makes changes, first preview the finish plan:

```bash
actual-coder finish <workspace-id> \
  --message "fix: describe the change" \
  --dry-run
```

The dry run performs project validation commands, scans added diff lines for high-signal credentials, checks protected paths, shows the diff, and plans either `push-mr` or `push-update`. It performs no commit or push.

If the plan is unblocked:

```bash
actual-coder finish <workspace-id> \
  --message "fix: describe the change"
```

ActualCoder prints the plan and requires human confirmation before Git writes. `--yes` exists for intentional scripted use, but it does not bypass validation, protected-path, or secret-scan gates. Protected or secret findings require their own explicit override flags after review.

The lower-level/compatibility task command remains available:

```bash
actual-coder task team/project-a \
  --agent copilot \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

Or let ActualCoder select an installed backend:

```bash
actual-coder task team/project-a \
  --agent auto \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

`auto` reads `.actualcoder.yaml` from the task/base ref when present and uses `agents.preferred`; otherwise it falls back to `codex → copilot`. It never launches a model during selection and reports the selected backend plus selection reason in the JSON handoff.

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

- **ReasonFirst** is the project/product identity.
- **ActualCoder** remains the stable orchestration CLI/engine.
- `main` is the recommended stable team-consumption branch.
- Current package version: `0.3.0`.
- `v0.1.0` began as a read-only ChatGPT ↔ self-hosted GitLab MCP; v0.3 evolved into the broader ReasonFirst architecture.
- v0.3 delivers `doctor`, repository-local project contracts, project-aware auto backend selection, `start`, controlled `finish`, and GitLab CI feedback / `resume --from-ci`.
- Real deployment validation has covered:
  - isolated workspace creation;
  - controlled edit/test/diff;
  - commit and MR creation;
  - repeated pushes to the same MR;
  - cleanup and MR reconstruction;
  - switching Codex/Copilot handoffs;
  - a real C++ coding task completed through GitHub Copilot CLI;
  - high-level start/finish against a real private GitLab MR;
  - matching-head GitLab MR pipeline inspection through `actual-coder ci`.

## License

Apache License 2.0. See [LICENSE](LICENSE).
