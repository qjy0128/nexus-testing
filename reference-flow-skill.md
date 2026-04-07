# Flow A（Skill 测试）参考

> 本文件补充 `flows/skill-testing.md` 与 `roles/skill-tester.md` 的详细模板，重点说明 Flow A 的用例设计和执行证明格式。

---

## 一、关键用例模板

### 1.1 触发条件

| 用例 ID | 触发描述 | 最低执行级别 | 预期行为 | 优先级 |
|---------|---------|-------------|---------|--------|
| TC-SKILL-01 | 用户发送触发词 | `shim-live` | Skill 正确响应 | P0 |
| TC-SKILL-02 | 触发词带参数 | `shim-live` | 参数正确解析 | P0 |
| TC-SKILL-03 | 无效触发词 | `shim-live` | 明确返回 `triggerMatched=false` 或礼貌拒绝 | P1 |

### 1.2 工具调用验证

| 用例 ID | 工具 | 最低执行级别 | 预期结果 | 优先级 |
|---------|------|-------------|---------|--------|
| TC-TOOL-01 | `Read` | `shim-live` | 读取存在的文件并返回内容 | P0 |
| TC-TOOL-02 | `Read` | `shim-live` | 读取不存在的文件时明确报错 | P0 |
| TC-TOOL-03 | `exec` | `shim-live` | 执行无害命令并返回输出 | P1 |

### 1.3 多轮对话

| 用例 ID | 脚本描述 | 最低执行级别 | 验证目标 | 优先级 |
|---------|---------|-------------|---------|--------|
| TC-MULTI-01 | 短对话 | `shim-live` | 基础上下文保持 | P0 |
| TC-MULTI-02 | 标准对话 | `shim-live` | 话题延续 + 切换 | P0 |
| TC-MULTI-03 | 长对话 | `shim-live` | 上下文溢出 + 性能 | P1 |

### 1.4 渠道适配

| 用例 ID | 渠道 | 最低执行级别 | 验证点 | 优先级 |
|---------|------|-------------|--------|--------|
| TC-CHAN-01 | Telegram | `shim-live` | 有 `deliveryStatus` 与送达证据 | P0 |
| TC-CHAN-02 | 飞书 | `shim-live` | 格式兼容且有送达证据 | P1 |
| TC-CHAN-03 | QQ | `shim-live` | 纯文本降级且有送达证据 | P1 |
| TC-CHAN-04 | 微信 | `shim-live` | 先文字后文件且有送达证据 | P1 |

---

## 二、执行证明模板

每条 Flow A 的关键用例都必须包含以下字段：

```text
TC-XX：（用例名称）
  能力：CAP-XX
  执行动作：sandbox-skill-invoke --mode auto --strict-real --expect-trigger ... --require-tools ... [--verification-manifest ...]
  执行级别：live / shim-live / trace
  实际输入：{message/channel/history}
  实际输出：{response.md 或 result JSON 摘要}
  工具证据：{toolsCalled / trace file}
  触发/上下文/送达断言：{triggerMatched / contextReferences / deliveryStatus}
  判定：✅ 通过 / ❌ 失败
  证据路径：{trace/output/log/result-json}
```

规则：

- `trace` 不能支撑“功能通过”或“渠道通过”。
- 当用例标注最低执行级别为 `live` / `shim-live` 且只拿到 `trace` 时，结果必须记为 blocker。
- `live --strict-real` 必须拿到 OpenClaw CLI 原生回传的 `nexus-live-telemetry/v1`；没有协议或协议字段不完整时不得返回成功。
- `shim-live --strict-real` 必须提供独立的 `--verification-manifest`，不能只信 Skill 自带 adapter 的自报遥测；manifest 必须位于 Skill 目录外，且在可识别仓库根时不能与 Skill 同仓库。没有 verifier 时不得返回成功。
- 适配器没有回传 `toolsCalled` 时，不能对工具调用链写“已验证”。
- 负向触发用例没有显式 `triggerMatched=false` 时，不能写“已验证未触发”。
- 上下文用例没有显式 `contextReferences` 时，不能写“上下文保持通过”。
- 渠道用例没有显式 `deliveryStatus` 和送达证据时，不能写“渠道通过”。

---

## 三、Skill 适配器约定

Flow A 若要在没有 OpenClaw CLI 的情况下完成真实执行，Skill 必须提供以下二选一入口：

1. `testing.json`
2. `scripts/test-entry.py|js|ts|sh`

若使用 `shim-live --strict-real`，则必须额外提供位于 Skill 目录外的 `--verification-manifest`；在可识别仓库根时，该文件也不能与 Skill 同仓库。没有 verifier 时调用结果必须失败。

推荐的 `testing.json`：

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

适配器应尽量写出 `NEXUS_RESULT_JSON_FILE`：

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
  "artifacts": ["workspace/artifacts/output.png"],
  "notes": ["可选诊断信息"]
}
```

---

## 四、报告要求

- `TEST-DESIGN.md` 必须给每条关键用例标注最低执行级别。
- `skill-results.md` 必须单独列出执行级别矩阵。
- `FINAL-TEST-REPORT.md` 必须区分：
  - 真实执行通过
  - 仅 trace 覆盖
  - 因缺少真实入口而阻塞
