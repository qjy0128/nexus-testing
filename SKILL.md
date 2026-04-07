---
name: nexus-testing
description: Nexus AI 测试体系入口。根据用户目标自动分流到 Skill、网页+接口、安卓、MCP 四类流程，并按统一阶段产出结构化测试文档。
---

# Nexus Testing Orchestrator

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

- 主 agent 负责用户沟通、阶段推进、批准请求、最终结论
- subagent 只负责执行本角色任务并写入结果
- 阶段间上下文通过报告目录里的文件传递，不依赖聊天上下文转述
- Flow B 的 A/B 双模式定义以 `DEFINITIONS.md` 和 `flows/web-api-testing.md` 为准

## 四、标准阶段合同

```text
阶段零：环境就绪检查 -> 等待用户确认
阶段一：需求解析 -> SPEC.md
阶段二：质量评估 -> PRODUCT-QUALITY-REVIEW.md -> 等待批准
阶段三：测试设计 -> TEST-DESIGN.md
阶段四：用例评估 -> TEST-CASE-REVIEW.md -> 等待批准
阶段五：并行测试执行 -> TEST-EXECUTION/*.md
阶段五后：证据收集 -> DEFECTS/evidence-collection.md
阶段六：缺陷分析 -> DEFECTS/DEFECT-REPORT.md
阶段七：报告整合 -> FINAL-TEST-REPORT.md
```

输出目录统一为 `memory/nexus-reports/{date}-{test-type}-{flow}/`。

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
- 判断是否需要 `sandbox-create.sh`、`sandbox-exec.sh` 等沙箱脚本
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
- 需要批准时明确要求“批准 / 拒绝”
- 缺输入或 blocker 时，用最短清单向用户提问
- 不用模糊措辞代替阶段状态

Telegram / OpenClaw 文件发送硬约束：

- 发送交付物时必须显式提供 `caption`
- 无交互按钮时也必须显式提供 `buttons: []`，不得省略
- `caption` 至少包含文件摘要和下一步

文件发送示例（Telegram / OpenClaw）：

```text
message(action: "send", filePath: "memory/nexus-reports/{date}-{test-type}-{flow}/SPEC.md", caption: "阶段一需求规格已生成，已整理核心需求与验收点。下一步：进入阶段二质量评估。", buttons: [])
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
