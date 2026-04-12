---
title: 操作规程与参考文档
scope: nexus-testing
---

# 操作规程与参考文档

本文承接 `SKILL.md` 中的沟通约束、执行原则、快速开始指引及参考文档索引，供主 agent 在运行期查阅。

---

## 沟通约束

只保留必要规则：

- 每阶段独立发送交付物和简要摘要
- 交付物生成后立即主动发送，不等待用户追问
- 所有交付物的描述性内容必须使用用户**发起测试请求的语言**；代码、命令、路径、协议名保持原样
- 需要批准时明确要求"批准 / 拒绝"
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

---

## 执行原则

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

---

## 快速开始

1. 将仓库作为 OpenClaw Skill 项目打开，入口使用 `SKILL.md`。
2. 提供待测对象：Skill 路径、URL/API、APK 或 MCP Server 信息。
3. 从阶段零开始执行，不跳过环境检查。
4. 阶段二和阶段四获批后，再继续后续阶段。

---

## 参考文档索引

| 文件 | 用途 |
|------|------|
| `DEFINITIONS.md` | 阶段、角色、目录、超时、门禁单一事实源 |
| `docs/references/reference-report-format.md` | 报告格式与占位符规范 |
| `docs/references/reference-approval-mechanism.md` | 批准、拒绝、无响应与 No-Go 规则 |
| `docs/references/reference-sandbox-spec.md` | 沙箱目录、生命周期与安全边界 |
| `docs/references/reference-security-scan.md` | 安全扫描维度与判定规则 |
| `docs/references/reference-security-blacklist.md` | 安全黑名单与禁用模式 |
| `docs/references/reference-external-case-sourcing.md` | 外部测试用例获取方法 |
| `docs/references/reference-test-case-templates.md` | 用例模板与反模式清单 |
| `docs/references/reference-skill-tier-requirements.md` | Skill 分层要求与层级判定 |
| `docs/references/reference-skill-review-framework.md` | Skill 文档与结构审查框架 |
| `docs/references/reference-agent-evaluation-methodology.md` | Agent/Skill 测试方法论 |
| `docs/references/reference-flow-skill.md` | Flow A 详细模板 |
| `docs/references/reference-flow-web-api.md` | Flow B 详细模板 |
| `docs/references/reference-flow-android.md` | Flow C 详细模板 |
| `docs/references/reference-flow-mcp.md` | Flow D 详细模板 |
| `docs/references/reference-expected-outputs.md` | 各阶段预期输出清单 |
| `docs/references/reference-output-verification-examples.md` | 输出验证示例 |
| `docs/references/reference-production-readiness.md` | 测试完成后的生产就绪检查项 |
| `docs/references/reference-recovery.md` | 测试中断后的恢复与续跑机制 |
| `docs/references/reference-operational-procedures.md` | 沟通约束、执行原则、快速开始（本文件） |

维护约束：任何修改入口、流程、角色、参考文档、校验器或执行语义时，必须同步更新 `README.md` 和 `CHANGELOG.md`。
