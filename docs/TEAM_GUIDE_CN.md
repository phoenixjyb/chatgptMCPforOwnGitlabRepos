# 团队安装、配置与使用完整指南（ActualCoder + 自建 GitLab）

> 适用对象：需要在 **私有 / 自建 GitLab** 上使用 Codex CLI、GitHub Copilot CLI 等本地 coding agent 进行真实代码开发的团队成员。
>
> 本文是团队使用的**推荐主入口**。日常开发优先阅读本文；ChatGPT 只读 MCP 的详细配置可参考 [SETUP_TUTORIAL_CN.md](SETUP_TUTORIAL_CN.md)。

---

## 0. 这套工具解决什么问题

目标是把“AI 负责写代码”和“GitLab / Git 操作”拆开：

```text
Codex CLI ───────┐
Copilot CLI ─────┼──► ActualCoder
未来其他 Agent ──┘        │
                           ▼
                     gitlab-agent
                           │
                           ├── 独立 worktree
                           ├── build / test
                           ├── diff
                           ├── commit
                           ├── push / push-update
                           ├── 创建 MR
                           └── 从 MR / remote branch 恢复工作区
                                │
                                ▼
                         公司自建 GitLab
```

同时，仓库还提供一个**只读 ChatGPT MCP**：

```text
ChatGPT
   │
   │ read-only MCP
   ▼
Secure MCP Tunnel
   │
   ▼
server.py
   │
   ▼
自建 GitLab
```

两条链路可以同时使用：

- ChatGPT：读代码、读 MR、读 pipeline/job/log、做架构分析；
- ActualCoder：把真实 coding task 交给 Codex / Copilot，并通过安全的 GitLab 工作流提交结果。

---

# 第一部分：团队成员第一次安装

## 1. 环境要求

支持：

| 平台 | ActualCoder / gitlab-agent | ChatGPT MCP launcher | tunnel-client |
|---|---|---|---|
| macOS | 原生支持 | `run_mcp.sh` | 官方 Homebrew |
| Linux | 原生支持 | `run_mcp.sh` | 官方 binary / source build |
| Windows 10/11 | 原生 PowerShell 支持 | `run_mcp.ps1` | `tunnel-client.exe` |
| Windows + WSL2 | 支持（按 Linux 使用） | `run_mcp.sh` | Linux binary |

基础要求：

- Git；
- Python 3.10+；
- `uv`；
- 能访问公司 GitLab 的网络环境 / VPN；
- 至少安装一种 coding backend：
  - Codex CLI；
  - GitHub Copilot CLI。

安装 `uv` 时使用 uv 官方对应平台安装方式；macOS 也可：

```bash
brew install uv
```

macOS / Linux 验证：

```bash
git --version
python3 --version
uv --version
```

Windows PowerShell 验证：

```powershell
git --version
python --version
uv --version
```

---

## 2. 克隆仓库

```bash
git clone https://github.com/phoenixjyb/chatgptMCPforOwnGitlabRepos.git
cd chatgptMCPforOwnGitlabRepos
```

团队日常使用直接使用 `main`：

```bash
git checkout main
git pull
```

新成员首次 clone 后默认就是 `main`，通常不需要额外切分支。

> 团队建议统一使用 `main` 或固定 release tag，不要每个人长期停留在不同 commit。

---

## 3. 安装 Python 依赖

```bash
uv sync
```

快速检查：

```bash
uv run actual-coder --help
uv run gitlab-agent --help
```

---

# 第二部分：GitLab 凭证与配置

## 4. 推荐的 Token 设计

推荐使用**两个 token**，职责分开。

### 4.1 API / 只读 Token

环境变量：

```text
GITLAB_TOKEN
```

推荐权限：

```text
read_api
read_repository
```

用途：

- ChatGPT read-only MCP；
- ActualCoder 的 GitLab metadata 查询；
- `checkout-mr` 查询 MR source/target branch。

### 4.2 Git 写入 Token

环境变量：

```text
GITLAB_GIT_TOKEN
```

推荐权限：

```text
write_repository
```

用途：

- clone / fetch；
- push feature branch；
- `push-mr`；
- `push-update`。

如果没有单独配置 `GITLAB_GIT_TOKEN`，当前实现会退回使用 `GITLAB_TOKEN`。

**团队推荐仍然分开两个 token。**

---

## 5. 创建本地配置

复制模板：

```bash
cp .env.example .env
chmod 600 .env
```

编辑：

```bash
vim .env
```

最低建议配置：

```bash
GITLAB_BASE_URL=http://gitlab.example.internal

GITLAB_TOKEN=YOUR_READ_TOKEN
GITLAB_GIT_TOKEN=YOUR_WRITE_TOKEN
GITLAB_GIT_USERNAME=oauth2

GITLAB_ALLOWED_PROJECTS=team/project-a,team/project-b

GITLAB_VERIFY_SSL=true
GITLAB_TRUST_ENV=false
GITLAB_GIT_TRUST_ENV=false

GITLAB_REQUIRE_WRITE_ALLOWLIST=true
GITLAB_WORKSPACE_ROOT=~/.local/share/chatgpt-gitlab-mcp
GITLAB_BRANCH_PREFIX=chatgpt/
GITLAB_DEFAULT_BASE_REF=main
```

### 为什么要配置 `GITLAB_ALLOWED_PROJECTS`

这是写操作的重要保护层。

例如：

```bash
GITLAB_ALLOWED_PROJECTS=team/project-a,team/project-b
```

ActualCoder 默认只能为这两个项目创建 / 恢复工作区。

不要为了省事在团队环境中关闭 allowlist。

---

## 6. HTTP GitLab 的注意事项

工具支持：

```text
http://gitlab.example.internal
```

但 HTTP 不是加密链路。

如果 GitLab 目前仍为 HTTP：

- 必须位于可信内网 / VPN；
- token 使用最小权限；
- 不要在公共 Wi-Fi / 不可信网络直接连接；
- 条件成熟后优先迁移 HTTPS。

---

# 第三部分：安装 ActualCoder 到用户环境

## 7. 安装全局 CLI

### macOS / Linux

在仓库根目录：

```bash
bash scripts/install_user.sh
```

然后把工作配置放到稳定位置：

```bash
mkdir -p ~/.config/gitlab-agent
cp .env ~/.config/gitlab-agent/.env

chmod 700 ~/.config/gitlab-agent
chmod 600 ~/.config/gitlab-agent/.env
```

### Windows PowerShell

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_user.ps1

$ConfigDir = Join-Path $HOME ".config\gitlab-agent"
$ConfigFile = Join-Path $ConfigDir ".env"
New-Item -ItemType Directory -Force $ConfigDir | Out-Null
Copy-Item .env $ConfigFile
```

Windows 建议再用 ACL 将 `.env` 限制为当前用户访问；完整命令见
[OpenAI Tunnel / 跨平台凭证配置指南](OPENAI_TUNNEL_TEAM_SETUP_CN.md)。

配置读取优先级：

```text
1. GITLAB_AGENT_ENV_FILE
2. ~/.config/gitlab-agent/.env
3. 当前目录 .env
```

推荐团队成员使用第 2 种。

---

## 8. 验证安装

```bash
actual-coder --help
actual-coder config
actual-coder agents
actual-coder doctor
gitlab-agent --help
```

推荐每位成员首次安装后先运行：

```bash
actual-coder doctor
```

如果当前不在公司网络 / VPN，可先：

```bash
actual-coder doctor --offline
```

`doctor` 不会修改 GitLab，也不会调用 Codex / Copilot 模型；它只做环境、配置和连通性诊断。

状态含义：

```text
pass  = 正常
warn  = 可以继续，但建议处理
fail  = 核心条件不满足；doctor 返回非 0
skip  = 可选项未配置或显式跳过
```

重点检查项包括：

- Python / Git / uv；
- Codex / Copilot 是否至少存在一个；
- tunnel-client（可选）；
- 配置文件与权限；
- GitLab URL / Token；
- 项目 allowlist；
- proxy 策略；
- workspace root 是否可写；
- 磁盘空间；
- stale / malformed workspace state；
- GitLab API 登录是否成功。

### 8.1 项目级 `.actualcoder.yaml`

项目可以在仓库根目录放置：

```text
.actualcoder.yaml
```

它用于声明项目自己的 coding contract，例如：

- 默认 base branch；
- Codex / Copilot 的偏好顺序；
- validation command；
- protected paths；
- project-specific instructions；
- 项目依赖的 executable；
- MR target branch / title prefix。

团队成员可以在**不创建 worktree**的情况下验证远端配置：

```bash
actual-coder project-config team/project-a --validate
```

在提交到项目之前，也可以先用本地候选文件验证：

```bash
actual-coder project-config team/project-a \
  --file .actualcoder.example.yaml \
  --validate
```

这一步不会访问目标项目的 `.actualcoder.yaml`，只会用当前用户策略检查本地候选文件。

指定 ref：

```bash
actual-coder project-config team/project-a \
  --ref develop \
  --validate
```

如果项目没有 `.actualcoder.yaml`，这是合法情况；ActualCoder 会继续使用用户级/default 配置。

安全规则：repository-owned config **不能自己扩展 executable allowlist**。例如项目写：

```yaml
validation:
  commands:
    - argv: [bash, -c, something]
```

但开发者的 `GITLAB_ALLOWED_EXECUTABLES` 没有允许 `bash`，则：

```bash
actual-coder project-config ... --validate
```

必须失败。

示例见仓库根目录：

```text
.actualcoder.example.yaml
```

其中：

```bash
actual-coder config
```

只显示：

- token 是否已配置；
- GitLab URL；
- allowlist；
- workspace root；
- branch prefix；
- command allowlist；

**不会打印 token 内容。**

`actual-coder agents` 只检查 CLI 是否存在：

```json
{
  "agents": [
    {
      "agent": "codex",
      "installed": true,
      "authentication_checked": false
    },
    {
      "agent": "copilot",
      "installed": true,
      "authentication_checked": false
    }
  ]
}
```

它不会调用模型，也不会消耗模型额度。

---

# 第四部分：准备 Coding Backend

## 9. Codex CLI

确保：

```bash
codex
```

可以正常启动并已登录。

如果希望使用 ChatGPT 订阅额度而不是 API 计费，应使用 Codex CLI 的 ChatGPT 登录方式，不要给项目配置 `OPENAI_API_KEY`。

ActualCoder 本身不会调用 OpenAI model API。

---

## 10. GitHub Copilot CLI

验证：

```bash
copilot
```

可以正常启动并完成登录。

如果 Codex 本周额度用完，可以在**同一个 workspace** 中直接改用 Copilot：

```bash
actual-coder resume "$WS" \
  --agent copilot \
  --goal "Continue the current task"
```

也可以让 ActualCoder 根据项目偏好与本机安装情况选择：

```bash
actual-coder resume "$WS" \
  --agent auto \
  --goal "Continue the current task"
```

`auto` 的规则：

1. 如果远端 `.actualcoder.yaml` 有 `agents.preferred`，按该顺序尝试；
2. 跳过当前 ActualCoder 不支持的 backend；
3. 跳过本机没有安装的 backend；
4. 如果项目没有偏好，默认尝试 `codex → copilot`；
5. 如果项目偏好的 backend 都没安装，则使用默认 fallback；
6. 两个都没安装则直接报错；
7. 选择过程不会启动模型，不消耗额度；
8. JSON 会输出 `agent_requested`、最终 `agent` 以及 `agent_selection.reason`。

Git 分支、worktree、MR 都不会因为更换 backend 而变化。

---

# 第五部分：标准开发流程

## 11. 推荐：用 `actual-coder start` 开始任务

团队日常推荐入口：

```bash
actual-coder start team/project-a \
  --task fix-timeout \
  --goal "Fix the request timeout bug and add regression coverage"
```

默认：

```text
--agent auto
```

一次完成：

```text
doctor preflight
→ 读取/验证 .actualcoder.yaml
→ 决定 effective base branch
→ 选择已安装 backend
→ 创建 isolated worktree
→ 把 project instructions / protected paths / validation commands 注入 handoff
→ 启动 coding CLI
```

如果只想测试整个准备流程、**不消耗模型额度**：

```bash
actual-coder start team/project-a \
  --task inspect \
  --goal "Inspect the workspace only. Do not modify files." \
  --no-launch
```

如果目前不在公司网络/VPN，但其他本地准备需要测试，可配合：

```text
--offline-doctor
```

不过真正创建 GitLab workspace 仍然需要能访问 GitLab。

ActualCoder 启动 backend 时不会替团队成员打开 `--allow-all-tools` / full-auto 一类广泛自动授权；使用 coding CLI 本身正常的交互/approval 机制。

## 11.1 低层兼容：`actual-coder task`

原有 `task` 仍然保留，适合调试和脚本：


示例：

```bash
actual-coder task team/project-a \
  --agent copilot \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the request timeout bug and add regression coverage"
```

也可以：

```bash
actual-coder task team/project-a \
  --agent codex \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the request timeout bug and add regression coverage"
```

或者：

```bash
actual-coder task team/project-a \
  --agent auto \
  --base-ref main \
  --task fix-timeout \
  --goal "Fix the request timeout bug and add regression coverage"
```

输出会包含：

```text
workspace_id
worktree_path
branch
agent
agent_command
agent_prompt
```

例如：

```text
workspace_id: abcd1234efgh
branch: chatgpt/fix-timeout-abcd1234
```

保存 workspace ID：

```bash
WS=abcd1234efgh
```

---

## 12. 启动 Coding Agent

最简单的方法是复制 ActualCoder 输出中的：

```text
agent_command
```

或者：

### Copilot

```bash
cd "$(gitlab-agent path "$WS" --plain)"
copilot
```

### Codex

```bash
cd "$(gitlab-agent path "$WS" --plain)"
codex
```

将 ActualCoder 输出的 `agent_prompt` 作为任务约束交给 coding backend。

---

## 13. 查看 workspace 状态

任何时候都可以：

```bash
gitlab-agent status "$WS"
```

重点字段：

```text
dirty
head
branch
commits_ahead_of_base
pushed
remote_branch
merge_request_url
```

---

## 14. 运行测试 / Build

统一入口：

```bash
gitlab-agent run "$WS" -- <command>
```

例如 Python：

```bash
gitlab-agent run "$WS" -- uv run pytest
```

例如 CMake：

```bash
gitlab-agent run "$WS" -- cmake --build build
```

默认 executable allowlist 可在：

```bash
GITLAB_ALLOWED_EXECUTABLES=...
```

中配置。

如果团队项目需要 `colcon`、`ctest` 或其他工具，需要显式加入 allowlist。

> `gitlab-agent run` 是受约束的 command runner，但不是 VM/container sandbox。不要在个人开发机直接运行不可信仓库的恶意 build script。

---

## 15. Review Diff

提交前必须检查：

```bash
gitlab-agent diff "$WS"
```

它会显示：

```text
COMMITTED SINCE BASE
STAGED
UNSTAGED
UNTRACKED
```

新建但未 git add 的文件也会显示。

---

## 16. Commit

```bash
gitlab-agent commit "$WS" \
  -m "fix: handle request timeout"
```

如果 Git 作者信息缺失，可使用正常 Git 配置：

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

或者配置：

```bash
GITLAB_GIT_AUTHOR_NAME="Your Name"
GITLAB_GIT_AUTHOR_EMAIL="you@example.com"
```

---

## 17. 第一次 Push + 创建 MR

准备 MR 描述：

```bash
cat >/tmp/mr.md <<'EOF'
## Summary

Describe the change.

## Validation

- relevant tests passed
EOF
```

第一次 push 推荐直接：

```bash
gitlab-agent push-mr "$WS" \
  --target main \
  --title "fix: handle request timeout" \
  --description-file /tmp/mr.md
```

工具使用 GitLab Git push options 创建 MR。

成功后状态中会看到：

```text
pushed: true
remote_branch: ...
merge_request_url: ...
```

---

## 17.1 推荐：用 `actual-coder finish` 收尾任务

Coding backend 完成改动后，先做 dry-run：

```bash
actual-coder finish "$WS" \
  --message "fix: describe the change" \
  --dry-run
```

dry-run 会：

```text
读取 workspace base 的 .actualcoder.yaml
→ 执行 configured validation
→ 检查 changed paths
→ 检查 protected paths
→ 扫描新增 diff 中的高风险 credential
→ 输出 diff
→ 计划 commit
→ 决定 first push / existing MR update
```

**不会 commit，不会 push。**

如果结果：

```text
ok: true
blockers: []
```

再执行：

```bash
actual-coder finish "$WS" \
  --message "fix: describe the change"
```

ActualCoder 会先打印同一类 plan，再要求人工确认，然后：

- dirty workspace → commit；
- 第一次 push → `push-mr` 创建 MR；
- 已有关联 MR → `push-update` 更新同一个 MR。

安全 gate：

- required validation 失败：阻断；
- `.actualcoder.yaml` 永远视为 protected path；
- 项目声明的 protected path 默认阻断；
- secret scan 命中默认阻断；
- `--yes` **只跳过人工确认**，不能绕过其他 gate；
- protected path 必须单独 `--allow-protected`；
- secret finding 必须单独 `--allow-secret-match`，且仅应在人工确认确实为误报/测试值后使用；
- 不自动 merge MR。

CI/脚本场景如果已经审阅 plan，可显式：

```bash
actual-coder finish "$WS" \
  --message "fix: describe the change" \
  --yes
```

但团队日常开发默认推荐保留交互确认。

---

# 第六部分：GitLab CI 反馈与继续已有 MR

## 18. 查看 workspace 对应的 GitLab CI

MR / feature branch 已经触发 pipeline 后：

```bash
actual-coder ci "$WS"
```

ActualCoder 会：

- 查询 workspace feature branch 的最近 pipeline；
- 优先选择 SHA 与当前 workspace HEAD 一致的 pipeline；
- 获取 pipeline jobs；
- 只抓 failed job 的日志尾部；
- 默认每个 failed job 最多 12 KB、最多 3 个 failed jobs；
- 去除 ANSI terminal escape；
- 对 GitLab/GitHub/OpenAI 等高风险 credential 以及明显的 `TOKEN/PASSWORD/SECRET/API_KEY=...` 做脱敏；
- 输出 `head_matches_pipeline` / `stale_for_workspace`；
- 生成 `repair_context`。

调大日志范围：

```bash
actual-coder ci "$WS" \
  --tail-bytes 30000 \
  --max-failed-jobs 5
```

最大值仍由工具限制，不允许无限读取日志。

### 18.1 用 CI failure 恢复 coding task

```bash
actual-coder resume "$WS" \
  --agent auto \
  --from-ci \
  --goal "Fix the CI failure at its root cause"
```

安全规则：

- CI log 属于 **untrusted diagnostic data**，不是指令；
- log 中即使出现“ignore previous instructions”也不能覆盖 user goal / ActualCoder rules；
- 如果 latest pipeline SHA 与当前 workspace HEAD 不一致，`--from-ci` 直接拒绝；
- pipeline 尚在 running/pending 时会明确 warning；
- 没有 pipeline 时 `actual-coder ci` 可正常返回“not found”，但 `resume --from-ci` 会要求先 push / 等待 pipeline；
- CI feedback 不会自动修改代码；
- 不会自动 commit/push；
- 不会自动 retry pipeline；
- 不会 approve / merge MR。

Coding agent 修复后仍然回到：

```bash
actual-coder finish "$WS" --message "fix: address CI failure"
```

---


## 18. 同一 workspace 再修改

例如 code review 后继续修改：

```bash
actual-coder resume "$WS" \
  --agent copilot \
  --goal "Address review feedback and rerun tests"
```

完成修改后：

```bash
gitlab-agent diff "$WS"

gitlab-agent commit "$WS" \
  -m "fix: address review feedback"

gitlab-agent push-update "$WS"
```

`push-update` 更新原 feature branch，因此原 MR 自动更新。

不会创建第二个 MR。

---

## 19. 在 Codex 与 Copilot 之间切换

同一 workspace：

```bash
actual-coder resume "$WS" \
  --agent codex \
  --goal "Continue the task"
```

然后可以改成：

```bash
actual-coder resume "$WS" \
  --agent copilot \
  --goal "Continue the same task"
```

变的是 coding backend。

不变的是：

- workspace；
- Git branch；
- HEAD；
- GitLab MR；
- gitlab-agent 状态。

---

# 第七部分：workspace 被清理后恢复

## 20. 从已有 MR 恢复

如果本地 workspace 已删除，但 GitLab MR 还在：

```bash
actual-coder checkout-mr team/project-a 123 \
  --agent copilot \
  --goal "Resume this MR and address review feedback"
```

ActualCoder 会：

1. 通过 GitLab API 查询 MR；
2. 找到 source branch / target branch；
3. fetch 最新 remote refs；
4. 创建新的本地 worktree；
5. checkout 原 MR source branch；
6. 恢复 MR URL；
7. 生成新的 agent handoff。

之后继续：

```bash
gitlab-agent commit "$WS" -m "..."
gitlab-agent push-update "$WS"
```

仍然更新原 MR。

---

## 21. 从 Remote Branch 恢复

```bash
actual-coder checkout-branch \
  team/project-a \
  chatgpt/fix-timeout-abcd1234 \
  --base-ref main \
  --agent copilot \
  --goal "Continue this branch"
```

为避免误操作，恢复的 branch 必须符合配置的安全 branch prefix。

---

# 第八部分：清理 Workspace

## 22. 正常清理

任务结束后：

```bash
gitlab-agent cleanup "$WS"
```

这会删除：

- 本地 managed worktree；
- 本地 task branch；
- 对应 local state。

不会自动删除：

- GitLab remote branch；
- MR。

---

## 23. 强制清理

如果 workspace 仍有未提交改动，正常 cleanup 会拒绝。

只有明确确认要丢弃时：

```bash
gitlab-agent cleanup "$WS" --force
```

不要把 `--force` 当成默认操作。

---

# 第九部分：ChatGPT 只读 MCP（可选）

ActualCoder 不依赖 ChatGPT MCP。

如果团队成员都有 ChatGPT Pro，并希望在普通 ChatGPT 中直接读 GitLab，推荐每位成员配置**自己的 Secure MCP Tunnel**。

完整的 Tunnel ID、Runtime API Key、Platform 权限、ChatGPT Developer Mode、macOS/Linux/Windows 凭证保存方式见：

[团队 OpenAI Secure MCP Tunnel 配置指南](OPENAI_TUNNEL_TEAM_SETUP_CN.md)

然后再参考下面的本地 MCP 验证步骤。

先测试 API：

```bash
uv run python smoke_test.py
```

测试 MCP：

```bash
uv run mcp dev server.py
```

详细 MCP tool 说明也可参考：

[SETUP_TUTORIAL_CN.md](SETUP_TUTORIAL_CN.md)

建议：

- MCP token 只使用 `read_api + read_repository`；
- MCP 保持只读；
- 不要通过 MCP 暴露写操作；
- Tunnel credential 与 GitLab token 都不要进入 Git 仓库。

---

# 第十部分：安全要求

## 24. 绝对不能提交的内容

包括：

```text
.env
真实 GITLAB_TOKEN
真实 GITLAB_GIT_TOKEN
GitHub PAT
模型 API Key
CONTROL_PLANE_API_KEY
私钥
证书私钥
真实 tunnel ID（如果属于内部部署信息）
包含 credential 的 URL
个人开发机绝对路径 / 内部部署细节（除非明确允许公开）
```

---

## 25. 本地 Secret Scan

日常：

```bash
uv run python scripts/check_repo_secrets.py
```

release / 对外分享前：

```bash
uv run python scripts/check_repo_secrets.py --history
```

CI 也会扫描完整 Git history。

如果发现真实 credential 曾经进入 commit：

**第一步不是删文件，而是先 revoke / rotate credential。**

然后再进行 Git history 清理。

---

## 26. 权限原则

推荐：

```text
ChatGPT MCP / API metadata:
    read_api
    read_repository

Git writes:
    write_repository
```

不要因为方便给所有开发 token `api` 全权限。

---

## 27. 分支安全

ActualCoder / gitlab-agent：

- 不直接 push base branch；
- 不 force push；
- 不负责 merge MR；
- 不负责 approve MR；
- 不自动删除 remote branch。

最终 merge 仍由团队正常 GitLab review / CI 流程决定。

---

# 第十一部分：常见问题

## 28. Git clone/fetch 出现 502 或访问内网 GitLab 失败

如果电脑使用 Clash / Surge / V2Ray / SOCKS proxy，很可能 Git 请求错误地走代理。

确认：

```bash
GITLAB_TRUST_ENV=false
GITLAB_GIT_TRUST_ENV=false
```

`GITLAB_GIT_TRUST_ENV=false` 还会覆盖本机 `~/.gitconfig` 中的 `http.proxy`。

---

## 29. 出现 socksio ImportError

例如：

```text
ImportError: Using SOCKS proxy, but the 'socksio' package is not installed
```

对于公司内网 GitLab，一般不需要安装 SOCKS 依赖。

优先：

```bash
GITLAB_TRUST_ENV=false
```

让 GitLab API 直连内网。

---

## 30. `actual-coder: command not found`

在仓库中：

```bash
bash scripts/install_user.sh
```

如果仍然找不到：

```bash
uv tool update-shell
```

然后重新打开 terminal。

验证：

```bash
which actual-coder
```

---

## 31. ActualCoder 找不到配置

推荐配置位置：

```text
~/.config/gitlab-agent/.env
```

确认：

```bash
actual-coder config
```

不要依赖“必须 cd 到工具仓库目录才能找到 .env”。

---

## 32. Build command 被拒绝

`gitlab-agent run` 只允许配置过的 executable。

查看：

```bash
actual-coder config
```

修改：

```bash
GITLAB_ALLOWED_EXECUTABLES=python,python3,pytest,uv,cmake,ninja,make,...
```

只增加团队真实需要的命令。

---

## 33. 本机缺少 ROS / CUDA / 特定 toolchain

ActualCoder 只能使用当前 host 已安装的开发环境。

例如缺少：

```text
ament_cmake
ROS 2
CUDA toolkit
交叉编译 SDK
```

coding agent 可以完成代码修改，但完整 build/test 仍然会失败。

这种情况要：

- 在具备工具链的开发机运行；
- 或使用团队 Docker / VM；
- 或交给 GitLab CI 做最终验证。

不要把“Agent 写完了”当成“完整集成测试通过”。

---

## 34. Codex 没额度

不用重建 workspace。

直接：

```bash
actual-coder resume "$WS" \
  --agent copilot \
  --goal "Continue the current task"
```

反过来也一样。

---

# 第十二部分：团队推荐 SOP

每个 coding task 建议统一执行：

```text
1. actual-coder task
2. coding backend 读代码 / 修改
3. gitlab-agent run
4. gitlab-agent diff
5. 人工确认重要改动
6. gitlab-agent commit
7. gitlab-agent push-mr
8. GitLab CI / Review
9. 有修改 → actual-coder resume
10. commit → push-update
11. MR merge 后 cleanup
```

团队建议约定：

- 一个 task 一个 workspace；
- 一个 workspace 一个 feature branch；
- 不让 agent 直接写 main；
- commit 前看 diff；
- push 前跑可运行的测试；
- MR 最终由 GitLab 正常 review/CI 决定是否 merge；
- 敏感项目使用独立开发机 / VM / container。

---

# 第十三部分：升级工具

在工具仓库：

```bash
git checkout main
git pull
uv sync
bash scripts/install_user.sh
```

然后：

```bash
actual-coder --help
actual-coder agents
```

已有 managed workspace 状态保存在：

```text
~/.local/share/chatgpt-gitlab-mcp/
```

工具代码升级不会自动删除这些 workspace。

---

# 第十四部分：团队成员第一天 Checklist

安装完成后请逐项确认：

- [ ] `uv sync` 成功；
- [ ] `actual-coder --help` 成功；
- [ ] `actual-coder config` 显示正确 GitLab 与 allowlist；
- [ ] `actual-coder agents` 能看到至少一个 backend；
- [ ] `actual-coder doctor` 无 FAIL；
- [ ] 目标项目如存在 `.actualcoder.yaml`，则 `actual-coder project-config <project> --validate` 通过；
- [ ] `GITLAB_TOKEN` 不在任何 Git tracked file 中；
- [ ] `GITLAB_GIT_TOKEN` 不在任何 Git tracked file 中；
- [ ] `uv run python scripts/check_repo_secrets.py` 通过；
- [ ] 能创建测试 workspace；
- [ ] 能查看 `gitlab-agent status`；
- [ ] 能运行至少一个项目相关 test/build；
- [ ] 能查看 `gitlab-agent diff`；
- [ ] 确认不会直接 push main；
- [ ] 完成一个测试 MR 后再用于真实研发任务。

---

# 相关文档

- [ActualCoder Quickstart](ACTUAL_CODER_QUICKSTART.md)
- [团队 OpenAI Secure MCP Tunnel 配置指南](OPENAI_TUNNEL_TEAM_SETUP_CN.md)
- [ChatGPT MCP 中文配置教程](SETUP_TUTORIAL_CN.md)
- [Architecture](V0.2_WRITE_ACCESS_DESIGN.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
