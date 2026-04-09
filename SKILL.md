---
name: nexus-testing
description: Nexus AI 测试体系入口。根据用户目标自动分流到 Skill、网页+接口、安卓、MCP 四类流程，并按统一阶段产出结构化测试文档。
---

# Nexus Testing Orchestrator

> 主要目标平台：**OpenClaw**。这套 Skill 默认按 OpenClaw 的调用与运行时约束设计；Claude CLI 等其他 runtime 适配只作为宿主桥接或调试备用，不改变主目标。

测试体系主入口。负责识别测试类型、选择工作模式、执行阶段门禁，并调度对应 Flow。

## Description

Nexus Testing 是一个多 Flow 测试编排入口。它根据用户输入识别测试对象类型，并按统一阶段驱动需求解析、测试设计、执行、缺陷分析和最终报告。

## Usage

1. 提供待测对象，例如 Skill 路径、URL/API、APK 或 MCP Server 信息。
2. 从阶段零开始执行环境就绪检查。
3. 按阶段门禁推进；阶段二和阶段四必须等待批准。

## Examples

- `测试这个 Skill：D:/workspace/my-skill`
- `帮我测一下这个网页和接口`
- `Review 这个 FINAL-TEST-REPORT.md 有没有问题`

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

**轻量模式**：当被测对象规模较小时（Skill 行数 < 100、能力 ≤ 3、必测维度 ≤ 5，或用户要求），自动合并部分阶段。触发条件和变更规则见 `DEFINITIONS.md` 第六节-C。轻量模式必须在环境就绪报告中显式声明。

### 评审模式

当用户给出已有测试报告、阶段交付物或评审请求时，只做静态审查，不触发标准流程。

评审模式至少检查：

- 必填章节是否齐全
- 命名和文件路径是否符合约定
- 缺陷、追溯、准入准出是否完整
- 占位符或未完成项是否残留

报告格式统一参考 `reference-report-format.md`。

## 三、单一事实源

> 共享阶段、角色、目录、超时、并行角色、门禁和执行率阈值基线以 `DEFINITIONS.md` 为准；Flow/Reference 文件可按已声明的文档优先级补充场景化细化规则。

**文档冲突优先级**：Flow 文件 > Reference 文件 > DEFINITIONS.md > Role 文件 > SKILL.md。详见 `DEFINITIONS.md` 第六节-B。

主入口只保留调度逻辑：

- 主 agent 负责用户沟通、阶段推进、批准请求、打回决策和最终结论
- 阶段零到阶段七的阶段角色默认都由对应 subagent 执行；主 agent 不直接代跑阶段角色工作
- subagent 只负责执行本角色任务并写入结果
- 阶段间上下文通过报告目录里的文件传递，不依赖聊天上下文转述
- Flow B 的 A/B 双模式定义以 `DEFINITIONS.md` 和 `flows/web-api-testing.md` 为准

## 四、标准阶段合同

```text
阶段零：环境就绪检查 -> 等待用户确认
阶段一：需求解析 + 事实校验 -> PRODUCT-FINGERPRINT.json / SPEC.md / SPEC-CONSISTENCY-REVIEW.md
阶段二：质量评估 -> PRODUCT-QUALITY-REVIEW.md -> 等待批准
阶段三：测试设计 -> TEST-DESIGN.md / SURFACE-EXECUTION-PLAN.json
阶段四：用例评估 -> TEST-CASE-REVIEW.md -> 等待批准
阶段五：并行测试执行 -> TEST-EXECUTION/*.md / SKILL-SURFACE-WORKLIST.md / SURFACE-COVERAGE.json
阶段五后：证据收集 -> DEFECTS/evidence-collection.md
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

- 识别 Node / npm、Python、外部插件、系统命令依赖
- 使用 `scripts/generate_flow_a_stage1.py --target <repo-or-skill> --output-dir <report-dir>` 优先生成阶段一三件套；其内部先调用 `scripts/extract_product_fingerprint.py` 抽取事实指纹，再写规格
- 使用 `scripts/generate_stage_subagent_plan.py --flow <skill|web-api|android|mcp> --mode <standard|b> --output-file <report-dir>/STAGE-SUBAGENT-PLAN.json` 在阶段零生成机器可读调度计划
- 使用 `scripts/nexus_stage_executor.py init --report-dir <report-dir> --flow <skill|web-api|android|mcp> --mode <standard|b>` 初始化阶段执行状态
- 使用 `scripts/nexus_stage_executor.py next --report-dir <report-dir>` 判断当前应启动哪个阶段角色、是否等待批准、或是否进入完成态
- 使用 `scripts/nexus_stage_executor.py dispatch --report-dir <report-dir>` 为当前阶段生成每个 subagent 的启动载荷
- 使用 `scripts/nexus_stage_executor.py bundle-dispatch --report-dir <report-dir>` 将当前阶段启动载荷写成可直接消费的 prompt bundle
- 使用 `scripts/nexus_dispatch_runner.py prepare --report-dir <report-dir>` 将当前 dispatch bundle 转成运行清单
- 使用 `scripts/nexus_dispatch_runner.py start-role|complete-role|fail-role|advance --report-dir <report-dir> ...` 跟踪角色运行状态；`advance` 在当前阶段角色全部完成后会自动补写 `stage-complete` 并推进阶段
- 使用 `scripts/generate_runtime_bridge_config.py --preset <mock|claude> --output-file <runtime.json> ...` 生成可直接给 runtime bridge 使用的宿主运行配置
- 使用 `scripts/generate_runtime_bridge_config.py --preset openclaw --output-file <runtime.json> --openclaw-command openclaw --channel telegram --skill-path <repo-root>` 生成更符合本 Skill 主目标的 OpenClaw runtime 配置
- 使用 `scripts/nexus_openclaw_role_runtime.py --payload-file <payload.json> --prompt-file <prompt.md> --openclaw-command openclaw` 将单个阶段角色交给 OpenClaw CLI 执行
- 使用 `scripts/run_openclaw_stage_demo.py start --report-dir <report-dir> --runtime-config runtime-config.openclaw.json` 从阶段零开始跑 OpenClaw 端到端调度演练，并在首个审批门停下
- 使用 `scripts/run_openclaw_stage_demo.py approve --report-dir <report-dir> --stage-id <stage-id> --runtime-config runtime-config.openclaw.json --continue-run` 记录批准后继续推进到下一个审批门
- 使用 `scripts/nexus_claude_role_runtime.py --payload-file <payload.json> --prompt-file <prompt.md> --claude-command claude` 将单个阶段角色交给 Claude CLI 非交互执行
- 使用 `scripts/nexus_runtime_bridge.py run-once --report-dir <report-dir> --runtime-config <runtime.json>` 将当前阶段 dispatch bundle 真正交给宿主 runtime 执行
- 使用 `scripts/nexus_runtime_bridge.py run-until-gate --report-dir <report-dir> --runtime-config <runtime.json>` 连续执行多个阶段，直到遇到审批门、No-Go、执行失败或完成
- `runtime-config` 至少提供 `default.command`，支持按角色覆盖；命令模板可使用 `{payload_file}`、`{prompt_file}`、`{report_dir}`、`{stage_id}`、`{role_id}` 等变量；外部 runtime 若 stdout 返回 `{"resultFile":"...", "note":"..."}`，bridge 会自动回写 `RUNS` 状态
- OpenClaw preset 通过 `nexus_openclaw_role_runtime.py` 调 `openclaw invoke`，更贴近这个 Skill 的原生使用方式；若 OpenClaw 结果 JSON 未直接给出主交付物，适配器会按当前阶段缺失交付物自动探测
- `run_openclaw_stage_demo.py` 是推荐的 OpenClaw 演练入口，会把初始化、运行到审批门、记录批准和继续推进串成一条可复用命令链
- Claude preset 默认通过 `nexus_claude_role_runtime.py` 调 `claude --print`，并用 JSON Schema 约束返回 `resultFile/note`；先用 `--dry-run` 检查 prompt 和命令，再接入真实执行
- 使用 `scripts/generate_flow_a_test_design.py --fingerprint <PRODUCT-FINGERPRINT.json> --spec <SPEC.md> --consistency-review <SPEC-CONSISTENCY-REVIEW.md> --output-dir <report-dir> --language <request-language>` 生成多表面 `TEST-DESIGN.md` 与 `SURFACE-EXECUTION-PLAN.json`
- 使用 `scripts/generate_flow_a_skill_execution.py --surface-plan <SURFACE-EXECUTION-PLAN.json> --output-dir <report-dir>` 生成阶段五 `SKILL-SURFACE-WORKLIST.md` 与 `SURFACE-COVERAGE.json`
- 使用 `scripts/run_flow_a_skill_execution.py --surface-plan <SURFACE-EXECUTION-PLAN.json> --skill-path <repo-or-skill> --session-id <id> --sandbox-root <sandbox-root> --output-dir <report-dir> --language <request-language>` 让 `skill-tester` 按 surface 顺序执行；当前 `skill/bin` 可给真实执行结论，`package/plugin-manifest` 为结构化校验，`openclaw-extension` 优先通过 `testing.json` 的 `openclawExtensionRuntimeHarness` 验证真实 OpenClaw runtime / subagent 行为，其次才是 `openclawExtensionHarness`；若无 harness 但 live runtime 可用，runner 也必须先做 live probe，并把 `runtime-probed=true` 记入结果；`mcp` 可通过 stdio JSON-RPC harness 验证协议交互，只有 probe 证据时才记为 `incomplete`
- 阶段五完成后，用 `scripts/validate_flow_a_skill_results.py --surface-plan <SURFACE-EXECUTION-PLAN.json> --skill-results <TEST-EXECUTION/skill-results.md>` 校验 surface 覆盖是否完整
- 判断是否需要 `sandbox-create.sh`、`sandbox-exec.sh` 等沙箱脚本
- 阶段一先生成 `PRODUCT-FINGERPRINT.json`，再生成 `SPEC.md`
- 阶段一必须完成 `SPEC-CONSISTENCY-REVIEW.md`；未通过不得进入阶段二
- OpenClaw 自身可用性默认由运行时保证，不作为本 Skill 的检测项

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

批准实现细节、拒绝计数、阶段回退入口、无响应处理统一引用 `reference-approval-mechanism.md`。

## 八、沟通约束

只保留必要规则：

- 每阶段独立发送交付物和简要摘要
- 交付物生成后立即主动发送，不等待用户追问
- 所有交付物的描述性内容必须使用用户**发起测试请求的语言**；代码、命令、路径、协议名保持原样
- 需要批准时明确要求“批准 / 拒绝”
- 缺输入或 blocker 时，用最短清单向用户提问
- 不用模糊措辞代替阶段状态

Telegram / OpenClaw 文件发送硬约束：

- 发送交付物时必须显式提供 `caption`
- 无交互按钮时也必须显式提供 `buttons: []`，不得省略
- `caption` 至少包含文件摘要和下一步
- 报告文件先写入 `memory/nexus-reports/...`，再通过 `python scripts/prepare_report_delivery.py --report-file <memory-report-file>` 镜像到工作区 `files/...`
- `message(action: "send", ...)` 的 `filePath` 必须使用相对工作区的 `files/...` 路径；`memory/...` 只用于归档，不直接用于发送
- 首次发送失败时，必须重试 `files/...` 中转路径；若平台仍拒绝，需在同轮消息里明确告知报告所在的工作区路径

文件发送示例（Telegram / OpenClaw）：

```text
message(action: "send", filePath: "files/nexus-reports/{date}-{test-type}-{flow}/SPEC.md", caption: "阶段一需求规格已生成，已整理核心需求与验收点。下一步：进入阶段二质量评估。", buttons: [])
```

推荐输出骨架：

```text
第 X 阶段完成
参与角色：...
交付物：...
关键结论：...
下一步：...
```

## 九、执行原则

> 读文档不等于测试，静态分析不等于验证。

阶段五每条关键用例都必须记录：

- 执行动作
- 实际输入
- 实际输出
- 判定

静态分析只能作为补充审查：

- 不得输出 `PASS` / `PARTIAL PASS`
- 不得输出功能覆盖率、API 覆盖率、规则覆盖率
- 只能输出 `blocked` / `incomplete` / `待真实执行复核`

环境不足时使用降级阶梯：

```text
真实执行
  ↓
沙箱执行
  ↓
构造模拟
  ↓
部分执行
  ↓
静态分析（最后手段，必须显式标注）
```

执行率阈值、Go/No-Go 规则、残余风险表达统一以 `DEFINITIONS.md` 为准。

## 十、快速开始

1. 将仓库作为 OpenClaw Skill 项目打开，入口使用本文件。
2. 提供待测对象：Skill 路径、URL/API、APK 或 MCP Server 信息。
3. 从阶段零开始执行，不跳过环境检查。
4. 阶段二和阶段四获批后，再继续后续阶段。

## 十一、参考文档

| 文件 | 用途 |
|------|------|
| `DEFINITIONS.md` | 阶段、角色、目录、超时、门禁单一事实源 |
| `reference-report-format.md` | 报告格式与占位符规范 |
| `reference-approval-mechanism.md` | 批准、拒绝、无响应与 No-Go 规则 |
| `reference-sandbox-spec.md` | 沙箱目录、生命周期与安全边界 |
| `reference-security-scan.md` | 安全扫描维度与判定规则 |
| `reference-external-case-sourcing.md` | 外部测试用例获取方法 |
| `reference-test-case-templates.md` | 用例模板与反模式清单 |
| `reference-skill-review-framework.md` | Skill 文档与结构审查框架 |
| `reference-agent-evaluation-methodology.md` | Agent/Skill 测试方法论 |
| `reference-flow-skill.md` | Flow A 详细模板 |
| `reference-flow-web-api.md` | Flow B 详细模板 |
| `reference-flow-android.md` | Flow C 详细模板 |
| `reference-flow-mcp.md` | Flow D 详细模板 |
| `reference-production-readiness.md` | 测试完成后的生产就绪检查项 |
| `reference-recovery.md` | 测试中断后的恢复与续跑机制 |

维护约束：

- 任何修改入口、流程、角色、参考文档、校验器或执行语义时，必须同步更新 `README.md` 和 `CHANGELOG.md`
