# Nexus Testing Framework

基于 OpenClaw 平台的多类型 AI 测试编排框架。自动识别测试类型，调度 8 阶段标准化测试流程，通过并行 subagent 执行测试，产出结构化报告并提供 Go/No-Go 判定。

## 支持的测试类型

| 测试类型 | Flow | 关键词 | 阶段五并行角色数 |
|---------|------|--------|----------------|
| Skill 测试 | Flow A | Skill / skill | 2（skill-tester + security-tester） |
| 网页+接口测试 | Flow B | 网页 / 页面 / web / 接口 / API | 5（functional + compatibility + security + performance + accessibility） |
| 安卓测试 | Flow C | APK / 安卓 / android | 5（functional + compatibility + security + performance + reality-checker） |
| MCP 测试 | Flow D | MCP / mcp | 4（mcp-tester + security + performance + reality-checker） |

系统根据用户输入的关键词自动识别测试类型并路由到对应 Flow。支持同时请求多种测试类型时选择串行或并行执行。

## 工作模式

**生成模式（默认）**：从零创建测试计划、设计用例、执行测试、输出报告。

**评审模式**：对已有的测试报告或文档进行符合性检查，输出评审报告（含必改项 / 建议项 / 可选项）。

## 8 阶段执行流程

```
阶段零：环境就绪检查 → 强制执行，等待用户确认
阶段一：需求解析 → 生成 SPEC.md
阶段二：质量评估 → 生成 PRODUCT-QUALITY-REVIEW.md → 需用户批准
阶段三：测试设计 → 生成 TEST-DESIGN.md
阶段四：用例评估 → 生成 TEST-CASE-REVIEW.md → 需用户批准
阶段五：并行测试执行 → 各测试工程师 subagent 并行执行
       ↓
阶段五后：证据收集 → evidence-collector（所有 subagent 完成后执行）
       ↓
阶段六：缺陷分析 → DEFECTS/DEFECT-REPORT.md（支持打回，最多 3 轮）
阶段七：报告整合 → FINAL-TEST-REPORT.md（含 Go/No-Go 判定）
```

### Flow B 双模式

Flow B 支持 A 模式（文档完整，标准 8 阶段）和 B 模式（文档不全，10 阶段）。B 模式在标准阶段间插入双边深度体验、交叉核对、争议复检三个独有阶段，由 experience-tester-a 和 experience-tester-b 独立探索后交叉验证。

## 项目结构

```
nexus-testing/
├── SKILL.md                            # 主入口，测试编排器
├── DEFINITIONS.md                      # 单一事实源（阶段/角色/超时/Token 等统一定义）
├── CHANGELOG.md                        # 版本变更记录
├── flows/                              # 测试流程定义
│   ├── skill-testing.md                # Flow A：Skill 测试
│   ├── web-api-testing.md              # Flow B：网页+接口测试
│   ├── android-testing.md              # Flow C：安卓 APK 测试
│   └── mcp-testing.md                  # Flow D：MCP Server 测试
├── roles/                              # 角色定义（19 个）
│   ├── requirement-analyst.md          # 需求解析师
│   ├── quality-assessor.md             # 质量评估师
│   ├── test-designer.md                # 测试设计师
│   ├── test-case-evaluator.md          # 用例评估师
│   ├── defect-analyst.md               # 缺陷分析师
│   ├── report-integrator.md            # 报告整合师
│   ├── skill-tester.md                 # Skill 测试工程师（Flow A）
│   ├── security-tester.md              # 安全测试工程师（Flow A/B/C/D）
│   ├── functional-tester.md            # 功能测试工程师（Flow B/C）
│   ├── compatibility-tester.md         # 兼容性测试工程师（Flow B/C/D）
│   ├── performance-tester.md           # 性能测试工程师（Flow B/C/D）
│   ├── accessibility-auditor.md        # 无障碍审计工程师（Flow B）
│   ├── mcp-tester.md                   # MCP 测试工程师（Flow D）
│   ├── reality-checker.md              # 真实场景测试工程师（Flow C/D）
│   ├── experience-tester-a.md          # 体验工程师 A（Flow B 模式）
│   ├── experience-tester-b.md          # 体验工程师 B（Flow B 模式）
│   ├── evidence-collector.md           # 证据收集工程师
│   ├── tool-evaluator.md               # 工具评估（按需触发）
│   └── workflow-optimizer.md           # 流程优化（按需触发）
├── reference-approval-mechanism.md     # 批准机制完整规范
├── reference-flow-skill.md             # Flow A 用例模板
├── reference-flow-web-api.md           # Flow B 用例模板
├── reference-flow-android.md           # Flow C 用例模板
├── reference-flow-mcp.md              # Flow D 用例模板
├── reference-report-format.md          # 报告格式与占位符规范
├── reference-security-blacklist.md     # XSS 注入字符黑名单
└── reference-security-scan.md          # 六阶段安全扫描规范
```

## 报告输出

所有测试报告输出到 `memory/nexus-reports/{date}-{test-type}-{flow}/`：

```
{date}-{test-type}-{flow}/
├── SPEC.md                          # 阶段一：需求规格
├── PRODUCT-QUALITY-REVIEW.md        # 阶段二：质量评估
├── TEST-DESIGN.md                   # 阶段三：测试设计
├── TEST-CASE-REVIEW.md              # 阶段四：用例评估
├── TEST-EXECUTION/                  # 阶段五：各角色测试结果
│   ├── skill-results.md
│   ├── security-results.md
│   └── ...
├── DEFECTS/                         # 阶段六：缺陷报告
│   ├── DEFECT-REPORT.md
│   └── evidence/
├── FINAL-TEST-REPORT.md             # 阶段七：最终报告
└── archive/                         # 复测归档
```

## 关键特性

### 真实执行原则（反偷懒机制）

每个测试用例必须包含执行证明：具体执行动作、真实输入参数、真实输出结果、判定结论。读文档不等于测试，静态分析不等于验证。环境不足时按 5 级降级阶梯执行（真实执行 → 沙箱 → 模拟 → 部分 → 静态分析），禁止直接跳过。

执行率要求：≥90% 正常通过，70%-89% 标注覆盖不足，50%-69% 强制打回，<50% 直接 No-Go。

### 阶段门禁

阶段二和阶段四必须等待用户显式批准后才可推进。每阶段最多拒绝 3 次，第 3 次自动 No-Go。拒绝计数通过 HMAC-SHA256 签名防篡改。每次阶段转换写入审计日志。

### 并行执行

阶段五的所有测试工程师 subagent 同时启动、独立计时（单次上限 15 分钟），互不等待。evidence-collector 在所有 subagent 完成后独立执行。

### 六阶段安全扫描

覆盖提示词注入、恶意代码、凭证泄露、结构命令、供应链、权限审计六个维度，产出 SAFE / REVIEW / BLOCKED 三级判定。

### 缺陷打回闭环

阶段六发现缺陷后可打回阶段五重新测试，最多 3 轮。修复后支持增量复测：P0 全量重跑、P1 关联模块复测、P2/P3 单用例复测。

### 回归套件

自动从测试结果中提取四级回归套件：Smoke（15-30min，核心路径）、Sanity（10-15min，热修复验证）、Targeted（30-60min，变更影响范围）、Full（2-4h，全量）。

## 支持的渠道

Telegram、飞书、QQ、微信。微信和 QQ 采用"先文字后文件"的降级发送策略。

## 当前版本

v0.9.8 — 详见 [CHANGELOG.md](CHANGELOG.md)
