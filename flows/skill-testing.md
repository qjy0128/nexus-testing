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

**执行角色**：`roles/requirement-analyst.md` + `roles/spec-consistency-validator.md`  
输出：`PRODUCT-FINGERPRINT.json`、`SPEC.md`、`SPEC-CONSISTENCY-REVIEW.md`

阶段一必须先抽取事实，再写规格：

- `PRODUCT-FINGERPRINT.json` 必须写出技术栈、版本、许可证、运行时要求、真实入口、能力表面、CLI/子命令/插件表面
- 推荐直接使用 `scripts/generate_flow_a_stage1.py --target <repo-or-skill> --output-dir <report-dir>` 生成阶段一三件套，减少手写 `SPEC.md` 时的幻觉空间
- 每个关键字段都必须附证据来源（文件路径 + 行号或键路径）
- `SPEC.md` 只能基于 `PRODUCT-FINGERPRINT.json` 已验证字段展开，未知项写“待验证”
- `SPEC-CONSISTENCY-REVIEW.md` 必须校验版本、许可证、技术栈、入口能力和关键接口是否与仓库事实一致
- 若一致性校验结论不是 `passed`，不得进入阶段二

**主 agent 动作**：阶段一完成后立即发送 `SPEC.md` 和一致性结论摘要；`PRODUCT-FINGERPRINT.json` 作为阶段事实附件保存在报告目录。

### 阶段二：质量评估

**执行角色**：`roles/quality-assessor.md`  
输出：`PRODUCT-QUALITY-REVIEW.md`

输入前提：`SPEC-CONSISTENCY-REVIEW.md` 结论必须为 `passed`。

**主 agent 动作**：`PRODUCT-QUALITY-REVIEW.md` 生成后立即发送文件，并在同一轮明确发起批准请求。

**需批准后才能进入阶段三。**

### 阶段三：测试设计

**执行角色**：`roles/test-designer.md`  
输出：`TEST-DESIGN.md`、`SURFACE-EXECUTION-PLAN.json`

**主 agent 动作**：`TEST-DESIGN.md` 生成后立即发送文件和摘要，不等待用户索取。
`SURFACE-EXECUTION-PLAN.json` 必须按真实入口表面给阶段五分配执行面；`skill-tester` 不得只挑一个入口执行。

设计时必须为每条关键用例标明：

- 目标能力
- 是否要求真实执行
- 最低执行级别：`live` / `shim-live` / `trace`
- 是否需要显式断言：`triggerMatched` / `contextReferences` / `deliveryStatus`
- 引用的产品表面：来自 `PRODUCT-FINGERPRINT.json` 的真实入口（如 `SKILL.md`、CLI、plugin、MCP、hooks）

禁止行为：

- 从行业经验脑补 HTTP API、SDK、Go library、Guard.Scan() 等仓库中不存在的表面
- 未在 `PRODUCT-FINGERPRINT.json` 中出现的命令、端点、目录、子命令，不得写入 `TEST-DESIGN.md`

### 阶段四：用例评估

**执行角色**：`roles/test-case-evaluator.md`  
输出：`TEST-CASE-REVIEW.md`

**主 agent 动作**：`TEST-CASE-REVIEW.md` 生成后立即发送文件，并在同一轮明确发起批准请求。

**需批准后才能进入阶段五。**

### 阶段五：并行测试执行

**并行角色（2 个）**：

- `roles/skill-tester.md`
- `roles/security-tester.md`

阶段五开始前，主 agent 必须先基于 `SURFACE-EXECUTION-PLAN.json` 生成：
- `TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md`
- `TEST-EXECUTION/SURFACE-COVERAGE.json`
- 然后由 `skill-tester` 使用 `scripts/run_flow_a_skill_execution.py` 逐 surface 执行；runner 需要真实处理 `skill/bin`，对 `package/plugin-manifest` 输出结构化校验结果，并在存在显式 harness 时验证 `openclaw-extension` hook 行为与 `mcp` 协议交互，只有 probe-only 证据时才保守记为 `incomplete`

#### Skill 执行门禁

- P0/P1 功能用例默认执行：`sandbox-skill-invoke --mode auto --strict-real`
- 多轮对话用例默认执行：`sandbox-multi-turn --mode auto --strict-real`
- `auto --strict-real` 在存在独立 verifier 时优先 `shim-live`，否则优先 `live`
- 若走 `live --strict-real`，必须由 OpenClaw CLI 原生回传 `nexus-live-telemetry/v1`；没有协议或协议字段不完整时直接 blocker。
- 若走 `shim-live --strict-real`，必须提供独立的 `--verification-manifest`；路径必须位于 Skill 目录外，且在可识别仓库根时不能与 Skill 同仓库。没有 verifier 时不得返回成功。
- 只有 `live` / `shim-live` 可以写“通过”
- `skill-results.md` 必须按 `SKILL-SURFACE-WORKLIST.md` 的 surface 顺序逐条记录
- 阶段五结束后必须运行 `scripts/validate_flow_a_skill_results.py`，缺任何 surface 视为执行不完整
- `trace` 只能写“静态追踪已完成，未完成真实执行”
- 负向触发必须显式得到 `triggerMatched=false`
- 上下文保持必须显式得到 `contextReferences`
- 渠道通过必须显式得到 `deliveryStatus` 和送达证据
- 若阶段五只完成静态分析，不得给出 `PASS` / `PARTIAL PASS` / 功能覆盖率
- 静态分析只能产出 `blocked-no-real-exec`、`incomplete-static-review` 或“待真实执行复核”

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

**主 agent 动作**：`DEFECTS/evidence-collection.md` 生成后立即发送文件和摘要，不等待用户索取。

### 阶段六：缺陷分析

**执行角色**：`roles/defect-analyst.md`  
输出：`DEFECTS/DEFECT-REPORT.md`

**主 agent 动作**：`DEFECTS/DEFECT-REPORT.md` 生成后立即发送文件和摘要，不等待用户索取。

### 阶段七：报告整合

**执行角色**：`roles/report-integrator.md`  
输出：`FINAL-TEST-REPORT.md`

**主 agent 动作**：`FINAL-TEST-REPORT.md` 生成后立即发送文件和摘要，不等待用户索取。
