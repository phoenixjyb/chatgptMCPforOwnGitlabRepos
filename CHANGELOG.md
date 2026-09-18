# Changelog

## 0.2.0-alpha.1 - Unreleased

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
