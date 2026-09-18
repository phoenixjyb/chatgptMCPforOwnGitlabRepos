# 团队 OpenAI Secure MCP Tunnel 配置指南

> 面向每位拥有 ChatGPT Pro 的团队成员。目标：每人用自己的 Tunnel + Runtime Key，把本机/内网的只读 GitLab MCP 安全接入 ChatGPT；ActualCoder 的本地写代码流程与 Tunnel 分离。

## 1. 先分清三种身份/凭证

### ChatGPT Pro

当前 Pro 可以在 Developer Mode 中连接 read/fetch 类型的自定义 MCP；full MCP write/modify 当前面向 Business / Enterprise / Edu。

本项目因此保持：

```text
ChatGPT Pro MCP = GitLab 只读
ActualCoder     = 本地 coding + GitLab feature branch / MR
```

### OpenAI Platform Tunnel

Tunnel ID 与 Runtime API Key 来自 OpenAI Platform，不等同于 ChatGPT Pro 订阅。

常用权限：

- 运行 tunnel：`Tunnels Read + Use`；
- 创建/修改 tunnel：`Tunnels Read + Manage`。

### GitLab

- `GITLAB_TOKEN`：建议 read_api + read_repository；
- `GITLAB_GIT_TOKEN`：建议 write_repository。

---

## 2. 团队推荐：每人一个 Tunnel

不要多人长期共享同一个 runtime key。建议每个成员/开发机一个 tunnel，例如：

```text
gitlab-mcp-alice-mac
gitlab-mcp-bob-linux
gitlab-mcp-charlie-windows
```

这样方便撤销、轮换、定位故障。

Tunnel ID 不是 bearer secret，但属于内部部署信息，不要写进公共仓库。

---

## 3. 获取 Tunnel ID

打开：

https://platform.openai.com/settings/organization/tunnels

创建 Tunnel，并记录：

```text
CONTROL_PLANE_TUNNEL_ID=tunnel_YOUR_ACTUAL_ID
```

如果成员自己不能创建，让 Platform 管理员创建，并确保：

- tunnel 关联正确 ChatGPT workspace；
- 成员有 `Tunnels Read + Use`。

---

## 4. 获取 Runtime API Key

打开：

https://platform.openai.com/settings/organization/api-keys

创建 Runtime API Key，推荐：

```text
Restricted
Tunnels Read + Use
```

得到的 key 用作：

```text
CONTROL_PLANE_API_KEY
```

它用于 `tunnel-client doctor` / `run` / poll，不应写入 Git。

普通成员通常不需要 `OPENAI_ADMIN_KEY`；Admin Key 只在用 CLI 管理 tunnel CRUD 时需要。

---

## 5. 安装 tunnel-client

### macOS

官方推荐：

```bash
brew install openai/tools/tunnel-client
tunnel-client --version
tunnel-client help quickstart
```

### Linux

从 Platform Tunnels 页面或官方 release 获取 supported binary：

https://github.com/openai/tunnel-client/releases/latest

也可源码构建：

```bash
git clone https://github.com/openai/tunnel-client.git
cd tunnel-client
go build -o bin/tunnel-client ./cmd/client
```

### Windows

从 Platform Tunnels 页面或官方 release 获取 `tunnel-client.exe`。

也可源码构建：

```powershell
git clone https://github.com/openai/tunnel-client.git
Set-Location tunnel-client
go build -o bin\tunnel-client.exe .\cmd\client
```

---

## 6. 本项目在三个平台上的 launcher

### macOS / Linux

```bash
git clone https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos.git
cd chatgptMCPforOwnGitlabRepos
uv sync
bash scripts/install_user.sh
```

MCP launcher：`run_mcp.sh`。

### Windows PowerShell

```powershell
git clone https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos.git
Set-Location chatgptMCPforOwnGitlabRepos
uv sync
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_user.ps1
```

MCP launcher：`run_mcp.ps1`。

---

## 7. GitLab Token 保存位置

ActualCoder、smoke test、MCP server 统一支持：

### macOS / Linux

```text
~/.config/gitlab-agent/.env
```

```bash
chmod 700 ~/.config/gitlab-agent
chmod 600 ~/.config/gitlab-agent/.env
```

### Windows

```text
%USERPROFILE%\.config\gitlab-agent\.env
```

PowerShell 创建：

```powershell
$ConfigDir = Join-Path $HOME ".config\gitlab-agent"
$ConfigFile = Join-Path $ConfigDir ".env"
New-Item -ItemType Directory -Force $ConfigDir | Out-Null
Copy-Item .env.example $ConfigFile
```

建议用 Windows ACL 将该文件限制为当前用户可访问。

---

## 8. CONTROL_PLANE_API_KEY 保存位置

不要放在仓库 `.env`、README、shell history 或 tunnel profile 明文中。

tunnel-client profile 支持：

```yaml
control_plane:
  api_key: env:CONTROL_PLANE_API_KEY
```

以及：

```yaml
control_plane:
  api_key: file:/protected/path/runtime.key
```

### macOS：Keychain

```bash
read -s -p "CONTROL_PLANE_API_KEY: " TUNNEL_RUNTIME_KEY
echo
security add-generic-password -a "$USER" -s "openai-tunnel-runtime" -w "$TUNNEL_RUNTIME_KEY" -U
unset TUNNEL_RUNTIME_KEY
```

使用前：

```bash
export CONTROL_PLANE_API_KEY="$(security find-generic-password -a "$USER" -s "openai-tunnel-runtime" -w)"
```

### Linux：受保护 secret file

```bash
mkdir -p ~/.config/tunnel-client/secrets
chmod 700 ~/.config/tunnel-client/secrets
umask 077
read -s -p "CONTROL_PLANE_API_KEY: " CONTROL_PLANE_API_KEY
echo
printf '%s' "$CONTROL_PLANE_API_KEY" > ~/.config/tunnel-client/secrets/runtime.key
unset CONTROL_PLANE_API_KEY
chmod 600 ~/.config/tunnel-client/secrets/runtime.key
```

profile 中引用：

```yaml
control_plane:
  api_key: file:/home/YOUR_USER/.config/tunnel-client/secrets/runtime.key
```

### Windows：DPAPI

保存：

```powershell
$SecretDir = Join-Path $HOME ".config\openai-tunnel"
$SecretFile = Join-Path $SecretDir "runtime-key.dpapi"
New-Item -ItemType Directory -Force $SecretDir | Out-Null
Read-Host "CONTROL_PLANE_API_KEY" -AsSecureString | ConvertFrom-SecureString | Set-Content $SecretFile
```

每次需要运行 tunnel 时加载到当前 session：

```powershell
$SecretFile = Join-Path $HOME ".config\openai-tunnel\runtime-key.dpapi"
$secure = Get-Content $SecretFile | ConvertTo-SecureString
$env:CONTROL_PLANE_API_KEY = (New-Object System.Net.NetworkCredential("", $secure)).Password
```

---

## 9. 初始化 Profile

Profile 默认位于 `~/.config/tunnel-client/<profile>.yaml`。

### macOS / Linux

```bash
PROFILE=selfhosted-gitlab
TUNNEL_ID=tunnel_YOUR_ID
MCP_COMMAND="$(pwd)/run_mcp.sh"

tunnel-client init --sample sample_mcp_stdio_local --profile "$PROFILE" --tunnel-id "$TUNNEL_ID" --mcp-command "$MCP_COMMAND"
```

### Windows PowerShell

```powershell
$Profile = "selfhosted-gitlab"
$TunnelId = "tunnel_YOUR_ID"
$McpScript = (Resolve-Path ".\run_mcp.ps1").Path
$McpCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $McpScript

tunnel-client.exe init --sample sample_mcp_stdio_local --profile $Profile --tunnel-id $TunnelId --mcp-command $McpCommand
```

---

## 10. Doctor / Run

### macOS / Linux

```bash
tunnel-client doctor --profile selfhosted-gitlab --explain
tunnel-client run --profile selfhosted-gitlab
```

### Windows

```powershell
tunnel-client.exe doctor --profile selfhosted-gitlab --explain
tunnel-client.exe run --profile selfhosted-gitlab
```

Doctor 目标：

```text
RESULT ok
```

本地 MCP 本身应先通过：

```bash
uv run python smoke_test.py
uv run mcp dev server.py
```

---

## 11. ChatGPT Pro 连接步骤

每位成员在自己的 ChatGPT Pro：

1. Settings；
2. Apps；
3. Advanced Settings / Developer Mode；
4. 打开 Developer Mode；
5. 创建 Custom MCP App；
6. Connection 选择 Tunnel；
7. 选择自己的 tunnel（或按 UI 填 tunnel ID）；
8. 本项目 MCP 不需要额外 user OAuth；
9. Discover / Scan tools；
10. 保存启用。

当前 Pro 适合本项目的 read-only MCP；真实写代码继续走 ActualCoder。

建议依次验证：

```text
gitlab_whoami
list_projects
get_file
```

---

## 12. Tunnel 看得到但 ChatGPT 找不到

检查：

1. tunnel 是否关联正确 ChatGPT workspace；
2. 用户是否有 `Tunnels Read + Use`；
3. Runtime API Key 是否有 `Tunnels Read + Use`；
4. `doctor --explain` 是否通过；
5. `run` 是否正在运行；
6. 新建 tunnel 后等待短时间再刷新 Apps 页面。

不要通过共享同事 runtime key 来绕过权限问题。

---

## 13. 团队 Secret 保存建议

| 平台 | GitLab Token | Tunnel Runtime Key |
|---|---|---|
| macOS | `~/.config/gitlab-agent/.env` + chmod 600 | Keychain |
| Linux | `~/.config/gitlab-agent/.env` + chmod 600 | protected file / Secret Service |
| Windows | `%USERPROFILE%\.config\gitlab-agent\.env` + restricted ACL | DPAPI / enterprise secret manager |

如果公司已有 Vault、1Password CLI、Azure Key Vault、AWS Secrets Manager 等，优先采用公司标准方案。

禁止：

- commit `.env`；
- commit runtime key；
- 群聊发送 token；
- 公共仓库写真实 tunnel ID / 内网域名/IP；
- 普通开发者长期使用 `OPENAI_ADMIN_KEY`；
- 多人共享一个 runtime key。

---

## 14. 每位成员 Checklist

- [ ] ChatGPT Pro 可用；
- [ ] OpenAI Platform 可访问；
- [ ] 有自己的 Tunnel；
- [ ] 有 `Tunnels Read + Use`；
- [ ] 创建 Restricted Runtime API Key；
- [ ] Runtime Key 已用 OS 合适方式保存；
- [ ] tunnel-client 已安装；
- [ ] GitLab token/allowlist 已配置；
- [ ] `smoke_test.py` 成功；
- [ ] `doctor --explain` 成功；
- [ ] tunnel runtime 正在运行；
- [ ] ChatGPT Developer Mode 已打开；
- [ ] MCP tools discover 成功；
- [ ] `gitlab_whoami` 成功；
- [ ] ActualCoder 至少一个 backend 可用。

---

## 官方参考

- ChatGPT Developer Mode / MCP：
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI Tunnels：
  https://platform.openai.com/settings/organization/tunnels
- Runtime API Keys：
  https://platform.openai.com/settings/organization/api-keys
- tunnel-client：
  https://github.com/openai/tunnel-client
- End User Guide：
  https://github.com/openai/tunnel-client/blob/master/docs/end-user-guide.md
- Permissions：
  https://github.com/openai/tunnel-client/blob/master/docs/permissions.md
- Configuration：
  https://github.com/openai/tunnel-client/blob/master/docs/configuration.md

本项目：

- [团队安装与日常使用](TEAM_GUIDE_CN.md)
- [ActualCoder Quickstart](ACTUAL_CODER_QUICKSTART.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security](../SECURITY.md)
