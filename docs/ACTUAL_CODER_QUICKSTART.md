# ActualCoder Quickstart

> 团队成员如需完整安装、凭证、安全、日常开发、MR 恢复和故障排查流程，请使用 [TEAM_GUIDE_CN.md](TEAM_GUIDE_CN.md)。

ActualCoder is the agent-neutral local coding layer in this repository. The older `codingagent` CLI remains a compatibility alias for existing workflows.

It separates:

- **coding backend** — Codex CLI, GitHub Copilot CLI, or future agents;
- **workspace / GitLab control** — `gitlab-agent`, which owns isolated worktrees,
  tests, diffs, commits, feature-branch push, Merge Request creation/update, and recovery.

The project itself makes no OpenAI model API calls.

## 1. Install

From the repository `main` branch:

```bash
git checkout main
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
actual-coder --help
actual-coder config
actual-coder agents
gitlab-agent --help
```

`actual-coder agents` only checks whether supported CLI executables are installed.
It does not launch Codex/Copilot, check authentication, or consume model quota.

## 2. Start a task with Codex

```bash
actual-coder task team/project-a \
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

For Codex, the older `codex_command` / `codex_prompt` aliases remain available for compatibility.

## 3. Start a task with GitHub Copilot CLI

```bash
actual-coder task team/project-a \
  --agent copilot \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the timeout bug and add regression coverage"
```

The handoff command will look like:

```bash
cd ~/.local/share/chatgpt-gitlab-mcp/worktrees/<workspace-id> && copilot
```

ActualCoder does not require the repository to be hosted on GitHub. Copilot works
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
actual-coder task team/project-a \
  --agent codex \
  --task fix-timeout \
  --goal "Implement the initial fix"
```

Then later resume the same workspace with Copilot:

```bash
actual-coder resume "$WS" \
  --agent copilot \
  --goal "Review the previous change, address feedback, and rerun tests"
```

Or switch back:

```bash
actual-coder resume "$WS" \
  --agent codex \
  --goal "Finish the remaining test failure"
```

## 6. Recover an existing remote MR

If the local worktree was cleaned up:

```bash
actual-coder checkout-mr team/project-a 123 \
  --agent copilot \
  --goal "Resume this existing MR and address review feedback"
```

ActualCoder reads the MR metadata through the configured GitLab API token,
reconstructs the source branch as a managed worktree, remembers the existing MR
URL, and emits a new agent handoff.

You can equally recover it for Codex:

```bash
actual-coder checkout-mr team/project-a 123 \
  --agent codex \
  --goal "Continue this existing MR"
```

## 7. Safety model

ActualCoder v0.3 keeps and extends the previously validated safety boundaries:

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
actual-coder agents
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

v0.3.0 supports:

```text
codex
copilot
```

The backend mapping is intentionally small and explicit. Future agents can be added
without changing the GitLab/worktree machinery.
