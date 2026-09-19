# CodingAgent Quickstart (Compatibility Alias)

> **ReasonFirst** is the project/product. **ActualCoder** / `actual-coder` is its primary local orchestration engine/CLI.
>
> `codingagent` is the former CLI name and remains only as a compatibility alias. See [ACTUAL_CODER_QUICKSTART.md](ACTUAL_CODER_QUICKSTART.md) and [ReasonFirst Design Philosophy](DESIGN_PHILOSOPHY.md).

CodingAgent is the former name of the agent-neutral local coding layer now used inside ReasonFirst.

It separates:

- **coding backend** — Codex CLI, GitHub Copilot CLI, or future agents;
- **workspace / GitLab control** — `gitlab-agent`, which owns isolated worktrees,
  tests, diffs, commits, feature-branch push, Merge Request creation/update, and recovery.

The project itself makes no OpenAI model API calls.

## 1. Install

From the `v0.2.0-dev` branch:

```bash
git pull
uv sync
bash scripts/install_user.sh
```

Copy the working configuration once:

```bash
mkdir -p ~/.config/gitlab-agent
cp .env ~/.config/gitlab-agent/.env
chmod 700 ~/.config/gitlab-agent
chmod 600 ~/.config/gitlab-agent/.env
```

Verify from any directory:

```bash
codingagent --help
codingagent config
codingagent agents
gitlab-agent --help
```

`codingagent agents` only checks whether supported CLI executables are installed.
It does not launch Codex/Copilot, check authentication, or consume model quota.

## 2. Start a task with Codex

```bash
codingagent task team/project-a \
  --agent codex \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

The JSON result includes:

```text
workspace
worktree_path
agent: codex
agent_command
agent_prompt
```

For Codex, alpha.4 also keeps the older `codex_command` / `codex_prompt`
aliases for compatibility.

## 3. Start a task with GitHub Copilot CLI

```bash
codingagent task team/project-a \
  --agent copilot \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

The handoff command will look like:

```bash
cd ~/.local/share/chatgpt-gitlab-mcp/worktrees/<workspace-id> && copilot
```

CodingAgent does not require the repository to be hosted on GitHub. Copilot works
against the local worktree while `gitlab-agent` continues to manage the
self-hosted GitLab branch/MR lifecycle.

## 4. Agent-neutral lifecycle

After either backend edits the worktree:

```bash
WS=<workspace-id>

gitlab-agent status "$WS"
gitlab-agent run "$WS" -- <allowed-test-command>
gitlab-agent diff "$WS"
gitlab-agent commit "$WS" -m "Describe the change"
```

First push + MR creation:

```bash
gitlab-agent push-mr "$WS" \
  --target main \
  --title "Describe the change" \
  --description-file /tmp/mr.md
```

Further iterations on the same MR:

```bash
gitlab-agent push-update "$WS"
```

## 5. Resume with a different coding backend

The backend is not stored as a permanent property of the workspace. You can switch
agents between iterations.

For example, start with Codex:

```bash
codingagent task team/project-a \
  --agent codex \
  --task fix-timeout \
  --goal "Implement the initial fix"
```

Then later resume the same workspace with Copilot:

```bash
codingagent resume "$WS" \
  --agent copilot \
  --goal "Review the previous change, address feedback, and rerun tests"
```

Or switch back:

```bash
codingagent resume "$WS" \
  --agent codex \
  --goal "Finish the remaining test failure"
```

## 6. Recover an existing remote MR

If the local worktree was cleaned up:

```bash
codingagent checkout-mr team/project-a 123 \
  --agent copilot \
  --goal "Resume this existing MR and address review feedback"
```

CodingAgent reads the MR metadata through the configured GitLab API token,
reconstructs the source branch as a managed worktree, remembers the existing MR
URL, and emits a new agent handoff.

You can equally recover it for Codex:

```bash
codingagent checkout-mr team/project-a 123 \
  --agent codex \
  --goal "Continue this existing MR"
```

## 7. Safety model

CodingAgent keeps the previously validated v0.2 boundaries:

- explicit project allowlist by default;
- generated / reconstructed branches must use the configured safe branch prefix;
- no direct base-branch push;
- no force push;
- no merge / approve / remote-branch-delete operation;
- build/test runner uses an executable allowlist and `shell=False`;
- obvious secret/token variables are stripped from runner subprocesses;
- Git credentials are passed through temporary askpass rather than embedded in remotes;
- the host runner is constrained execution, not a VM/container sandbox.

## 8. Check installed coding backends

```bash
codingagent agents
```

Example:

```json
{
  "agents": [
    {
      "agent": "codex",
      "executable": "codex",
      "installed": true,
      "path": "/path/to/codex",
      "authentication_checked": false
    },
    {
      "agent": "copilot",
      "executable": "copilot",
      "installed": true,
      "path": "/path/to/copilot",
      "authentication_checked": false
    }
  ]
}
```

## 9. Current backends

Alpha.4 supports:

```text
codex
copilot
```

The backend mapping is intentionally small and explicit. Future agents can be added
without changing the GitLab/worktree machinery.
