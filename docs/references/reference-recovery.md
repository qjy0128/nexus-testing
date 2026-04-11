# 测试恢复与续跑机制

> 当测试执行在中间阶段中断（agent 崩溃、超时、用户中断）时，使用本文件定义的恢复流程从断点继续，而非从头重跑。

---

## 一、恢复原理

测试流程的每一步都会产出文件到报告目录。恢复机制依赖这些文件判断"最后完成到哪一步"，然后从下一阶段继续。

**关键文件**：`stage-transition-log.json`（阶段转换审计日志）

---

## 二、恢复流程

```text
恢复启动
  │
  ├─ 1. 定位报告目录
  │     └─ memory/nexus-reports/{date}-{test-type}-{flow}/
  │
  ├─ 2. 读取 stage-transition-log.json
  │     └─ 找到最后一条 to_stage 记录
  │
  ├─ 3. 验证该阶段交付物文件存在
  │     └─ 阶段零 → STAGE-SUBAGENT-PLAN.json
  │     └─ 阶段一 → PRODUCT-FINGERPRINT.json + SPEC.md + SPEC-CONSISTENCY-REVIEW.md
  │     ┘─ 阶段二 → PRODUCT-QUALITY-REVIEW.md
  │     ┘─ 阶段三 → TEST-DESIGN.md + SURFACE-EXECUTION-PLAN.json
  │     ┘─ 阶段四 → TEST-CASE-REVIEW.md
  │     ┘─ 阶段五 → TEST-EXECUTION/*.md
  │     ┘─ 阶段六 → DEFECTS/DEFECT-REPORT.md
  │     ┘─ 阶段七 → FINAL-TEST-REPORT.md
  │
  ├─ 4. 交付物存在 → 从下一阶段继续
  │     └─ 需批准阶段（二/四）检查 approval-records.json
  │
  └─ 5. 交付物缺失 → 从该阶段重新执行
        └─ 在报告中标注「恢复重跑」
```

---

## 三、阶段交付物验证表

| 阶段 | 交付物 | 存在则已完成 | 批准状态检查 |
|------|--------|-------------|-------------|
| 阶段零 | `STAGE-SUBAGENT-PLAN.json` + 环境就绪报告（内存中） | ✅（计划文件存在）且需用户确认 | — |
| 阶段一 | `PRODUCT-FINGERPRINT.json` + `SPEC.md` + `SPEC-CONSISTENCY-REVIEW.md` | ✅ | — |
| 阶段二 | `PRODUCT-QUALITY-REVIEW.md` | ✅ | 检查 `approval-records.json` |
| 阶段三 | `TEST-DESIGN.md` + `SURFACE-EXECUTION-PLAN.json` | ✅ | — |
| 阶段四 | `TEST-CASE-REVIEW.md` | ✅ | 检查 `approval-records.json` |
| 阶段五 | `TEST-EXECUTION/*.md` | ✅ 且文件数 ≥ 并行角色数 | — |
| 阶段六 | `DEFECTS/DEFECT-REPORT.md` | ✅ | — |
| 阶段七 | `FINAL-TEST-REPORT.md` | ✅ | — |

---

## 四、阶段五部分完成恢复

阶段五有多个并行角色，可能出现部分完成的情况：

### 判定规则

| 情况 | 判定 | 恢复动作 |
|------|------|---------|
| 所有并行角色结果文件存在 | 完整完成 | 继续到 evidence-collector |
| 部分结果文件存在 | 部分完成 | 重跑缺失角色的 subagent |
| 无结果文件 | 未完成 | 完整重跑阶段五 |

### 部分完成恢复步骤

1. 读取 `TEST-EXECUTION/` 目录，列出已有结果文件
2. 对比 `DEFINITIONS.md` 第四节该 Flow 的并行角色列表
3. 缺失的角色重新启动对应 subagent
4. 保留已有的结果文件，不覆盖
5. 所有角色完成后，启动 evidence-collector subagent

若已启用 `RUNS/` 运行清单：
- 读取 `RUNS/<stage>/<role>.state.json`
- `status=completed` 的角色跳过
- `status=failed` 的角色优先重试
- `status=running` 但无新日志增长时，可按宿主 runtime 已中断处理并重新启动

## 四-B、串行阶段恢复

阶段零到阶段四、阶段六、阶段七虽然是串行推进，但每个阶段也默认由对应阶段角色 subagent 执行。

| 阶段 | 默认恢复动作 |
|------|-------------|
| 阶段零 | 重启 `environment-checker` |
| 阶段一 | 缺 `PRODUCT-FINGERPRINT.json` / `SPEC.md` 时重启 `requirement-analyst`；缺 `SPEC-CONSISTENCY-REVIEW.md` 时重启 `spec-consistency-validator` |
| 阶段二 | 重启 `quality-assessor` |
| 阶段三 | 重启 `test-designer` |
| 阶段四 | 重启 `test-case-evaluator` |
| 阶段六 | 重启 `defect-analyst` |
| 阶段七 | 重启 `report-integrator` |

---

## 五、批准状态恢复

中断发生在需批准阶段（二/四）时：

| `approval-records.json` 状态 | 恢复动作 |
|------------------------------|---------|
| `user_response: "approved"` | 直接进入下一阶段 |
| `user_response: null` 或缺失 | 重新发送交付物并请求批准 |
| `user_response: "auto-continue"` | 视为已批准，继续 |
| `user_response: "rejected"` | 按打回规则回到上一阶段 |

---

## 六、拒绝计数恢复

读取 `rejection-count.json`：

- 文件存在且有有效 `count` → 继承当前拒绝计数
- 文件缺失 → 按 0 处理
- 文件损坏 → 重置为 0，在报告中标注

---

## 七、恢复报告格式

恢复时在 `stage-transition-log.json` 中追加恢复记录：

```json
{
  "from_stage": "recovery",
  "to_stage": 3,
  "timestamp": "YYYY-MM-DD HH:mm:ss",
  "deliverable_file": "TEST-DESIGN.md",
  "recovery": true,
  "recovery_reason": "agent crash during stage 3",
  "resumed_from_partial": false
}
```

---

## 八、不可恢复的情况

以下情况必须从头开始新测试流程：

| 情况 | 原因 |
|------|------|
| 报告目录不存在 | 无法定位任何历史状态 |
| `stage-transition-log.json` 损坏 | 无法确定断点 |
| 阶段零未完成 | 环境状态不可信 |
| 用户主动要求重新开始 | 用户指令优先 |
