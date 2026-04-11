# Skill 生产就绪检查清单

> 本文档定义被测 Skill 在测试完成后进入生产环境前的检查项。优先使用仓库里真实存在的脚本和交付物，不引用不存在的安全脚本或矩阵文件。

---

## 一、P0 Critical

> 任一阻断项未通过，禁止进入生产。

| 检查项 | 要求 | 验证方式 |
|--------|------|---------|
| 框架自检通过 | 仓库规范、脚本语法、链接一致性无阻断项 | `python scripts/validate-framework.py` |
| Skill 结构校验通过 | 结构、层级与关键入口满足最低要求 | `python scripts/skill-structure-validator.py {skill_dir} --json` |
| 阶段零依赖就绪 | 运行时、系统命令、沙箱能力满足测试设计需要 | 查看 `SPEC.md` 与阶段零环境就绪报告 |
| 关键用例有真实执行证明 | 每条关键用例都含动作、实际输入、实际输出、判定 | 查看 `TEST-EXECUTION/*.md`，规则见 `DEFINITIONS.md` 第十节 |
| 关键输出已核验 | 存在 golden/expected 输出时已完成比对 | `bash scripts/sandbox-verify-output.sh ...` 或 `bash scripts/sandbox-compare-output.sh ...` |
| 阻断缺陷已清零 | 无未解决 P0，核心路径无不可接受 P1 | 查看 `DEFECTS/DEFECT-REPORT.md` |
| 最终发布结论已生成 | 存在最终报告且结论明确 | 查看 `FINAL-TEST-REPORT.md` |

### P0 说明

- `sandbox-verify-output.sh` 适用于有结构化期望输出或 JSON 字段断言的场景。
- `sandbox-compare-output.sh` 适用于 golden file 对比或近似文本比对。
- 若项目没有 expected/golden 输出，必须在 `TEST-EXECUTION/*.md` 中保留足够的真实执行证据，不能用“未准备脚本”代替验证。

---

## 二、P1 High

> 不阻断发布，但应在进入稳定生产前收敛。

| 检查项 | 要求 | 验证方式 |
|--------|------|---------|
| 版本与变更记录明确 | 当前版本、关键变更、破坏性变更可追踪 | `README.md` + `CHANGELOG.md` |
| 测试覆盖说明完整 | 未覆盖范围、残余风险、降级执行原因写清楚 | `FINAL-TEST-REPORT.md` |
| 安全测试已完成 | 至少有独立安全测试结论与关键发现 | `TEST-EXECUTION/security-results.md` |
| 回归路径已验证 | 修复后的关键路径完成复测 | `TEST-EXECUTION/retest-*.md` 或最终报告中的回归章节 |
| 运行环境约束清楚 | 依赖的 Node/Python/外部命令/插件已写明 | `SPEC.md`、环境就绪报告 |

---

## 三、P2 Medium

> 建议项，用于降低后续维护和事故成本。

| 检查项 | 说明 |
|--------|------|
| 预期输出资产沉淀 | 为关键能力补齐 `expected-outputs/` 或 golden 文件 |
| 生产回滚预案 | 明确回滚入口、关闭开关、降级路径 |
| 监控与告警 | 明确线上成功率、延迟、错误率指标 |
| 运维操作手册 | 记录初始化、依赖安装、常见故障排查 |

---

## 四、推荐检查顺序

```text
1. 运行 validate-framework.py，确认仓库本身没有结构问题
2. 运行 skill-structure-validator.py，确认被测 Skill 结构满足最低要求
3. 审查阶段零环境就绪报告，确认依赖与运行时满足要求
4. 审查 TEST-EXECUTION/*.md，确认关键用例有真实执行证明
5. 如存在期望输出，使用 compare/verify 脚本完成输出核验
6. 审查 DEFECT-REPORT.md，确认阻断缺陷已清零
7. 审查 FINAL-TEST-REPORT.md，生成最终 Go / Conditional / No-Go 结论
```

---

## 五、结论规则

- `Go`：所有 P0 通过，P1 仅剩可接受风险
- `Conditional Go`：P0 通过，但存在明确的 P1 遗留项和发布时间窗口约束
- `No-Go`：任一 P0 未通过，或关键路径仍存在无法接受的残余风险

建议在最终报告中保留如下结论摘要：

```text
生产建议：Go / Conditional Go / No-Go
阻断项：{如有，逐条列出}
残余风险：{最多 3 条，高优先级优先}
前置动作：{上线前必须完成的事项}
```
