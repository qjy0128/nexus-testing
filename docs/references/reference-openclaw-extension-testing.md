# OpenClaw Extension 类型 Skill 测试规范

> 本文件集中定义 `openclaw-extension` 类型 Skill 的识别条件、Harness 选择链路、证据要求与降级规则。
> `roles/skill-tester.md` 和 `flows/skill-testing.md` 中涉及 openclaw-extension 的逻辑统一引用此文件。

---

## 一、识别条件

满足以下任一条件，即视为 `openclaw-extension` 类型 Skill：

| 识别依据 | 判定条件 |
|---------|---------|
| `SKILL.md` frontmatter | 包含 `type: openclaw-extension` 字段 |
| 插件清单文件 | 仓库根目录存在 `openclaw.plugin.json` |
| `PRODUCT-FINGERPRINT.json` | `productType` 中包含 `openclaw-extension` |

识别结论必须写入 `PRODUCT-FINGERPRINT.json` 的 `productType` 字段，并作为 `SURFACE-EXECUTION-PLAN.json` 的分类依据。

---

## 二、Harness 选择优先级链路

按以下优先级顺序选择执行方式，**不允许跳级**：

### 优先级 1：openclawExtensionRuntimeHarness（首选）

**触发条件**：`testing.json` 存在且包含 `openclawExtensionRuntimeHarness` 字段。

**期望产出**（必须全部出现，缺一则降级）：

| 字段 | 含义 |
|------|------|
| `behaviorVerified` | 行为层验证结果（boolean） |
| `runtimeVerified` | OpenClaw runtime 层验证结果（boolean） |
| `runtimeTransport` | runtime 通信协议（如 `nexus-live-telemetry/v1`） |
| `registeredHooks` | 已注册的 hooks 列表 |

若任一字段缺失，不得写为"验证通过"，必须降级至优先级 2。

### 优先级 2：openclawExtensionHarness（次选）

**触发条件**：`testing.json` 存在且包含 `openclawExtensionHarness` 字段，但无 `openclawExtensionRuntimeHarness`。

执行结果须包含 harness 实际输出的结构化 JSON；只有 stdout 文本输出时不得写为"验证通过"。

### 优先级 3：Live Probe（有 runtime 时兜底）

**触发条件**：`testing.json` 中两个 harness 字段均不存在，但当前环境可用 OpenClaw live runtime 或可启动 subagent。

执行要求：
- 必须实际触发 OpenClaw runtime，记录真实调用链
- 结果文件中写入 `"runtime-probed": true`
- 说明 probe 的具体行为（如：触发了哪个 subagent、收到何种响应）
- probe 结论只能写 `"runtime-reachable"` 或 `"runtime-unreachable"`，不能写"功能通过"

### 优先级 4：Blocker（无法验证 runtime 行为）

**触发条件**：以上三个选项均不可用。

必须输出：

```
状态：blocker
原因：openclaw-extension 无法验证 runtime 行为
详情：testing.json 缺少 openclawExtensionRuntimeHarness / openclawExtensionHarness；
      当前环境 OpenClaw live runtime 不可达。
未覆盖范围：[列出所有受影响的 surface-id]
建议动作：提供 testing.json.openclawExtensionRuntimeHarness 或确保 OpenClaw runtime 可达
```

---

## 三、降级判定表

| 环境条件 | 最高可达级别 | 结论限制 |
|---------|------------|---------|
| `openclawExtensionRuntimeHarness` 完整 | 优先级 1 | 可写"runtime 验证通过" |
| 仅 `openclawExtensionHarness` | 优先级 2 | 可写"harness 验证通过"，不能写"runtime 验证" |
| 仅 live runtime 可达 | 优先级 3（probe） | 只能写"runtime-reachable"，不能写"功能通过" |
| 三者均不可用 | blocker | 不得写任何通过结论 |

---

## 四、禁止行为

- 跳过 runtime probe 直接写"环境限制，无法验证"——有 live runtime 时必须先做 probe
- 把 `openclawExtensionHarness` 的结果冒充 `openclawExtensionRuntimeHarness` 的证据
- 缺少 `registeredHooks` 或 `runtimeTransport` 时仍写"优先级 1 通过"
- 仅有 probe 证据时写"功能验证通过"

---

## 五、结果写入格式（skill-results.md）

```markdown
### surface-id: openclaw-extension-runtime

**执行方式**：openclawExtensionRuntimeHarness / openclawExtensionHarness / live-probe / blocker

**证据**：
- behaviorVerified: true/false（优先级 1 时填写）
- runtimeVerified: true/false（优先级 1 时填写）
- runtimeTransport: nexus-live-telemetry/v1（优先级 1 时填写）
- registeredHooks: [hook-a, hook-b]（优先级 1 时填写）
- runtime-probed: true（优先级 3 时填写）

**判定**：✅ 通过 / ❌ 失败 / ⚠️ blocker

**未覆盖范围**：（blocker 时填写）
```
