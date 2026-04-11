# Skill Tier 验证机制

> 本文档说明 Skill 的 Tier 分级体系和验证方法。

## 概述

Skill Tier 是 OpenClaw 生态中的 Skill 质量分级制度，类似于编程语言的版本控制或课程的难度等级。Tier 越高，Skill 需要满足的要求越严格。

## Tier 级别

| Tier | 定位 | SKILL.md 行数 | 脚本数量 | 每脚本行数 | 必须目录 |
|------|------|--------------|----------|-----------|---------|
| **BASIC** | 基础 | ≥100 行 | ≥1 | 50-300 LOC | scripts/ |
| **STANDARD** | 标准 | ≥200 行 | ≥1 | 150-500 LOC | scripts/, assets/, references/ |
| **POWERFUL** | 强大 | ≥300 行 | ≥2 | 300-800 LOC | scripts/, assets/, references/, expected_outputs/ |

## Tier 要求详解

### BASIC Tier

**适用场景**：简单工具、单脚本 Skill

**要求**：
- SKILL.md ≥ 100 行
- scripts/ 目录存在
- 至少 1 个受支持脚本（Python / JavaScript / TypeScript），50-300 LOC
- 推荐功能：CLI 参数解析、明确入口点

### STANDARD Tier

**适用场景**：中等复杂度 Skill、多功能工具

**要求**：
- SKILL.md ≥ 200 行
- scripts/、assets/、references/ 目录存在
- 至少 1 个受支持脚本（Python / JavaScript / TypeScript），150-500 LOC
- 必须功能：CLI 参数解析、明确入口点、机器可读输出、错误处理

### POWERFUL Tier

**适用场景**：复杂 Skill、系统工具

**要求**：
- SKILL.md ≥ 300 行
- scripts/、assets/、references/、expected_outputs/ 目录存在
- 至少 2 个受支持脚本（Python / JavaScript / TypeScript），每个 300-800 LOC
- 必须功能：CLI 参数解析、明确入口点、机器可读输出、错误处理、帮助文本

## 验证命令

### 基本验证

```bash
# 验证 Skill 结构（自动检测 Tier）
python scripts/skill-structure-validator.py /path/to/skill

# 指定目标 Tier 验证
python scripts/skill-structure-validator.py /path/to/skill --tier POWERFUL

# JSON 输出（适合程序处理）
python scripts/skill-structure-validator.py /path/to/skill --json

# 详细输出
python scripts/skill-structure-validator.py /path/to/skill --verbose
```

### 预期输出示例

```
================================================================
SKILL STRUCTURE VALIDATION REPORT
================================================================
Skill: /path/to/agentguard
Timestamp: 2026-04-06T10:30:00Z
Overall Score: 85.0/100 (GOOD)
Detected Tier: STANDARD

CHECKS:
  ✓ SKILL.md found
  ✓ SKILL.md has 280 lines (≥200)
  ✓ Required frontmatter fields present
  ✓ All required sections present
  ✓ README.md found
  ✓ README.md has substantial content
  ✓ scripts/ found
  ✓ Found 3 supported script(s)
  ✓ action-cli.ts: 150 LOC
  ✓ trust-cli.ts: 120 LOC
  ✓ checkup-report.js: 450 LOC
  ✓ action-cli.ts: valid TypeScript syntax
  ✓ trust-cli.ts: valid TypeScript syntax
  ✓ checkup-report.js: valid JavaScript syntax
  ✓ action-cli.ts: uses a CLI parser
  ✓ trust-cli.ts: uses a CLI parser
  ✓ action-cli.ts: has an entrypoint
  ✓ trust-cli.ts: has an entrypoint
  ✓ All scripts use built-in modules only
  ✓ Detected tier: STANDARD

WARNINGS:
  ⚠ checkup-report.js should declare an executable entrypoint
  ⚠ checkup-report.js should expose argument parsing

ERRORS:
  ✗ Scripts use external imports: checkup-report.js: yaml, requests

SUGGESTIONS:
  → Add missing sections: Troubleshooting
  → Optional directories found: expected_outputs, tests

EXTERNAL IMPORTS DETECTED:
  checkup-report.js: yaml, requests
```

## 在测试中使用

### TEST-DESIGN.md 中指定 Tier

```markdown
## Skill Tier 要求

• 目标 Tier：POWERFUL
• 验证命令：`python scripts/skill-structure-validator.py {skill_path} --tier POWERFUL`

### 验证结果

| 检查项 | 结果 | 说明 |
|--------|------|------|
| SKILL.md 行数 ≥ 300 | ✅ 320 行 | |
| 脚本数量 ≥ 2 | ✅ 3 个 | |
| expected_outputs/ 存在 | ✅ | |
| 内建模块依赖 | ❌ | checkup-report.js 使用了 yaml, requests |
```

### 缺陷报告中的 Tier 问题

如果被测 Skill 不满足目标 Tier，应报告为 P1 缺陷：

```markdown
### BUG-001：Tier 不达标 - 使用外部依赖

• 严重级别：P1
• 类型：代码质量
• 描述：checkup-report.js 使用了外部依赖（yaml, requests），不符合 POWERFUL Tier 的内建模块要求
• 位置：agentguard/scripts/checkup-report.js
• 修复建议：替换为内建模块实现，或降低 Tier 目标并在测试设计中显式声明依赖
```

## 常见问题

### Q1：为什么限制使用外部依赖？

**原因**：
1. **可移植性**：内建模块在目标运行时中默认可用
2. **安全性**：减少供应链攻击面
3. **简单性**：减少额外安装步骤，降低使用门槛

**替代方案**：
- Python：优先使用 `urllib`、`json`、`pathlib` 等标准库
- JavaScript / TypeScript：优先使用 Node 内建模块（如 `fs`、`path`、`url`）

### Q2：SKILL.md 行数怎么算？

只计算非空行（包括 markdown 语法），不含空行。

### Q3：LOC（代码行数）怎么算？

只计算非空、非注释行。

### Q4：Tier 不达标怎么办？

根据目标选择：
- **降低目标 Tier**：如果 Skill 很简单，设为 BASIC
- **补齐缺失项**：添加目录、扩展文档
- **重构代码**：替换外部依赖为目标运行时的内建模块

---

## OpenClaw Tier 体系对比

| 特性 | OpenClaw | Nexus Testing |
|------|----------|--------------|
| Tier 分级 | ✅ | ✅ |
| 自动检测 | ✅ | ✅ |
| 强制验证 | - | 可选（通过 --tier 指定） |
| 外部依赖检查 | ✅ | ✅ |
| 目录结构检查 | ✅ | ✅ |
| 脚本复杂度检查 | ✅ | ✅ |
| 集成 Sandbox | - | ✅ |
