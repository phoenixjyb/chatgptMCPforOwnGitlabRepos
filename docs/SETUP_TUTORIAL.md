# ReasonFirst Tutorial: Connect ChatGPT to a Private / Self-Hosted GitLab with MCP

> This document covers the **read-only GitLab bridge** used by ReasonFirst's Reasoning Plane. For the local coding workflow, see [ActualCoder Quickstart](ACTUAL_CODER_QUICKSTART.md). For the product philosophy, see [ReasonFirst Design Philosophy](DESIGN_PHILOSOPHY.md). Team members who read Chinese should use [ONBOARDING_GUIDE_CN.md](ONBOARDING_GUIDE_CN.md) as the main onboarding and usage guide.

This tutorial shows how to connect a self-managed GitLab to ordinary ChatGPT conversations without exposing the GitLab instance directly to the public Internet.

The design uses a read-only Python MCP server plus OpenAI Secure MCP Tunnel.

## 0. Architecture

```text
┌──────────────────────────────┐
│            ChatGPT           │
│  "read this MR / repo / CI" │
└──────────────┬───────────────┘
               │
               │ Secure MCP Tunnel
               │ outbound HTTPS
               ▼
┌──────────────────────────────┐
│      OpenAI tunnel service   │
└──────────────▲───────────────┘
               │
               │ outbound connection maintained by tunnel-client
               │
┌──────────────┴───────────────┐
│       Mac / Linux host       │
│  tunnel-client + server.py   │
└──────────────┬───────────────┘
               │
               │ GitLab REST API
               │ HTTP or HTTPS
               ▼
┌──────────────────────────────┐
│      Self-managed GitLab     │
└──────────────────────────────┘
```

No inbound port on the laptop or GitLab is required by this design.

## 1. Prerequisites

You need:

1. A Mac or Linux machine that can reach your self-hosted GitLab.
2. The same machine must have outbound Internet access to OpenAI over HTTPS.
3. Python 3.10+ and `uv`.
4. A GitLab access token with read permissions.
5. ChatGPT access to custom MCP apps in Developer Mode.
6. An OpenAI Secure MCP Tunnel and a runtime API key for `tunnel-client`.

Useful official documentation:

- ChatGPT Developer Mode and MCP: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI tunnel client: https://github.com/openai/tunnel-client
- Tunnel management: https://platform.openai.com/settings/organization/tunnels
- Runtime API keys: https://platform.openai.com/settings/organization/api-keys
- GitLab token scopes: https://docs.gitlab.com/security/tokens/access_token_scopes/

## 2. Clone and install

```bash
git clone https://github.com/phoenixjyb/reasonFirst.git
cd reasonFirst

uv sync
```

If `uv` is not installed on macOS:

```bash
brew install uv
```

## 3. Create a read-only GitLab token

For a personal token, project token, or group token, give it only the permissions required for reading.

For this MCP server the useful scopes are:

```text
read_api
read_repository
```

Avoid `api` or `write_repository` unless you later deliberately add write tools.

A dedicated service account or narrowly scoped project/group token is preferable to a powerful personal token where your GitLab edition and workflow allow it.

## 4. Configure `.env`

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`:

```bash
GITLAB_BASE_URL=http://gitlab.example.internal
GITLAB_TOKEN=glpat_xxxxxxxxxxxxxxxxx
GITLAB_TRUST_ENV=false
```

For HTTPS GitLab:

```bash
GITLAB_BASE_URL=https://gitlab.example.com
GITLAB_VERIFY_SSL=true
```

### Restrict repositories exposed to ChatGPT

This is strongly recommended:

```bash
GITLAB_ALLOWED_PROJECTS=team/project-a,team/project-b
```

You can use exact `path_with_namespace` values or numeric project IDs.

## 5. Smoke-test the GitLab connection

```bash
uv run python smoke_test.py
```

Expected shape:

```text
GET /user -> 200
Authenticated as: your-user (Your Name)
GET /projects -> 200
- 1: team/project-a
- 2: team/project-b
```

If this fails, do not continue to the MCP/tunnel steps yet. Fix network reachability, token scope, or proxy configuration first.

## 6. Test the MCP server locally

Start MCP Inspector:

```bash
uv run mcp dev server.py
```

The browser Inspector should discover the tools. Connect the stdio server and test, in order:

1. `gitlab_whoami`
2. `list_projects`
3. `get_repository_tree`
4. `get_file`
5. `search_code`
6. MR and CI tools as needed

Example `get_repository_tree` call:

```text
project = team/project-a
ref = main
path =
recursive = false
```

If your default branch is not `main`, leave `ref` empty where supported or use the project's actual branch.

## 7. Create an OpenAI Secure MCP Tunnel

Open:

https://platform.openai.com/settings/organization/tunnels

Create a tunnel and copy its ID:

```text
tunnel_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Make sure the tunnel is available to the ChatGPT workspace/account in which you plan to create the custom app. If ChatGPT later says **No tunnels yet**, check the tunnel's organization/workspace association and permissions.

## 8. Create a runtime API key

Open:

https://platform.openai.com/settings/organization/api-keys

Create a dedicated runtime key for the tunnel client.

For an interactive test session:

```bash
export CONTROL_PLANE_API_KEY="sk-..."
```

Do not commit this key and do not paste it into `.env` if the repository may be shared.

On macOS, for long-term use, consider storing it in Keychain rather than plaintext in `.zshrc`.

## 9. Install `tunnel-client`

On macOS, use the official OpenAI Homebrew path:

```bash
brew install openai/tools/tunnel-client
```

Verify:

```bash
tunnel-client --version
tunnel-client help quickstart
```

The OpenAI repository also publishes platform releases, but Homebrew is the clean path on macOS.

## 10. Initialize a tunnel profile for this stdio MCP

Make the launcher executable:

```bash
chmod +x run_mcp.sh
```

Get the absolute path of the repository:

```bash
pwd
```

Initialize a named profile:

```bash
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile selfhosted-gitlab \
  --tunnel-id tunnel_YOUR_ACTUAL_ID \
  --mcp-command "/absolute/path/to/reasonfirst/run_mcp.sh"
```

The current working directory does not matter because `--mcp-command` is an absolute path and `run_mcp.sh` changes into its own directory.

## 11. Diagnose before running

```bash
tunnel-client doctor \
  --profile selfhosted-gitlab \
  --explain
```

You want:

```text
RESULT ok
```

For a stdio MCP target it is normal for checks such as network reachability or OAuth metadata to show `SKIP`.

## 12. Run the tunnel

```bash
tunnel-client run --profile selfhosted-gitlab
```

Keep this process running while ChatGPT is using the MCP.

The local tunnel UI is normally available at:

```text
http://127.0.0.1:8080/ui
```

## 13. Create the custom app/plugin in ChatGPT

In ChatGPT web:

1. Enable **Developer Mode** under Settings → Apps → Advanced settings (wording can vary by rollout).
2. In Settings → Apps/Plugins, create a new custom app/plugin.
3. Give it a name such as `My GitLab MCP`.
4. Under **Connection**, select **Tunnel**.
5. Choose the tunnel created above.
6. For this server, choose **None / no user-facing authentication** if offered. The GitLab token stays server-side on the MCP host.
7. Accept the custom-MCP risk warning after reviewing the server.
8. Scan/discover tools and create the app.

If the Tunnel picker says **No tunnels yet** even though `tunnel-client run` is healthy, the most common cause is that the tunnel exists in the Platform organization but is not associated with the ChatGPT workspace/account currently in use.

## 14. End-to-end validation in ChatGPT

Try these prompts in order:

```text
Use My GitLab MCP and tell me which GitLab user is authenticated.
```

```text
List the GitLab projects available through My GitLab MCP.
```

```text
Show me the root tree of team/project-a on its default branch.
```

```text
Read README.md from team/project-a and summarize it.
```

```text
Inspect the architecture of team/project-a. Read the relevant files rather than only searching filenames.
```

For CI:

```text
Inspect the most recent failed pipeline, identify failed jobs, read the relevant job log, and explain the likely root cause.
```

At this point the full path is proven:

```text
ChatGPT → Secure MCP Tunnel → local MCP server → self-hosted GitLab API
```

## 15. macOS Keychain for the OpenAI runtime key (optional)

Instead of putting a secret directly into `.zshrc`:

```bash
security add-generic-password \
  -a "$USER" \
  -s "openai-gitlab-mcp-tunnel" \
  -w "sk-..." \
  -U
```

Load it only when needed:

```bash
export CONTROL_PLANE_API_KEY="$(
  security find-generic-password \
    -a "$USER" \
    -s "openai-gitlab-mcp-tunnel" \
    -w 2>/dev/null
)"
```

Verify only the length:

```bash
echo ${#CONTROL_PLANE_API_KEY}
```

Do not print the key itself.

## 16. HTTP vs HTTPS on the GitLab side

This MCP supports either:

```text
http://gitlab.example.internal
```

or:

```text
https://gitlab.example.com
```

If your current GitLab uses HTTP, the setup can still work because the OpenAI tunnel terminates at the MCP host; the MCP host then calls GitLab independently.

However, HTTP means the GitLab access token and repository contents are not TLS-protected between the MCP host and GitLab. Use only on a trusted private network/VPN and migrate to HTTPS when practical.

When you later switch GitLab to HTTPS, normally only this value needs to change:

```bash
GITLAB_BASE_URL=https://gitlab.example.com
```

The MCP tool contract and ChatGPT plugin do not need to change.

## 17. Production hardening

For a first prototype, a MacBook is fine. For team/24x7 use, move the same code to an always-on machine and add process supervision.

Recommended controls:

- dedicated low-privilege GitLab identity/token;
- `GITLAB_ALLOWED_PROJECTS` allowlist;
- HTTPS to GitLab when available;
- token expiration/rotation;
- macOS Keychain or a proper secret manager for runtime secrets;
- monitor tunnel and MCP logs;
- keep tools read-only unless there is a concrete need for writes.
