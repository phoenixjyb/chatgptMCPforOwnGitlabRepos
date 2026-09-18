# Security notes

This project bridges ChatGPT and local coding backends (through ActualCoder) to private source code. Treat the MCP host, local worktrees, coding-agent sessions, and credentials as security-sensitive.

## Never commit

- `.env`
- a real `GITLAB_TOKEN`
- a real `GITLAB_GIT_TOKEN`
- `CONTROL_PLANE_API_KEY`
- `OPENAI_API_KEY`
- private certificates/keys
- copied CI logs or source files containing secrets

## Least privilege

For the read MCP, use a dedicated read-only identity/token and restrict projects with `GITLAB_ALLOWED_PROJECTS`.

For v0.2 Git writes, prefer a separate Git credential with `write_repository` rather than upgrading the read API token to broad `api` scope.

## v0.2 workspace safety

The local coding engine:

- creates isolated worktrees under `GITLAB_WORKSPACE_ROOT`;
- generates feature branches with a configured prefix;
- refuses direct base-branch pushes;
- never force-pushes;
- requires a project allowlist by default;
- blocks file paths escaping the worktree;
- uses dedicated Git operations instead of arbitrary Git shell commands.

## Build/test execution is not a sandbox

`gitlab-agent run` constrains the executable, cwd, timeout, output, and environment, and strips obvious secret variables.

It does **not** provide OS/container filesystem isolation. Repository build scripts are code execution. A malicious Makefile, package lifecycle script, Python test, or binary can attempt to read other host files using absolute paths or make network requests.

Run untrusted repositories in a container/VM or on a disposable host.

## Prompt injection

Repository files, MR descriptions, issues, build output, and CI logs are untrusted content. They can contain instructions intended to manipulate an AI system.

Keep the ChatGPT MCP read-only on personal Pro, review ActualCoder backend actions, preserve project/branch allowlists, and avoid exposing unrelated secrets to build/test processes.

## HTTP GitLab

HTTP can work on a trusted private network, but it does not encrypt the MCP/CLI host-to-GitLab hop. Tokens and repository contents can be observed by an attacker on that network segment. Prefer HTTPS when possible.

## Repository secret scanning

Before pushing or sharing changes, run:

```bash
uv run python scripts/check_repo_secrets.py
```

For a release/security audit, scan the full available Git history:

```bash
uv run python scripts/check_repo_secrets.py --history
```

CI performs the history scan with a full Git checkout. The scanner checks high-signal token formats, private-key blocks, credential-bearing URLs, real-looking Secure MCP tunnel IDs, and developer-specific absolute home paths.

This is defense in depth, not a substitute for credential rotation. If a real secret is ever committed, **revoke/rotate it first**, then rewrite/remove it from repository history before distributing the repository.

## Zero OpenAI model API usage

The repository intentionally contains no OpenAI model SDK dependency and does not call OpenAI model endpoints.

CI checks Python/project code to help preserve this invariant. The Secure MCP Tunnel runtime credential is separate from model API inference.
