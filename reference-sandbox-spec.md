# 沙箱执行环境规格

> **定位**：本文件是 `nexus-testing` 框架沙箱执行能力的单一规格源。Skill 的真实调用、shim 适配器调用、trace 追踪、多轮对话与执行证明都以此为准。

---

## 一、能力边界

沙箱的价值不是“看起来像执行过”，而是把 Flow A 的执行证据拆成三个明确级别：

| 级别 | 模式 | 是否真实执行 | 适用场景 |
|------|------|-------------|---------|
| Level 1 | `live` | 是 | OpenClaw CLI 可用，直接调用 Skill |
| Level 2 | `shim-live` | 是 | 无 OpenClaw CLI，但 Skill 提供本地测试入口 |
| Level 3 | `trace` | 否 | 只能做静态路径追踪和补充分析 |

补充模式：

- `auto`：默认优先 `live`；但在 `--strict-real` 且存在独立 verifier 时优先 `shim-live`，最后才是 `trace`
- `dry-run`：只验证安装和入口，不执行调用

**强制规则**：

- `live` / `shim-live` 才能支撑“功能通过”“渠道通过”“多轮对话通过”。
- `trace` 只能写“已完成静态追踪，未完成真实执行”。
- `--strict-real` 开启后，脚本不得自动降级到 `trace`；若无真实执行入口，必须返回 blocker。

---

## 二、目录结构

沙箱根目录：`.nexus-sandbox/`（相对仓库根目录）

```text
.nexus-sandbox/
└── {session-id}/
    ├── workspace/
    │   ├── fixtures/
    │   ├── outputs/
    │   ├── temp/
    │   ├── state/
    │   ├── artifacts/
    │   └── skills/
    ├── runtime/
    ├── logs/
    │   ├── {timestamp}-*.stdout.log
    │   ├── {timestamp}-*.stderr.log
    │   ├── exit-codes.json
    │   └── file-ops.json
    └── META.json
```

关键目录说明：

- `workspace/skills/`：每个 session 内已安装的 Skill 副本
- `workspace/state/`：多轮历史、结果 JSON、状态文件
- `workspace/artifacts/`：适配器执行过程中产生的文件证据
- `workspace/outputs/`：最终响应、渠道渲染、汇总文件

---

## 三、生命周期

### 1. Create

```bash
bash scripts/sandbox-create.sh [--runtime node|python|both|none] [--session-id ID]
```

职责：

- 创建隔离目录结构
- 探测 Node / Python 运行时
- 写入 `META.json`

### 2. Execute

普通命令：

```bash
bash scripts/sandbox-exec.sh \
  --session-id ID \
  --command "..." \
  --backend host-logged \
  --ack-unsafe-exec \
  [--timeout 30]
```

> `sandbox-exec --backend host-logged` 只是带日志和基础黑名单的命令执行器，不提供容器/VM 级安全隔离；不得把它当成不可信代码沙箱。

容器命令：

```bash
bash scripts/sandbox-exec.sh \
  --session-id ID \
  --command "pytest -q" \
  --backend container \
  --container-image ubuntu:24.04 \
  [--allow-network] \
  [--timeout 30]
```

- `container` 后端会把当前 session 的 `workspace/` 挂载到容器内，默认工作目录为 `/workspace`
- 默认关闭容器网络；只有显式传 `--allow-network` 才开启
- 镜像必须自行提供 `bash` 与所需运行时（如 Node / Python / npm）
- 容器后端的隔离级别是“容器级”，不是 VM 级；但已明显强于 `host-logged`

Skill 调用：

```bash
bash scripts/sandbox-skill-invoke.sh --session-id ID --skill-path PATH --message "..."
```

多轮对话：

```bash
bash scripts/sandbox-multi-turn.sh --session-id ID --skill-path PATH --conversation-file FILE
```

### 3. Cleanup

```bash
bash scripts/sandbox-cleanup.sh --session-id ID [--force]
```

---

## 四、`sandbox-skill-invoke` 规格

### 命令

```bash
bash scripts/sandbox-skill-invoke.sh \
  --session-id ID \
  --skill-path /path/to/skill \
  --message "用户消息" \
  --channel telegram|feishu|qq|wechat \
  --mode auto|live|shim-live|trace|dry-run \
  --timeout 60 \
  [--strict-real] \
  [--expect-trigger true|false] \
  [--require-tools tool1,tool2] \
  [--expect-context-ref 1] \
  [--require-delivery-status delivered] \
  [--require-delivery-evidence] \
  [--verification-manifest /path/to/shim-verifier.json] \
  [--history-file workspace/state/history.json]
```

### 输出字段

```text
REQUESTED_MODE=auto
SELECTED_MODE=shim-live
EXECUTION_LEVEL=shim-live
REAL_EXECUTED=true
TELEMETRY_TRUST=runtime|independent|self-reported
TELEMETRY_PROTOCOL_STATUS=passed|missing|invalid
TELEMETRY_PROTOCOL_VERSION=nexus-live-telemetry/v1|missing
TELEMETRY_SOURCE=openclaw-runtime|unknown
STRICT_REAL=true
INVOKE_STATUS=success|failure|timeout|trace-complete|dry-run-complete|assertion-failed|blocked-*
TRIGGER_MATCHED=true|false|unknown
TOOLS_CALLED=tool1,tool2|unknown
DELIVERY_STATUS=delivered|sent|unknown
DELIVERY_RECEIPTS=receipt-1,receipt-2|unknown
DELIVERY_EVIDENCE=receipt-1,proof-2|unknown
INVALID_DELIVERY_EVIDENCE=path-outside-session,missing-proof.txt
CONTEXT_REFERENCES=1,2|unknown
ASSERTIONS_PASSED=true|false
ASSERTION_FAILURES=...
VERIFICATION_STATUS=not-configured|passed
VERIFIER_SOURCE=/abs/path/to/shim-verifier.json|none
TOOL_TRACE_FILE=...
OUTPUT_FILE=...
CHANNEL_RENDER_FILE=...
SEQ=...
```

`shim-live` 额外输出：

```text
ADAPTER_SOURCE=testing.json|scripts/test-entry.py
ADAPTER_SUPPORTS_MULTI_TURN=true|false|unknown
RESULT_JSON_FILE=...
VERIFIER_RESULT_FILE=...
VERIFIER_STDOUT_FILE=...
VERIFIER_STDERR_FILE=...
INSTALL_STATUS=not-required|cached|success
INSTALL_STDOUT_FILE=...
INSTALL_STDERR_FILE=...
```

### 严格模式

`--strict-real` 的行为：

- 若 `auto` 最终只能选到 `trace`，直接返回 `blocked-no-real-exec`
- 若 `auto --strict-real` 同时存在独立 verifier 和本地适配器，应优先 `shim-live`，避免因旧版 OpenClaw CLI 缺少 telemetry 协议而误 blocker
- 若 `--mode live` 但缺少 OpenClaw CLI，直接返回 `blocked-no-live-runtime`
- 若 `--mode live` 且开启 `--strict-real`，必须拿到 OpenClaw CLI 原生回传的 `nexus-live-telemetry/v1`；缺失时返回 `blocked-live-telemetry-missing`，字段不完整或协议错误时返回 `blocked-live-telemetry-invalid`
- 若 `--mode shim-live` 但缺少适配器，直接返回 `blocked-no-shim-adapter`
- 若 `--mode shim-live` 且开启 `--strict-real`，必须提供独立的 `--verification-manifest`；manifest 必须位于 Skill 目录外，且在可识别仓库根时不能与 Skill 同仓库。没有 verifier 时不得返回成功
- Windows 上执行 `shim-live` 时必须优先选择可运行的 Git Bash；`C:\Windows\System32\bash.exe` 这类 WSL 包装器不算有效运行时
- 若断言参数要求显式触发结果、上下文引用或送达证据而实际结果缺失，返回 `assertion-failed`
- Skill 目录内的 `testing.json` / `scripts/test-entry.*` 只算自报遥测；没有独立 verifier 时，严格断言不能通过

**禁止静默自动降级。**

### 审计要求

每次 `sandbox-skill-invoke` 都必须：

- 写入独立的 trace / stdout / stderr / output / result-json 证据文件
- 在审计锁保护下追加一条到 `logs/exit-codes.json`
- 更新 `META.json` 的 `commandCount` 与 `totalDurationMs`
- 使用 Skill 源文件内容哈希生成安装目录，避免同一 session 内复用旧副本

---

## 五、`shim-live` 适配器规范

### 支持方式

二选一：

1. `testing.json`
2. `scripts/test-entry.py|js|ts|sh`

### `testing.json`

```json
{
  "version": 1,
  "install": {
    "command": "python -m pip install -r requirements.txt",
    "cwd": "."
  },
  "invoke": {
    "command": "python scripts/test-entry.py",
    "cwd": "."
  },
  "supportsMultiTurn": true
}
```

要求：

- `command` 是在 Skill 根目录内执行的 shell 命令
- `cwd` 必须位于 Skill 根目录内
- 未声明 `supportsMultiTurn` 时按 `unknown` 处理

### 约定入口

当没有 `testing.json` 时，框架自动识别以下入口：

- `scripts/test-entry.py`
- `scripts/test-entry.js`
- `scripts/test-entry.mjs`
- `scripts/test-entry.cjs`
- `scripts/test-entry.ts`
- `scripts/test-entry.sh`

若存在 `requirements.txt` / `package.json`，框架会先按常规方式安装依赖。

### 传入环境变量

- `NEXUS_SESSION_ID`
- `NEXUS_MESSAGE`
- `NEXUS_CHANNEL`
- `NEXUS_SKILL_PATH`
- `NEXUS_WORKSPACE_DIR`
- `NEXUS_OUTPUT_FILE`
- `NEXUS_RESULT_JSON_FILE`
- `NEXUS_HISTORY_FILE`
- `NEXUS_ARTIFACTS_DIR`
- `NEXUS_STRICT_REAL`
- `NEXUS_TELEMETRY_PROTOCOL_VERSION`
- `NEXUS_TELEMETRY_SOURCE`
- `NEXUS_TELEMETRY_REQUIRED_FIELDS`
- `NEXUS_ADAPTER_RESULT_JSON_FILE`
- `NEXUS_VERIFIER_RESULT_FILE`
- `NEXUS_EXPECT_TRIGGER`
- `NEXUS_REQUIRE_TOOLS`
- `NEXUS_EXPECT_CONTEXT_REFS`
- `NEXUS_REQUIRE_DELIVERY_STATUS`
- `NEXUS_REQUIRE_DELIVERY_EVIDENCE`

### 建议回传结果

适配器应写入 `NEXUS_RESULT_JSON_FILE`：

```json
{
  "triggerMatched": true,
  "toolsCalled": ["Read", "Write"],
  "contextReferences": [1],
  "assistantMessage": "最终回复内容",
  "delivery": {
    "status": "delivered",
    "receipt": "tg:msg:12345",
    "evidence": ["workspace/artifacts/delivery-receipt.json"]
  },
  "artifacts": ["workspace/artifacts/result.png"],
  "notes": ["可选诊断信息"]
}
```

未回传 `toolsCalled` 时，框架不会把“工具链已验证”写成通过。
- 未回传 `contextReferences` 时，框架不会把“上下文保持”写成通过。
- 未回传 `deliveryStatus` 和送达证据时，框架不会把“渠道通过”写成通过。

### OpenClaw runtime telemetry protocol

`live --strict-real` 下，OpenClaw CLI 必须原生回传 `nexus-live-telemetry/v1`。可写入 `NEXUS_RESULT_JSON_FILE`，或在 stdout/stderr 中输出 `NEXUS_RESULT_JSON=` / `NEXUS_RESULT_JSON_START ... NEXUS_RESULT_JSON_END` 包裹的 JSON。

最小合法载荷：

```json
{
  "telemetryProtocolVersion": "nexus-live-telemetry/v1",
  "telemetrySource": "openclaw-runtime",
  "triggerMatched": true,
  "toolsCalled": ["Read"],
  "contextReferences": [1],
  "assistantMessage": "最终回复内容",
  "deliveryStatus": "delivered",
  "deliveryReceipts": ["tg:msg:12345"],
  "deliveryEvidence": ["workspace/artifacts/delivery-receipt.json"]
}
```

约束：

- `telemetryProtocolVersion` 必须精确等于 `nexus-live-telemetry/v1`
- `telemetrySource` 必须精确等于 `openclaw-runtime`
- `triggerMatched` 必须是布尔值
- `toolsCalled` / `contextReferences` / `deliveryReceipts` / `deliveryEvidence` 必须是数组
- `deliveryStatus` 必须是非空字符串
- 缺少协议或字段不完整时，`live --strict-real` 不得返回成功

### 独立 verifier manifest

`shim-live --strict-real` 必须提供位于 Skill 目录外的 verifier manifest；在可识别仓库根时，该 manifest 也不能与 Skill 同仓库：

```json
{
  "verify": {
    "command": "python verify.py",
    "cwd": "."
  }
}
```

verifier 写入 `NEXUS_VERIFIER_RESULT_FILE` 的 `triggerMatched` / `toolsCalled` / `contextReferences` / `delivery*` 会覆盖 Skill 自报结果，作为严格断言依据。

---

## 六、`sandbox-multi-turn` 规格

### 命令

```bash
bash scripts/sandbox-multi-turn.sh \
  --session-id ID \
  --skill-path /path/to/skill \
  --conversation-file workspace/fixtures/conversation.json \
  --mode auto|live|shim-live|trace \
  --timeout-per-turn 60 \
  [--verification-manifest /path/to/shim-verifier.json] \
  [--strict-real]
```

### 对话脚本格式

```json
{
  "description": "测试上下文保持",
  "turns": [
    {
      "role": "user",
      "message": "帮我查北京天气",
      "expect_trigger": true,
      "expect_tools": ["web_fetch"]
    },
    {
      "role": "user",
      "message": "那明天呢？",
      "expect_trigger": true,
      "expect_context_from_turn": 1,
      "expect_delivery_status": "delivered",
      "require_delivery_evidence": true
    }
  ]
}
```

规则：

- 每轮都调用 `sandbox-skill-invoke`
- 历史上下文写入 `workspace/state/*-multi-turn-history.json`
- `--strict-real` 时，任意一轮未达到 `live` / `shim-live` 都算失败
- 有 `expect_context_from_turn` 的回合必须拿到显式 `contextReferences`
- 有 `expect_delivery_status` 的回合必须拿到显式 `deliveryStatus`；若 `require_delivery_evidence=true`，还必须有送达证据

---

## 七、执行证明

每个真实执行用例必须记录：

- 执行动作
- 执行级别：`live` / `shim-live` / `trace`
- 实际输入
- 实际输出
- 工具证据
- 判定
- 证据路径

推荐证据路径：

- `invoke-trace.json`
- `response.md`
- `channel-*.md`
- `*.stdout.log`
- `*.stderr.log`
- `invoke-result.json`

---

## 八、与降级阶梯的关系

| 阶梯级别 | 对应实现 | 说明 |
|---------|---------|------|
| 1 | `sandbox-skill-invoke --mode live` | 真实 OpenClaw 调用 |
| 2 | `sandbox-skill-invoke --mode shim-live` | 本地适配器真实执行 |
| 3 | `sandbox-skill-invoke --mode trace` | 静态路径追踪 |
| 4 | `sandbox-exec` / 手工构造输入输出 | 仅在前三级不可行时使用；可信命令优先 `host-logged --ack-unsafe-exec`，不可信或高风险命令优先 `container` |
| 5 | 部分执行 | 记录已执行与未执行范围 |
| 6 | 静态分析 | 最后手段，必须明确标注未执行 |

---

## 九、诚实性要求

- 看到 `SKILL.md`、`package.json`、`requirements.txt` 不等于实际执行过。
- 只有脚本返回 `REAL_EXECUTED=true` 且 `EXECUTION_LEVEL` 为 `live` / `shim-live`，才能写“已实际使用 Skill”。
- 没有 OpenClaw CLI，也没有 shim 适配器时，结论必须是 blocker，而不是“trace 通过”。
