# 沙箱执行环境规格

> **定位**：本文档是 nexus-testing 框架沙箱执行能力的单一规格源。所有角色和流程文件引用本文件，不重复手写。

> **映射**：沙箱执行对应 `DEFINITIONS.md` 第十节降级阶梯第 2 级。当沙箱可用时，沙箱执行结果等同于真实执行，**不是降级**。

---

## 一、概览

### 解决什么问题

nexus-testing 框架的测试工程师（AI agent）在阶段五需要真实执行命令来验证被测产品。当前缺少隔离的执行环境，导致：
- 测试用例退化为静态分析（读文件→搜关键词→PASS）
- 执行率低于框架要求（≥ 90%）
- 降级阶梯第 2 级「沙箱执行」有名无实

沙箱提供：隔离的文件系统、受控的命令执行、完整的日志捕获、安全的资源限制。

### 设计原则

1. **轻量**：纯 bash 脚本，无外部依赖，POSIX 兼容 + Windows Git Bash 兼容
2. **安全**：路径隔离 + 命令黑名单 + 资源限制 + 完整审计
3. **可选**：沙箱不可用时框架降级到现有机制，不阻塞流程
4. **临时**：每个测试 session 创建独立沙箱，测试完成后清理

---

## 二、目录结构

沙箱根路径：`.nexus-sandbox/`（相对于测试报告目录）

```
.nexus-sandbox/
└── {session-id}/                         # 独立测试会话
    ├── workspace/                        # 工作目录（命令 CWD）
    │   ├── fixtures/                     # FX-NN 测试夹具
    │   ├── outputs/                      # 捕获的输出文件
    │   └── temp/                         # 临时文件
    ├── runtime/                          # 运行时环境
    │   └── (node_modules / venv 等)      # 按需安装的依赖
    ├── logs/                             # 执行日志
    │   ├── {timestamp}-{seq}.stdout.log  # 标准输出
    │   ├── {timestamp}-{seq}.stderr.log  # 标准错误
    │   ├── exit-codes.json               # 每条命令的退出码
    │   └── file-ops.json                 # 文件操作记录
    └── META.json                         # 会话元数据
```

**session-id 格式**：`{YYYYMMDD-HHmmss}-{random6hex}`（如 `20260403-143025-a1b2c3`）

**META.json 格式**：
```json
{
  "sessionId": "20260403-143025-a1b2c3",
  "createdAt": "2026-04-03T14:30:25",
  "status": "active",
  "platform": "win32",
  "runtime": {
    "node": "v20.11.0",
    "python": "3.12.1"
  },
  "capabilities": "full",
  "parentTestReport": "memory/nexus-reports/2026-04-03-skill-A",
  "commandCount": 0,
  "totalDurationMs": 0
}
```

---

## 三、沙箱生命周期

### Phase 1: Create（创建）

```
sandbox-create [--runtime node|python|both|none] [--session-id ID]
    ↓
生成 session-id（如未指定）
    ↓
创建目录结构
    ↓
探测运行时（node -v, python --version）
    ↓
写入 META.json
    ↓
输出 session-id 和能力级别
```

**能力级别**：

| 级别 | 条件 | 对应降级阶梯 |
|------|------|------------|
| Full | node + python 均可用 | 等同真实执行 |
| Partial | 仅 node 或仅 python | 等同真实执行（受限运行时） |
| Minimal | 无运行时，仅文件系统 | 等同降级阶梯第 3 级 |

### Phase 2: Provision（按需配置）

```
sandbox-provision --session-id ID [--npm package.json] [--pip requirements.txt]
    ↓
在 runtime/ 下安装依赖
    ↓
更新 META.json 状态
```

依赖安装仅在 TEST-DESIGN.md 中有用例明确需要时执行。

### Phase 3: Execute（执行）

```
sandbox-exec --session-id ID --command "..." [--timeout SECONDS] [--tag TC-XX]
    ↓
校验命令不在黑名单中
    ↓
设置 CWD 为 workspace/
    ↓
用 timeout 执行命令（默认 30s）
    ↓
捕获 stdout/stderr 到 logs/
    ↓
记录 exit code 到 exit-codes.json
    ↓
更新 META.json 计数
```

### Phase 4: Collect（收集）

```
sandbox-collect --session-id ID
    ↓
读取 logs/ 下所有日志
    ↓
读取 outputs/ 下所有文件
    ↓
汇总为执行证明格式
```

### Phase 5: Cleanup（清理）

```
sandbox-cleanup --session-id ID [--force]
    ↓
验证 session-id 存在于 .nexus-sandbox/ 下
    ↓
删除整个 session 目录
    ↓
验证删除完成（目录不存在）
    ↓
输出清理状态
```

---

## 四、安全边界

### 4.1 路径隔离

| 规则 | 说明 |
|------|------|
| 工作目录限制 | 所有命令的 CWD 为 `workspace/` |
| 禁止访问路径 | `/etc/`、`/usr/`、`~/.ssh/`、`~/.gnupg/`、`C:\Windows\`、`C:\Program Files\` |
| 路径遍历检测 | 拒绝解析到沙箱根目录之外的 `../` 路径 |
| 写入限制 | 命令只允许写入 `workspace/` 和 `runtime/` |

### 4.2 命令黑名单

以下命令/模式被禁止执行：

| 模式 | 风险 | 处理 |
|------|------|------|
| `rm -rf /` | 递归删除根目录 | 阻断 |
| `rm -rf ~` | 递归删除 home | 阻断 |
| `del /s /q C:\` | Windows 递归删除 | 阻断 |
| `format` | 格式化磁盘 | 阻断 |
| `mkfs` | 格式化文件系统 | 阻断 |
| `dd if=` | 原始磁盘写入 | 阻断 |
| `curl ... \| bash` / `wget ... \| sh` | 远程代码执行 | 阻断 |
| `eval` + 变量拼接 | 动态代码注入 | 警告（允许但记录） |
| `chmod 777` / `icacls grant Everyone` | 过度权限 | 警告 |

**校验方式**：字符串匹配命令前缀和管道模式，不做语法分析。误判可接受（宁可多拦）。

### 4.3 资源限制

| 资源 | 限制 | 超出行为 |
|------|------|---------|
| 单命令超时 | 30 秒（默认，可配置） | SIGTERM → 5s 后 SIGKILL |
| 沙箱总时长 | 10 分钟 | 后续命令返回超时错误 |
| 单文件大小 | 50MB | 拒绝写入 |
| 并发进程 | 不限制（沙箱内） | — |
| 网络访问 | 允许（沙箱内） | — |

### 4.4 审计日志

每条执行的命令都记录到 `exit-codes.json`：

```json
[
  {
    "seq": 1,
    "tag": "TC-47",
    "command": "node action-cli.ts decide --type exec_command --command \"rm -rf /\"",
    "exitCode": 0,
    "timestamp": "2026-04-03T14:31:05",
    "durationMs": 1250,
    "stdoutFile": "logs/20260403-143105-1.stdout.log",
    "stderrFile": "logs/20260403-143105-1.stderr.log"
  }
]
```

---

## 五、命令参考

### sandbox-create

```bash
bash scripts/sandbox-create.sh [--runtime node|python|both|none] [--session-id ID]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--runtime` | `both` | 指定要检测的运行时 |
| `--session-id` | 自动生成 | 指定 session ID |

**输出**：
```
SESSION_ID=20260403-143025-a1b2c3
CAPABILITIES=full
NODE=v20.11.0
PYTHON=3.12.1
SANDBOX_ROOT=.nexus-sandbox/20260403-143025-a1b2c3
```

### sandbox-exec

```bash
bash scripts/sandbox-exec.sh --session-id ID --command "..." [--timeout SECONDS] [--tag TC-XX]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--session-id` | 必填 | 目标 session |
| `--command` | 必填 | 要执行的命令 |
| `--timeout` | 30 | 超时秒数 |
| `--tag` | — | 关联的测试用例编号 |

**额外模式**：
- `--probe node|python`：仅探测运行时可用性，不执行命令

**输出**：
```
EXIT_CODE=0
STDOUT_FILE=logs/20260403-143105-1.stdout.log
STDERR_FILE=logs/20260403-143105-1.stderr.log
DURATION_MS=1250
```

### sandbox-cleanup

```bash
bash scripts/sandbox-cleanup.sh --session-id ID [--force]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--session-id` | 必填 | 要清理的 session |
| `--force` | false | 强制清理（跳过确认） |

**输出**：
```
CLEANUP_STATUS=success
DELETED_PATH=.nexus-sandbox/20260403-143025-a1b2c3
```

---

## 六、与测试框架的集成点

| 阶段 | 集成内容 |
|------|---------|
| 阶段零 | 检测 `scripts/sandbox-create.sh` 是否存在，探测运行时可用性 |
| 阶段三 | test-designer 标注哪些用例需要沙箱执行 |
| 阶段五 | tester 创建沙箱 → 配置 → 执行 → 收集 → 清理 |
| 阶段五后 | evidence-collector 审计沙箱日志是否完整 |
| 阶段六 | 缺陷分析师将沙箱日志作为执行证据 |

### FX 夹具规格中的沙箱字段

当测试用例需要沙箱执行时，FX 夹具规格增加以下字段：

```
#### FX-NN：（夹具名称）
• 类型：{测试数据/测试 Skill/...}
• 用途：{...}
• 内容规格：{...}
• 预期行为：{...}
• 执行环境：sandbox（标注需要沙箱）
• 运行时依赖：node / python / none
• 创建命令：sandbox-exec --session-id {ID} --command "..."
• 清理命令：sandbox-exec --session-id {ID} --command "rm -rf fixtures/FX-NN"
```

### 沙箱执行证明格式

沙箱执行的用例，执行证明使用标准 4 字段格式，外加沙箱标注：

```
TC-XX：（用例名称）
  执行动作：sandbox-exec --session-id {ID} --command "..." --tag TC-XX
  实际输入：{传入的命令和参数}
  实际输出：（粘贴 logs/{file}.stdout.log 的完整内容）
  判定：✅ 通过 / ❌ 失败
  沙箱证据：exit-codes.json seq={N}, exit_code={N}, duration={ms}ms
```

---

## 七、降级与容错

| 场景 | 处理 |
|------|------|
| sandbox-create.sh 不存在 | 跳过沙箱，直接进入降级阶梯第 3 级 |
| 运行时不可用 | 沙箱降级为 Minimal（仅文件系统），记录在 META.json |
| 命令被黑名单拦截 | 记录拦截原因，该用例标记为「执行环境限制」，降级 |
| 命令超时 | 记录超时，使用已捕获的部分输出作为执行证明 |
| 沙箱总时长超限 | 停止执行，已完成的用例正常记录，未执行的标注超时 |
| cleanup 失败 | 记录残留文件路径，不阻塞流程 |

---

## 八、OpenClaw 集成

- 沙箱目录 `.nexus-sandbox/` 建议加入 `.clawignore`
- 沙箱 workspace 是标准文件系统目录，OpenClaw 的 Read/Write/Glob/Grep 工具可直接操作
- 沙箱脚本通过 Bash 工具调用，无需额外权限
- 多次测试的沙箱 session 互相隔离，不会冲突

---

## 九、Skill 调用模拟（sandbox-skill-invoke）

> **定位**：降级阶梯第 1-2 级的核心实现。让测试工程师能像用户一样"调用" Skill，而非仅读文档。

### 解决什么问题

当前沙箱只能执行 shell 命令。但 Skill 测试需要：
- 将 Skill 安装到隔离环境
- 模拟用户发送触发消息
- 追踪 Skill 的决策树和工具调用链
- 捕获每个工具的参数和返回值
- 验证最终输出是否符合预期

### 三种模式

| 模式 | 说明 | 降级阶梯 | 需要 OpenClaw CLI |
|------|------|---------|------------------|
| `live` | 通过 OpenClaw CLI 真实调用 Skill | 第 1 级（真实调用） | ✅ 是 |
| `trace` | 解析 SKILL.md，追踪决策树，记录"会调用什么工具" | 第 2 级（追踪调用） | ❌ 否 |
| `dry-run` | 仅安装 Skill 并验证结构，不调用 | 安装验证 | ❌ 否 |

### 命令参考

```bash
bash scripts/sandbox-skill-invoke.sh \
  --session-id ID \
  --skill-path /path/to/skill \
  --message "用户消息" \
  --channel telegram|feishu|qq|wechat \
  --mode live|dry-run|trace \
  --timeout 60
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--session-id` | 必填 | 沙箱 session ID |
| `--skill-path` | 必填 | Skill 目录或 SKILL.md 路径 |
| `--message` | 必填（非 dry-run） | 模拟的用户消息 |
| `--channel` | `telegram` | 模拟的渠道 |
| `--mode` | `trace` | 执行模式 |
| `--timeout` | `60` | 超时秒数 |

### 输出

```
INVOKE_STATUS=success|failure|timeout|trace-complete|dry-run-complete
TRIGGER_MATCHED=true|false|unknown
TOOLS_CALLED=tool1,tool2,tool3
TOOL_TRACE_FILE=logs/{timestamp}-invoke-trace.json
OUTPUT_FILE=workspace/outputs/{timestamp}-response.md
CHANNEL_RENDER_FILE=workspace/outputs/{timestamp}-channel-{channel}.md
```

### 调用追踪日志格式（invoke-trace.json）

```json
{
  "mode": "trace",
  "timestamp": "2026-04-05T10:30:00",
  "skillName": "my-skill",
  "skillPath": ".nexus-sandbox/{session}/workspace/skills/my-skill",
  "message": "用户消息",
  "channel": "telegram",
  "triggerMatched": true,
  "triggerAnalysis": "Found 3 trigger conditions: [...]",
  "toolsCalled": ["Read", "web_fetch", "Write"],
  "traceSteps": [
    {"step": 1, "action": "trigger_match", "detail": "Message matched trigger: ...", "tools": []},
    {"step": 2, "action": "tool_call_trace", "detail": "Would call tool: Read", "tools": ["Read"]},
    {"step": 3, "action": "tool_call_trace", "detail": "Would call tool: web_fetch", "tools": ["web_fetch"]}
  ],
  "expectedOutput": "...",
  "channelAdaptation": "Markdown rendering supported, max 4096 chars",
  "status": "trace-complete"
}
```

### 执行证明格式（调用测试专用）

```
TC-XX：（用例名称）
  能力：CAP-XX
  调用：sandbox-skill-invoke --session-id {ID} --message "..." --channel telegram --mode trace
  触发匹配：true/false
  工具调用链：[tool1(param=val), tool2(param=val)]
  调用追踪：（粘贴 invoke-trace.json 关键内容）
  实际输出：（粘贴 response.md 内容）
  预期输出：（来自 TEST-DESIGN.md）
  Token 消耗：XXX（live 模式可测量，trace 模式标注"追踪模式不可测"）
  判定：✅ 通过 / ❌ 失败（原因：xxx）
```

### 降级行为

| 场景 | 处理 |
|------|------|
| live 模式但 OpenClaw CLI 不可用 | 自动降级为 trace 模式，记录降级原因 |
| trace 模式但 Python 不可用 | 降级为最小追踪（仅记录工具声明列表） |
| Skill 安装失败 | 记录失败原因，该用例标记为"安装失败" |
| 触发匹配无法判定 | 标记为 `unknown`，由测试工程师人工判断 |

---

## 十、多轮对话模拟（sandbox-multi-turn）

> **定位**：ST-4（交互对话型）Skill 的专用测试工具。验证多轮对话中的上下文保持、话题切换、上下文溢出。

### 命令参考

```bash
bash scripts/sandbox-multi-turn.sh \
  --session-id ID \
  --skill-path /path/to/skill \
  --conversation-file workspace/fixtures/conversation-script.json \
  --channel telegram \
  --timeout-per-turn 60
```

### 对话脚本格式（conversation-script.json）

```json
{
  "description": "测试上下文保持：5轮对话，第3轮引用第1轮内容",
  "turns": [
    {
      "role": "user",
      "message": "帮我查一下北京今天的天气",
      "expect_trigger": true,
      "expect_tools": ["web_fetch"]
    },
    {
      "role": "user",
      "message": "那明天呢？",
      "expect_trigger": true,
      "expect_context_from_turn": 1
    },
    {
      "role": "user",
      "message": "上海的呢？",
      "expect_trigger": true
    },
    {
      "role": "user",
      "message": "刚才北京今天几度来着？",
      "expect_trigger": true,
      "expect_context_from_turn": 1
    },
    {
      "role": "user",
      "message": "完全不相关的话题：推荐一首歌",
      "expect_trigger": false
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `role` | 固定为 `user` |
| `message` | 用户发送的消息 |
| `expect_trigger` | 是否期望 Skill 被触发 |
| `expect_tools` | 期望调用的工具列表（可选） |
| `expect_context_from_turn` | 期望响应引用第 N 轮的上下文（可选） |

### 输出

```
MULTI_TURN_STATUS=all-passed|partial-pass|all-failed
TOTAL_TURNS=5
PASSED_TURNS=4
FAILED_TURNS=1
CONTEXT_PRESERVATION=verified|partial|failed|not-tested
LOG_FILE=logs/{timestamp}-multi-turn.json
SUMMARY_FILE=workspace/outputs/{timestamp}-multi-turn-summary.md
```

### 与降级阶梯的关系

多轮对话模拟底层调用 `sandbox-skill-invoke.sh`（trace 模式），因此：
- 当 trace 模式可用时，多轮模拟等同于降级阶梯第 2 级
- 当 Python 不可用时，多轮模拟不可执行，降级为手动构造多轮输入/输出

---

## 十一、外部服务 Mock（sandbox-mock-service）

> **定位**：ST-2（数据获取型）Skill 依赖外部 API 时的测试支撑。创建可预期的 mock 响应文件，覆盖成功/超时/错误/空数据等场景。

### 设计说明

本脚本**不启动真实的 HTTP 服务器**（避免端口冲突和权限问题），而是：
1. 根据配置文件在沙箱中创建 mock 响应文件
2. 测试工程师在构造 Skill 调用参数时，引用这些 mock 文件作为模拟数据
3. 通过对比 Skill 对不同 mock 响应的处理行为，验证错误处理和降级能力

### 命令参考

```bash
# 启动 mock（创建响应文件）
bash scripts/sandbox-mock-service.sh \
  --session-id ID \
  --mock-config workspace/fixtures/mock-services.json \
  --action start

# 查看状态
bash scripts/sandbox-mock-service.sh --session-id ID --action status

# 停止（标记为停用）
bash scripts/sandbox-mock-service.sh --session-id ID --action stop
```

### Mock 配置格式（mock-services.json）

```json
{
  "services": [
    {
      "name": "weather-api",
      "scenarios": [
        {
          "name": "success",
          "status": 200,
          "headers": {"Content-Type": "application/json"},
          "body": {"city": "Beijing", "temp": 25, "condition": "sunny"}
        },
        {
          "name": "timeout",
          "status": 0,
          "error": "connection_timeout",
          "delay_ms": 30000
        },
        {
          "name": "server-error",
          "status": 500,
          "body": {"error": "internal server error"}
        },
        {
          "name": "empty-response",
          "status": 200,
          "body": {}
        },
        {
          "name": "rate-limited",
          "status": 429,
          "headers": {"Retry-After": "60"},
          "body": {"error": "rate limit exceeded"}
        },
        {
          "name": "malformed-json",
          "status": 200,
          "raw_body": "not valid json {{"
        }
      ]
    }
  ]
}
```

### 目录结构

```
workspace/mocks/
├── registry.json                    # Mock 服务注册表
├── weather-api/
│   ├── success.json                # 成功响应
│   ├── timeout.json                # 超时场景
│   ├── server-error.json           # 服务端错误
│   ├── empty-response.json         # 空数据
│   ├── rate-limited.json           # 限流
│   └── malformed-json.json         # 畸形响应
└── {other-service}/
    └── ...
```

### 测试工程师使用方式

在测试用例中：
1. 启动 mock（`--action start`）
2. 读取 mock 文件内容作为模拟的 API 响应
3. 将 mock 数据作为 Skill 的输入或环境变量
4. 观察 Skill 对不同场景的处理行为
5. 停止 mock（`--action stop`）

**执行证明格式**：
```
TC-XX：（外部服务降级测试）
  Mock 场景：weather-api/timeout
  Mock 数据：（粘贴 timeout.json 内容）
  Skill 输入：（传入的触发消息）
  Skill 实际行为：（Skill 如何处理超时——重试/降级/报错）
  预期行为：友好提示"数据源暂不可用"
  判定：✅ / ❌
```
