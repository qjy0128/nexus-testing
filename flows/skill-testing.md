# 流程 A：OpenClaw Skill 测试

> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**

## 触发条件

用户请求测试一个 OpenClaw Skill（包含 `skill` 关键词）。

## 测试目标

验证 Skill 的触发条件、工具调用、输出格式、错误处理、跨渠道适配，以及是否具备真实可执行入口。

## 执行步骤

### 阶段零：环境就绪检查

**执行角色**：主 agent

- 基础检查：Skill 源码路径、`SKILL.md` 可读性、YAML frontmatter 完整性。
- 依赖环境检测：识别 npm / Python / 系统命令依赖。
- 沙箱能力检测：确认 `scripts/sandbox-create.sh`、`scripts/sandbox-skill-invoke.sh`、`scripts/sandbox-multi-turn.sh` 可用。
- 真实执行能力检测：
  - `live`：OpenClaw CLI 可用。
  - `shim-live`：Skill 提供 `testing.json` 或 `scripts/test-entry.*`。
  - `trace`：仅剩静态追踪，**不能支撑功能通过结论**。

**需用户确认后才能进入阶段一。**

### 阶段一：需求解析

**执行角色**：`roles/requirement-analyst.md`  
输出：`SPEC.md`

### 阶段二：质量评估

**执行角色**：`roles/quality-assessor.md`  
输出：`PRODUCT-QUALITY-REVIEW.md`

**需批准后才能进入阶段三。**

### 阶段三：测试设计

**执行角色**：`roles/test-designer.md`  
输出：`TEST-DESIGN.md`

设计时必须为每条关键用例标明：

- 目标能力
- 是否要求真实执行
- 最低执行级别：`live` / `shim-live` / `trace`
- 是否需要显式断言：`triggerMatched` / `contextReferences` / `deliveryStatus`

### 阶段四：用例评估

**执行角色**：`roles/test-case-evaluator.md`  
输出：`TEST-CASE-REVIEW.md`

**需批准后才能进入阶段五。**

### 阶段五：并行测试执行

**并行角色（2 个）**：

- `roles/skill-tester.md`
- `roles/security-tester.md`

#### Skill 执行门禁

- P0/P1 功能用例默认执行：`sandbox-skill-invoke --mode auto --strict-real`
- 多轮对话用例默认执行：`sandbox-multi-turn --mode auto --strict-real`
- `auto --strict-real` 在存在独立 verifier 时优先 `shim-live`，否则优先 `live`
- 若走 `live --strict-real`，必须由 OpenClaw CLI 原生回传 `nexus-live-telemetry/v1`；没有协议或协议字段不完整时直接 blocker。
- 若走 `shim-live --strict-real`，必须提供独立的 `--verification-manifest`；路径必须位于 Skill 目录外，且在可识别仓库根时不能与 Skill 同仓库。没有 verifier 时不得返回成功。
- 只有 `live` / `shim-live` 可以写“通过”
- `trace` 只能写“静态追踪已完成，未完成真实执行”
- 负向触发必须显式得到 `triggerMatched=false`
- 上下文保持必须显式得到 `contextReferences`
- 渠道通过必须显式得到 `deliveryStatus` 和送达证据

#### 沙箱准备

当 `TEST-DESIGN.md` 标注 `执行环境：sandbox` 时：

1. `sandbox-create` 创建隔离 session
2. `sandbox-skill-invoke` / `sandbox-multi-turn` / `sandbox-exec` 执行用例
   可信命令可用 `--backend host-logged --ack-unsafe-exec`；不可信或高风险命令优先 `--backend container`
3. 收集日志、输出文件、结果 JSON、`exit-codes.json` 和 `META.json`
4. `sandbox-cleanup` 清理

#### 阶段五后：证据收集

**执行角色**：`roles/evidence-collector.md`  
输出：`DEFECTS/evidence-collection.md`

### 阶段六：缺陷分析

**执行角色**：`roles/defect-analyst.md`  
输出：`DEFECTS/DEFECT-REPORT.md`

### 阶段七：报告整合

**执行角色**：`roles/report-integrator.md`  
输出：`FINAL-TEST-REPORT.md`
