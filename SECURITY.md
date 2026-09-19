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

For ActualCoder Git writes, prefer a separate Git credential with `write_repository` rather than upgrading the read API token to broad `api` scope.

## Workspace safety

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

It does **not** provide OS/container filesystem isolation. Repository build scripts are code execution. A malicious Makefile, package lifecycle script, Python test, package-manager lifecycle hook, or binary can attempt to read other host files using absolute paths or make network requests.

The same boundary applies to v0.3 `.actualcoder.yaml` validation commands. The repository contract cannot expand `GITLAB_ALLOWED_EXECUTABLES`, but an already-approved executable such as `uv`, `python`, `make`, `npm`, or `pytest` can still execute repository-controlled code.

Therefore:

- review/protect `.actualcoder.yaml` like build/CI configuration;
- use `actual-coder project-config PROJECT --validate` to inspect the effective contract;
- understand that `actual-coder finish --dry-run` means **no Git commit/push**, not “no code execution” — configured validation commands still run;
- run untrusted or externally supplied repositories in a container/VM or on a disposable host.

## Prompt injection

Repository files, MR descriptions, issues, build output, project-contract instructions, and CI logs can contain instructions intended to manipulate an AI system.

v0.3 applies explicit trust boundaries:

- `.actualcoder.yaml` guidance is labeled repository-owned and subordinate to the user goal / ActualCoder rules;
- `.actualcoder.yaml` is a built-in protected path in `actual-coder finish`;
- project contracts are size/cardinality bounded and reject duplicate YAML keys;
- CI logs are labeled untrusted diagnostic data, ANSI-cleaned, size-capped, and credential-redacted before entering a coding-agent prompt;
- `resume --from-ci` refuses CI whose pipeline SHA does not match the workspace HEAD.

These are defense-in-depth controls, not a guarantee that model behavior cannot be influenced by malicious text. Keep the ChatGPT MCP read-only on personal Pro, review ActualCoder backend actions, preserve project/branch allowlists, and avoid exposing unrelated secrets to build/test processes.

## Workspace concurrency and state

Managed workspace state is local and persistent, but v0.3 does not yet implement per-workspace process locking. Do not run concurrent mutating ActualCoder/gitlab-agent commands against the same workspace from multiple terminals/processes.

`actual-coder finish` fingerprints the reviewed post-validation workspace state and re-checks it immediately before commit/push, which closes the review-to-write change window for that workflow. General workspace locking/crash-recovery remains planned for a later release.

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
