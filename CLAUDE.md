# CLAUDE.md — Nexus Testing Framework

## 项目概述

Nexus Testing 是一个多 Flow AI 测试编排框架，用于测试 OpenClaw Skill、网页/接口、安卓应用和 MCP Server。主入口是 `SKILL.md`。

## 核心架构

- **单一事实源**: `DEFINITIONS.md` — 所有阶段、角色、超时、门禁的唯一权威定义
- **4 个 Flow**: `flows/skill-testing.md` (A), `flows/web-api-testing.md` (B), `flows/android-testing.md` (C), `flows/mcp-testing.md` (D)
- **19 个角色**: `roles/*.md` — 每个角色有 frontmatter、输入来源、下游消费者
- **沙箱执行**: `scripts/sandbox-*.sh` + Python 包 `scripts/sandbox_skill_invoke/`
- **安全扫描**: `scripts/security-scanner.py` — 自动化 S1-S4 检测规则
- **元测试 Fixtures**: `scripts/fixtures/` — pass/defect/extreme 三个样例 Skill

## 关键约定

1. **不要重复定义**: DEFINITIONS.md 已有的规则，Flow/Role 文件只引用不重写
2. **文档优先级**: Flow > Reference > DEFINITIONS.md > Role > SKILL.md
3. **降级阶梯**: 完整定义在 `reference-sandbox-spec.md`，DEFINITIONS.md 只做速查引用
4. **输出目录**: `memory/nexus-reports/{date}-{test-type}-{flow}/`
5. **运行期产物**: `memory/nexus-reports/` 和 `.nexus-sandbox/` 不入库（已 .gitignore）

## 编辑规范

- 修改流程/角色/参考文档后，先跑 `python scripts/validate-framework.py`
- Shell 脚本用 LF 换行
- 运行期文件不要提交到 git
- 修改 DEFINITIONS.md 时确保 `validate_definition_consistency` 仍能通过
- 新增脚本文件需要在 `validate-framework.py` 的 `REQUIRED_*` 列表中注册

## 验证

```bash
python scripts/validate-framework.py        # 结构校验
python scripts/security-scanner.py <dir>     # 安全扫描
python scripts/test_sandbox_lifecycle.py     # E2E 生命周期测试
```

## 参考文档

| 文件 | 用途 |
|------|------|
| `DEFINITIONS.md` | 阶段、角色、门禁、超时单一事实源 |
| `reference-sandbox-spec.md` | 沙箱执行环境完整规格 |
| `reference-security-scan.md` | 安全扫描六阶段规则 |
| `reference-approval-mechanism.md` | 批准/拒绝/无响应规则 |
| `reference-recovery.md` | 测试中断后的恢复/续跑机制 |
| `reference-report-format.md` | 报告输出格式规范 |
| `reference-production-readiness.md` | 生产就绪检查清单 |
