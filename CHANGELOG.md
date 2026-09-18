# Changelog

## 0.2.0-alpha.4 - Unreleased

- Introduce **CodingAgent** as the agent-neutral user-facing coding layer.
- Add the `codingagent` console command while retaining `gitlab-agent` as the lower-level GitLab/worktree controller.
- Add first-class `--agent codex|copilot` selection for task, resume, branch recovery, and MR recovery handoffs.
- Replace Codex-specific handoff fields with `agent`, `agent_command`, and `agent_prompt`; keep Codex aliases for compatibility.
- Add a CodingAgent quickstart and backend-handoff regression tests.
- Verify both packaged CLIs in CI.
- Real coding validation already includes a GitHub Copilot CLI C++ change pushed to an existing GitLab MR.

## 0.2.0-alpha.3

- Add `checkout-branch` to reconstruct a managed local worktree from an existing remote feature branch.
- Add `checkout-mr` to resume a same-project GitLab MR after local cleanup/restart.
- Preserve existing MR URL/source branch state so `push-update` continues the same MR.
- Refuse duplicate local worktrees for a branch that is already checked out.
- Add GitLab MR API helper with the same direct-network/proxy-bypass behavior.
- Add tests for branch reconstruction, continued pushes, and MR API lookup behavior.

## 0.2.0-alpha.2

- Add user-level editable installation for `gitlab-agent`.
- Add stable config lookup via `~/.config/gitlab-agent/.env`.
- Add `config`, `task`, `resume`, and `path` helper commands.
- Add Codex-ready handoff prompts from `task` / `resume`.
- Add `push-update` for repeated commit/push cycles on an existing MR branch.
- Add regression tests proving a second commit updates the same remote feature branch.
- Keep zero OpenAI model API usage as a CI-enforced invariant.

## 0.2.0-alpha.1

- Keep the ChatGPT MCP read-only for the personal-Pro workflow.
- Add a reusable local coding engine for Codex/terminal use.
- Add isolated cached Git repositories and per-task worktrees.
- Add safe workspace read/write and unified-patch operations.
- Add allowlisted build/test execution with timeout/output limits and secret scrubbing.
- Add dedicated commit and feature-branch push operations.
- Add first-push GitLab Merge Request creation via Git push options.
- Add explicit project allowlist and branch-prefix safety policy.
- Add `gitlab-agent` JSON CLI.
- Add local Git workflow tests.
- Add CI invariant preventing accidental OpenAI model API integration.
- End-to-end smoke-tested against a real private self-hosted GitLab: isolated worktree → local edit → controlled command → diff → commit → feature-branch push → Merge Request creation.

## 0.1.0 - Initial public version

- Read-only MCP server for self-managed GitLab.
- Repository tree and file reading.
- Project code search.
- Merge request metadata and diffs.
- CI pipeline, job, and job-log inspection.
- Project allowlist.
- Direct-access mode that ignores host proxy variables by default.
- GitLab API smoke test.
- OpenAI Secure MCP Tunnel launcher.
- English and Chinese setup documentation.
- Troubleshooting notes based on an end-to-end working deployment.
- GitHub Actions syntax/dependency validation.
