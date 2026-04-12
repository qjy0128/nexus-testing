# 流程 A：OpenClaw Skill 测试

> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**

## 触发条件

用户请求测试一个 OpenClaw Skill（包含 `skill` 关键词）。

## 测试目标

验证 Skill 的触发条件、工具调用、输出格式、错误处理、跨渠道适配，以及是否具备真实可执行入口。

## 执行步骤

### 阶段零：环境就绪检查

**执行角色**：`roles/environment-checker.md`

- 主 agent 应先生成 `STAGE-SUBAGENT-PLAN.json`，再按该计划启动阶段零角色。
- 基础检查：Skill 源码路径、`SKILL.md` 可读性、YAML frontmatter 完整性。
- 依赖环境检测：识别 npm / Python / 系统命令依赖。
- 沙箱能力检测：确认 `scripts/sandbox-create.sh`、`scripts/sandbox-skill-invoke.sh`、`scripts/sandbox-multi-turn.sh` 可用。
- 真实执行能力检测：
  - `live`：OpenClaw CLI 可用。
  - `shim-live`：Skill 提供 `testing.json` 或 `scripts/test-entry.*`。
  - `trace`：仅剩静态追踪，**不能支撑功能通过结论**。
- 若当前测试运行时本身就是 OpenClaw / 可拉起 subagent，则不得仅因通用 runner 未接线就写“OpenClaw runtime unavailable”；必须先做实际探测，或通过 `testing.json` 的显式 harness 验证真实运行时行为。

**需用户确认后才能进入阶段一。**

### 阶段一：需求解析

**执行角色**：`roles/requirement-analyst.md` + `roles/spec-consistency-validator.md`  
输出：`PRODUCT-FINGERPRINT.json`、`SPEC.md`、`SPEC-CONSISTENCY-REVIEW.md`

阶段一必须先抽取事实，再写规格：

- `PRODUCT-FINGERPRINT.json` 必须写出技术栈、版本、许可证、运行时要求、真实入口、能力表面、CLI/子命令/插件表面
- 对复杂安全 Skill，阶段一不能只读 `SKILL.md`；还必须继续下钻伴随规则文件、策略文件、检查清单和相关源码（例如 `scan-rules.md`、`action-policies.md`、`patrol-checks.md` 这类 companion docs / source），把规则、决策路径、检查项 inventory 抽进 `PRODUCT-FINGERPRINT.json`
- 推荐直接使用 `scripts/generate_flow_a_stage1.py --target <repo-or-skill> --output-dir <report-dir>` 生成阶段一三件套，减少手写 `SPEC.md` 时的幻觉空间
- 每个关键字段都必须附证据来源（文件路径 + 行号或键路径）
- `SPEC.md` 只能基于 `PRODUCT-FINGERPRINT.json` 已验证字段展开，未知项写“待验证”
- `SPEC-CONSISTENCY-REVIEW.md` 必须校验版本、许可证、技术栈、入口能力和关键接口是否与仓库事实一致
- 若一致性校验结论不是 `passed`，不得进入阶段二

**主 agent 动作**：阶段一完成后先用 `prepare_report_delivery.py` 把阶段文件镜像到 `files/...`，再立即发送 `SPEC.md` 和一致性结论摘要；`PRODUCT-FINGERPRINT.json` 作为阶段事实附件保存在报告目录。

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

复杂 Skill / 安全工具的测试设计必须数据驱动展开：

- 规则清单：每条规则至少覆盖“能检出”和“不误报”
- 决策路径：每条路径（如 `DENY` / `CONFIRM`）至少 1 个独立用例
- 检查项：每项 patrol / runtime / monitor 检查至少 1 个真实执行用例
- 若事实指纹未抽取到规则、决策路径、检查项 inventory，不得把 1 条泛化 capability 用例写成“覆盖完成”

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
- 然后由 `skill-tester` 使用 `scripts/run_flow_a_skill_execution.py` 逐 surface 执行；runner 需要真实处理 `skill/bin`，对 `package/plugin-manifest` 输出结构化校验结果
- `openclaw-extension` 类型 Skill 的 `openclawExtensionRuntimeHarness` 优先级链、伴随规则文件完整性与 fallback 路径，见 `docs/references/reference-openclaw-extension-testing.md`

#### Skill 执行门禁

> 执行降级阶梯与合规要求（`live`/`shim-live`/`trace` 判定标准、`--strict-real` 要求、负向触发/上下文/渠道断言要求）
> 见 `DEFINITIONS.md` 第十节「执行验证标准」，阶段五所有角色须严格遵循，不得自行重新定义。

**Flow A 特有执行门禁：**

- P0/P1 功能用例默认执行：`sandbox-skill-invoke --mode auto --strict-real`
- 多轮对话用例默认执行：`sandbox-multi-turn --mode auto --strict-real`
- `skill-results.md` 必须按 `SKILL-SURFACE-WORKLIST.md` 的 surface 顺序逐条记录
- 阶段五结束后必须运行 `scripts/validate_flow_a_skill_results.py`，缺任何 surface 视为执行不完整
- 若 subagent runtime 因 OpenClaw Gateway、`mcp__web_reader__webReader`、真实执行环境缺失等原因无法完成测试，宿主 runtime 应先尝试该角色的 fallback runtime；仍失败时必须产出 `takeover-required` 工单，交由主 agent 在当前 host session 接管
- 对纯指令型 Skill，主 agent 接管优先走框架内置的 host takeover executor，而不是要求被测仓库预先提供 `testing.json`；只有通用 host takeover 无法表达的私有运行时行为，才回退到 skill 私有 harness

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

