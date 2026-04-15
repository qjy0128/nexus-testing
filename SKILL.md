---
name: nexus-testing
description: Nexus AI 测试编排入口，面向 OpenClaw 优先运行时。根据用户目标分流到 Skill、网页+接口、安卓、MCP 四类流程，并支持评审已有测试报告/阶段交付物、按 report-dir 继续/批准/恢复多阶段测试会话，统一产出结构化测试文档。
---

# Nexus Testing Orchestrator

> 主要目标平台：**OpenClaw**。这套 Skill 默认按 OpenClaw 的调用与运行时约束设计；Claude CLI 等其他 runtime 适配只作为宿主桥接或调试备用，不改变主目标。

测试体系主入口。负责识别测试类型、选择工作模式、执行阶段门禁、处理评审模式与恢复/批准链路，并调度对应 Flow。

## Description

Nexus Testing 是一个多 Flow 测试编排入口。它根据用户输入识别测试对象类型，或进入已有报告/交付物的评审模式，并按统一阶段驱动需求解析、测试设计、执行、缺陷分析、恢复推进和最终报告。

## Usage

1. 提供待测对象，例如 Skill 路径、URL/API、APK 或 MCP Server 信息。
2. 从阶段零开始执行环境就绪检查。
3. 按阶段门禁推进；阶段二和阶段四必须等待批准。

## Examples

- `测试这个 Skill：D:/workspace/my-skill`
- `帮我测一下这个网页和接口`
- `Review 这个 FINAL-TEST-REPORT.md 有没有问题`
- `继续这个 report-dir 的测试会话`
- `批准 stage-2 并继续执行`

## 一、路由规则

| 关键词 | 测试类型 | Flow | 流程文件 |
|--------|----------|------|----------|
| `Skill` / `skill` | Skill 测试 | Flow A | `flows/skill-testing.md` |
| `网页` / `页面` / `web` / `接口` / `API` | 网页+接口测试 | Flow B | `flows/web-api-testing.md` |
| `APK` / `安卓` / `android` | 安卓测试 | Flow C | `flows/android-testing.md` |
| `MCP` / `mcp` | MCP 测试 | Flow D | `flows/mcp-testing.md` |

检测到多个类型时，不自行猜测执行方式，必须让用户选择：

- 串行执行
- 并行执行
- 只测其中一种

## 二、工作模式

### 生成模式

默认模式。执行阶段零到阶段七，产出完整测试文档与最终结论。

**轻量模式**：当被测对象规模较小时，自动合并部分阶段。具体触发条件和变更规则见 `DEFINITIONS.md` 第六节-C。轻量模式必须在环境就绪报告中显式声明。

**极简模式**：用户传入 `minimal` / `lite` / `quick` 参数，或被测对象满足"单文件 Skill、无外部依赖、无安全敏感操作、CAP ≤ 3"的全部条件时，启用 3 阶段极简流水线（快速扫描 → 核心测试 → 报告整合）。**纯指令型 Skill**（运行时为 `instruction` 且无代码文件）自动触发极简模式，不受 CAP 数量限制。详见 `DEFINITIONS.md` 第六节-D。极简模式须在报告中注明覆盖维度受限。若运行中发现安全敏感操作或超过 3 个 CAP，立即升级为标准模式。

### 评审模式

当用户给出已有测试报告、阶段交付物或评审请求时，只做静态审查，不触发标准流程。

评审模式至少检查：

- 必填章节是否齐全
- 命名和文件路径是否符合约定
- 缺陷、追溯、准入准出是否完整
- 占位符或未完成项是否残留

报告格式统一参考 `docs/references/reference-report-format.md`。

## 三、单一事实源

> 共享阶段、角色、目录、超时、并行角色、门禁和执行率阈值基线以 `DEFINITIONS.md` 为准；Flow/Reference 文件可按已声明的文档优先级补充场景化细化规则。

**文档冲突优先级**：Flow 文件 > Reference 文件 > DEFINITIONS.md > Role 文件 > SKILL.md。详见 `DEFINITIONS.md` 第六节-B。

主入口只保留调度逻辑：

- 主 agent 负责用户沟通、阶段推进、批准请求、打回决策和最终结论
- 阶段零到阶段七的阶段角色默认都由对应 subagent 执行；主 agent 不直接代跑阶段角色工作
- **Subagent 不可用降级**：当 subagent 因平台限制、runtime 不可用或超时重试仍失败时，主 agent 可按角色输出规范直接生成交付物，在交付物开头标记 `[subagent-unavailable: main-agent-executed]`，后续阶段正常推进。此降级路径不得用于规避质量门禁或批准流程。
- subagent 只负责执行本角色任务并写入结果
- 阶段间上下文通过报告目录里的文件传递，不依赖聊天上下文转述
- Flow B 的 A/B 双模式定义以 `DEFINITIONS.md` 和 `flows/web-api-testing.md` 为准
- `tool-evaluator`、`workflow-optimizer` 属于按需触发的辅助角色，不属于标准 8 阶段链路

## 四、标准阶段合同

```text
阶段零：环境就绪检查 -> 等待用户确认
阶段一：需求解析 + 事实校验 -> PRODUCT-FINGERPRINT.json / SPEC.md / SPEC-CONSISTENCY-REVIEW.md
阶段二：质量评估 -> PRODUCT-QUALITY-REVIEW.md -> 等待批准
阶段三：测试设计 -> TEST-DESIGN.md / SURFACE-EXECUTION-PLAN.json
阶段四：用例评估 -> TEST-CASE-REVIEW.md -> 等待批准
阶段五：并行测试执行 -> TEST-EXECUTION/*.md / SKILL-SURFACE-WORKLIST.md / SURFACE-COVERAGE.json
阶段五完成后（后置角色）：证据收集 -> DEFECTS/evidence-collection.md
阶段六：缺陷分析 -> DEFECTS/DEFECT-REPORT.md
阶段七：报告整合 -> FINAL-TEST-REPORT.md
```

输出目录统一为 `memory/nexus-reports/{date}-{test-type}-{flow}/`。

阶段执行模型统一要求：

- 阶段零先生成 `STAGE-SUBAGENT-PLAN.json`，作为后续阶段调度计划
- 阶段零由 `environment-checker` subagent 执行环境检查，主 agent 负责请求用户确认
- 阶段一到阶段七由对应阶段角色 subagent 执行
- 阶段五或 B 模式体验阶段按 Flow 模板并行启动多个 subagent
- 主 agent 负责发送交付物、请求批准、处理打回，不直接替代阶段角色写交付物

推荐调度顺序：

```text
主 agent
  -> generate_stage_subagent_plan.py
  -> environment-checker
  -> requirement-analyst
  -> spec-consistency-validator
  -> quality-assessor
  -> test-designer
  -> test-case-evaluator
  -> [阶段五并行角色]
  -> evidence-collector
  -> defect-analyst
  -> report-integrator
```

## 五、阶段零要求

阶段零必须先做，再进入阶段一。报告发出后，必须等待用户明确回复 `确认` 或 `通过`。

| Flow | 必检项 |
|------|--------|
| Flow A | Skill 路径、`SKILL.md` frontmatter、引用文件存在性、运行时依赖、系统命令、沙箱能力 |
| Flow B | URL 可访问、关键接口可达、输出目录可写 |
| Flow C | APK 路径可读、设备/工具链可用、输出目录可写 |
| Flow D | MCP Server 可连接、JSON-RPC 通道可用、输出目录可写 |

Flow A 额外要求：

- **产物生成**：用 `generate_flow_a_stage1.py` 生成阶段一三件套；用 `generate_stage_subagent_plan.py` 生成 `STAGE-SUBAGENT-PLAN.json`；用 `generate_flow_a_test_design.py` 生成测试设计；用 `generate_flow_a_skill_execution.py` 生成阶段五 worklist
- **执行编排**：`nexus_stage_executor.py init/next/dispatch/bundle-dispatch` → `nexus_dispatch_runner.py prepare/start-role/complete-role/fail-role/advance` → `nexus_runtime_bridge.py run-once/run-until-gate`（runtime-config 文件由 `generate_runtime_bridge_config.py --preset openclaw|claude|mock` 生成）
- **宿主运行时**：OpenClaw preset 用 `nexus_openclaw_role_runtime.py`；Claude preset 用 `nexus_claude_role_runtime.py`；演练入口用 `run_openclaw_stage_demo.py start/approve`
- **统一校验层**：dispatch payload 修改先扩展 `dispatch_payload_schema.py`；runtime config 修改先扩展 `runtime_config_schema.py`；role metadata 修改先扩展 `role_metadata.py`
- **接管路径**：`skill-tester` 进入 `takeover-required` 时用 `run_flow_a_takeover_execution.py`；用 `run_flow_a_skill_execution.py` 执行阶段五；完成后用 `validate_flow_a_skill_results.py` 校验覆盖完整性；`openclaw-extension` 优先通过 `testing.json` 的 `openclawExtensionRuntimeHarness` 验证真实 OpenClaw runtime 行为，有 live runtime 时先做 live probe
- **详细脚本参数与运行示例**见 `docs/references/reference-operational-procedures.md`

## 六、阶段五执行模型

阶段五必须并行，不得串行等待。并行角色集合由 `DEFINITIONS.md` 第四节决定。

执行要求：

- 同一 Flow 的所有并行角色同时启动
- 每个角色独立写入 `TEST-EXECUTION/*.md`
- 每个角色完成时写入进度文件，主 agent 汇总对外展示
- `evidence-collector` 只在所有并行角色结束后启动
- 任一角色失败、超时或降级执行时，必须保留部分结果，并在阶段六、阶段七显式标注未覆盖范围

## 七、批准与门禁

批准机制只收敛为以下硬规则：

- 阶段零完成后，等待用户确认
- 阶段二和阶段四结束后，必须等待用户批准
- 每个阶段交付物必须单独发送，禁止合并两个阶段的输出
- 在收到批准前，禁止提前执行下一阶段

批准实现细节、拒绝计数、阶段回退入口、无响应处理统一引用 `docs/references/reference-approval-mechanism.md`。

## 八、沟通约束（摘要）

- 交付物生成后立即主动发送，不等待用户追问
- 所有交付物的描述性内容必须使用用户**发起测试请求的语言**；代码、命令、路径保持原样
- 需要批准时明确要求"批准 / 拒绝"

Telegram / OpenClaw 文件发送示例：

```text
message(action: "send", filePath: "files/nexus-reports/{date}-{test-type}-{flow}/SPEC.md", caption: "阶段一需求规格已生成，已整理核心需求与验收点。下一步：进入阶段二质量评估。", buttons: [])
```

> 执行约束（核心）：见 `DEFINITIONS.md` 第十节「执行验证标准」。静态分析只能作为补充审查，只能标注 `blocked`/`incomplete`/`待真实执行复核`，不得输出 `PASS`/`PARTIAL PASS`/覆盖率。

> 完整沟通约束、执行原则、快速开始指引及参考文档索引见 `docs/references/reference-operational-procedures.md`。
