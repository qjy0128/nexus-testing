# Nexus Testing Framework — 变更记录

> 本文件记录所有历史版本中的已废弃名称、矛盾表述和重大变更，供 Review 和调试参考。**agent 执行时不应依赖此文件，所有定义以 DEFINITIONS.md 为准。**

---

## 废弃命名表（禁止使用）

| 废弃名称 | 正确名称 | 废弃版本 | 说明 |
|---------|---------|---------|------|
| `QUALITY-ASSESSMENT.md` | `PRODUCT-QUALITY-REVIEW.md` | v0.6.3 | 阶段二输出文件名 |
| `TEST-CASE-EVALUATION.md` | `TEST-CASE-REVIEW.md` | v0.6.3 | 阶段四输出文件名 |

---

## 废弃矛盾表述（以新值为准）

| 废弃表述 | 正确值 | 来源版本 | 说明 |
|---------|-------|---------|------|
| 「最多 30 分钟」subagent 超时 | **15 分钟（900 秒）** | v0.6.3 | 旧版 SKILL.md 中 subagent 超时有 15 分钟和 30 分钟两种表述，已统一为 15 分钟 |
| 「最多 15 分钟」并行总时长 | **15 分钟（900 秒）** | v0.6.3 | 同上，已统一 |

---

## 重大版本变更

### v0.9.24（2026-04-06）
**sandbox-exec 容器后端落地 + 审计增强**

**执行后端（4 项）**
- 新增：`sandbox-exec.sh` 支持 `--backend host-logged|container`，其中 `container` 可通过 `docker` / `podman` 运行容器化命令。
- 新增：容器后端支持 `--container-runtime`、`--container-image`、`--container-workdir`、`--allow-network`，默认挂载当前 session 的 `workspace/` 到容器内并关闭网络。
- 调整：`--ack-unsafe-exec` 只对 `host-logged` 后端强制；`container` 后端不再要求这类“口头确认”替代技术隔离。
- 增强：`sandbox-exec` 输出和 `exit-codes.json` 现在会记录 `backend`、`isolationLevel`、`containerRuntime`、`containerImage`、`networkAccess`。

**回归与规格（3 项）**
- 新增：`scripts/test_sandbox_exec_container.py`，覆盖 `host-logged` 无确认失败、`container` probe、默认断网、显式放开网络等 smoke case。
- 更新：`validate-framework.py` 与 GitHub Actions 将 `test_sandbox_exec_container.py` 纳入 Python 编译和 runtime smoke tests。
- 更新：`DEFINITIONS.md`、`reference-sandbox-spec.md`、`flows/skill-testing.md`、`roles/skill-tester.md`、`reference-output-verification-examples.md` 统一到新的 host/container 双后端口径。

---

### v0.9.23（2026-04-06）
**Flow A 自动模式收紧 + 本地回归补齐 + sandbox-exec 显式确认**

**Flow A 执行链修复（4 项）**
- 更新：`sandbox-skill-invoke` 在 `auto --strict-real` 且存在独立 verifier 时优先选择 `shim-live`，避免旧版 OpenClaw CLI 因缺少 live telemetry 协议把本可严格验证的用例误判为 blocker。
- 修复：`live` 模式不再用原始 stdout 覆盖 `NEXUS_OUTPUT_FILE`；现在会优先保留 `assistantMessage` 或 CLI 已写入的真实回复内容。
- 更新：`scripts/test_flow_a_strict.py` 新增 `auto --strict-real` 选择 `shim-live` 的 smoke case，`scripts/test_flow_a_live_telemetry.py` 新增真实输出文件断言。
- 更新：`scripts/validate-framework.py` 本地校验新增 Flow A runtime smoke tests，消除“本地只 py_compile、CI 才跑行为测试”的假绿灯。

**Flow A 文档对齐（3 项）**
- 更新：`roles/test-designer.md`、`roles/test-case-evaluator.md` 去掉把 Skill/Agent 测试写成 `Dry Run` 的旧口径，统一为 `live` / `shim-live` 真实执行要求。
- 更新：`flows/skill-testing.md`、`roles/skill-tester.md`、`DEFINITIONS.md`、`reference-sandbox-spec.md` 补充 `auto --strict-real` 的模式选择规则。
- 更新：`README.md` 当前版本同步到 `v0.9.23`。

**sandbox-exec 防误用（2 项）**
- 更新：`sandbox-exec.sh` 执行真实命令时新增强制参数 `--ack-unsafe-exec`，明确它只是带日志命令执行器，不是安全沙箱。
- 更新：`reference-sandbox-spec.md`、`reference-output-verification-examples.md`、`flows/skill-testing.md`、`roles/skill-tester.md`、`DEFINITIONS.md` 同步显式确认要求。

---

### v0.9.22（2026-04-06）
**减少 prompt 级自循环暗示 + 测试设计去硬编码轮数**：

**流程措辞收敛（3 项）**：
- 更新：`reference-approval-mechanism.md` 将“打回路径”统一改为“阶段回退入口”，明确含义是终止当前阶段并由主 agent 重新进入前置阶段生成新的交付物，而不是要求同一次输出里自我返工
- 更新：`SKILL.md`、`roles/quality-assessor.md`、`roles/test-case-evaluator.md` 同步改为“重新进入前一阶段/阶段三”的表述，避免把阶段回退误读成模型内部循环
- 更新：阶段评审不通过时的文案统一强调“当前评审不通过”，而不是笼统写“打回重做”

**测试设计去硬编码（2 项）**：
- 更新：`roles/test-designer.md` 把多轮脚本要求从固定 `3/5/10 轮` 改成短/中/长三类覆盖，不再要求 LLM 为了满足模板机械跑固定轮数
- 更新：同文件把“打回重做”改成“由主 agent 重新进入测试设计阶段并生成新的交付物”，避免把流程回退写成同一执行链内的自循环

---

### v0.9.21（2026-04-06）
**Flow A live telemetry protocol 硬门禁 + OpenClaw 原生回传协议**：

**live 模式收紧（3 项）**：
- 新增：`sandbox-skill-invoke` 为 `live` 模式定义 OpenClaw 原生 runtime telemetry protocol，当前版本为 `nexus-live-telemetry/v1`
- 修复：`live --strict-real` 现在无条件要求 OpenClaw CLI 回传结构化 telemetry；缺少协议时返回 `blocked-live-telemetry-missing`，协议字段不完整或错误时返回 `blocked-live-telemetry-invalid`
- 新增：`TELEMETRY_PROTOCOL_STATUS`、`TELEMETRY_PROTOCOL_VERSION`、`TELEMETRY_SOURCE` 输出字段，并通过环境变量把协议要求传给 OpenClaw CLI

**回归测试补齐（3 项）**：
- 新增：`scripts/test_flow_a_live_telemetry.py`，用 mock OpenClaw CLI 覆盖 `no-protocol -> blocker`、`protocol-pass -> success`、`bad-evidence -> assertion-failed`
- 更新：GitHub Actions 新增 Flow A live telemetry smoke test，避免 `live` 模式退回“只看退出码和 stdout”
- 更新：`validate-framework.py` 将 `scripts/test_flow_a_live_telemetry.py` 纳入必检与 `py_compile` 范围

**规范同步（3 项）**：
- 更新：`DEFINITIONS.md`、`flows/skill-testing.md`、`roles/skill-tester.md`、`reference-flow-skill.md` 明确 `live --strict-real` 没有 runtime telemetry protocol 就不得返回成功
- 更新：`reference-sandbox-spec.md` 新增 OpenClaw runtime telemetry protocol 章节、环境变量、载荷示例和 blocker 规则
- 更新：`README.md` 明确 `live` 严格模式依赖 OpenClaw CLI 原生回传 `nexus-live-telemetry/v1`

---

### v0.9.20（2026-04-06）
**Flow A 严格 verifier 硬门禁 + CI 行为级回归**：

**严格门禁收紧（3 项）**：
- 修复：`sandbox-skill-invoke` 在 `shim-live --strict-real` 下改为无条件要求独立 `--verification-manifest`；即使没有传 `--expect-*` / `--require-*` 断言参数，也不能再绕过 verifier 门禁返回成功
- 修复：`shim-live --strict-real` 缺少独立 verifier 时统一返回 `assertion-failed`，并明确标记 `TELEMETRY_TRUST=self-reported`
- 修复：当可识别 Skill 仓库根时，位于同仓库的 verifier manifest 不再被视为“独立 verifier”

**回归测试补齐（3 项）**：
- 新增：`scripts/test_flow_a_strict.py`，覆盖 `no-verifier -> fail`、`with-verifier -> pass`、`bad-evidence -> fail`、`multi-turn -> pass`、`same-repo-verifier -> fail` 五个行为级 smoke 场景
- 更新：GitHub Actions 新增 Flow A strict smoke test，CI 不再只看语法和结构
- 更新：`validate-framework.py` 将 `scripts/test_flow_a_strict.py` 纳入必检与 `py_compile` 范围

**规范同步（2 项）**：
- 更新：`DEFINITIONS.md`、`flows/skill-testing.md`、`roles/skill-tester.md`、`reference-flow-skill.md`、`reference-sandbox-spec.md` 统一为“`shim-live --strict-real` 必须带独立 verifier，否则不得返回成功”
- 更新：示例命令与 verifier 说明同步到最新严格口径，减少测试 agent 误用或偷懒空间

---

### v0.9.19（2026-04-06）
**Flow A shim-live 独立 verifier 门禁 + 多轮入口同步**：

**严格门禁增强（3 项）**：
- 新增：`sandbox-skill-invoke` 支持 `--verification-manifest`，用于在 `shim-live --strict-real` 场景下接入 Skill 目录外的独立 verifier
- 修复：`shim-live` 在严格断言场景下不再接受 Skill 自带 adapter 的自报遥测；缺少独立 verifier 时直接返回 `assertion-failed`
- 新增：`TELEMETRY_TRUST`、`VERIFICATION_STATUS`、`VERIFIER_SOURCE`、`VERIFIER_RESULT_FILE` 等输出字段，用于明确证据可信度与 verifier 产物

**执行链路补强（2 项）**：
- 修复：`sandbox_multi_turn.py` 透传 `--verification-manifest`，使多轮严格验证与单轮规则一致
- 修复：多轮摘要改用 ASCII `PASS` / `FAIL`，并记录无效送达证据字段，避免日志摘要出现乱码或遗漏关键失败原因

**规范同步（3 项）**：
- 更新：`DEFINITIONS.md`、`flows/skill-testing.md`、`roles/skill-tester.md` 写明 `shim-live --strict-real` 的独立 verifier 要求
- 更新：`reference-sandbox-spec.md` 补齐 verifier manifest、环境变量、输出字段与严格门禁说明
- 更新：`reference-flow-skill.md` 把 verifier 要求纳入 Flow A 用例与适配器约定

---

### v0.9.18（2026-04-06）
**Flow A 证据可信度继续收紧 + 审计并发安全补强**：

**执行可信度增强（3 项）**：
- 修复：`sandbox-skill-invoke` 的 `shim-live` 路径与 `live` 路径统一为同一套交付断言，补齐 `deliveryReceipts`、`invalidDeliveryEvidence` 和结构化结果回传
- 增强：`live` 模式现在可通过 `NEXUS_RESULT_JSON_FILE` 或结构化 stdout/stderr 回传 `triggerMatched`、`toolsCalled`、`contextReferences`、`deliveryStatus`
- 增强：送达证据必须落在当前 session 内且真实存在；无效路径会显式记入 `INVALID_DELIVERY_EVIDENCE` 并触发断言失败

**稳定性与并发安全（2 项）**：
- 修复：Skill 安装副本的源指纹从路径/mtime 规则升级为内容哈希，降低同一 session 内复用旧副本的风险
- 修复：`sandbox-exec.sh` 与 `sandbox-skill-invoke` 的审计写入都受锁保护，避免并发执行时写坏 `logs/exit-codes.json` / `META.json`
- 修复：Windows 下 `shim-live` 会优先选择可运行的 Git Bash，而不是误用 `system32\\bash.exe` 的 WSL 包装器

**文档同步（2 项）**：
- 更新：`reference-sandbox-spec.md` 补齐 `DELIVERY_RECEIPTS`、`INVALID_DELIVERY_EVIDENCE` 输出字段以及审计锁/内容哈希说明
- 更新：`roles/skill-tester.md` 明确重测时必须使用最新内容哈希副本

---

### v0.9.17（2026-04-06）

**Flow A 反偷懒断言 + 审计链补齐**：

**执行严格性增强（4 项）**：
- 新增：`sandbox-skill-invoke` 支持 `--expect-trigger`、`--require-tools`、`--expect-context-ref`、`--require-delivery-status`、`--require-delivery-evidence`
- 修复：负向触发不再接受 `unknown`，必须拿到显式 `triggerMatched=false`
- 修复：多轮上下文验证不再依赖关键词猜测，改为要求显式 `contextReferences`
- 修复：渠道验证不再接受本地渲染替代送达证明，改为要求显式 `deliveryStatus` 与送达证据

**执行可靠性增强（2 项）**：
- 修复：Skill 安装目录改为基于源文件指纹，避免同一 session 内复用旧副本
- 修复：`sandbox-skill-invoke` 现已写入 `logs/exit-codes.json` 并更新 `META.json`，纳入标准审计账本

**文档与模板同步（3 项）**：
- 更新：`reference-sandbox-spec.md` 补充断言参数、适配器返回字段、送达证据和审计要求
- 更新：`reference-flow-skill.md`、`flows/skill-testing.md`、`roles/skill-tester.md` 强制负向触发 / 上下文 / 渠道验证使用显式证据
- 更新：`DEFINITIONS.md` 明确 `triggerMatched=false`、`contextReferences`、`deliveryStatus` 是 Flow A 真实通过的必要条件

---

### v0.9.16（2026-04-06）

**Flow A 严格真实执行收口 + shim 适配器补全**：

**执行能力升级（4 项）**：
- 新增：`sandbox-skill-invoke` Python 核心实现，支持 `auto` / `live` / `shim-live` / `trace` / `dry-run`
- 新增：`--strict-real` 门禁；真实执行不可用时不再静默退回 `trace`
- 新增：`testing.json` / `scripts/test-entry.*` 适配器约定，用于在无 OpenClaw CLI 时完成本地真实执行
- 新增：`sandbox-multi-turn` Python 核心实现，支持真实执行模式透传与历史文件管理

**规范收口（4 项）**：
- 修复：`reference-sandbox-spec.md` 重写为现行沙箱规格，明确 `live` / `shim-live` / `trace` 的能力边界
- 修复：`DEFINITIONS.md` 降级阶梯新增 `shim-live`，并明确 `trace` 不能计入真实执行率
- 修复：`flows/skill-testing.md` 与 `roles/skill-tester.md` 强制 P0/P1 功能用例使用 `--strict-real`
- 修复：`reference-flow-skill.md` 补充最低执行级别和适配器结果回传格式

**基础设施补充（1 项）**：
- 更新：`sandbox-create.sh` 新增 `workspace/state/` 与 `workspace/artifacts/` 目录，承载多轮历史和适配器产物

---

### v0.9.15（2026-04-06）

**Flow/Role 继续瘦身 + Skill 结构校验器拆分**：

**流程与角色文档优化（3 项）**：
- 重写：`flows/web-api-testing.md`，改为只保留模式选择、阶段合同、并行角色和门禁规则，删除大量重复的步骤模板与工具细节
- 精简：`roles/quality-assessor.md`，收敛为规格质量、风险、可测试性与 Flow B 模式选择职责
- 精简：`roles/skill-tester.md`，收敛为隔离安装、安全门禁、能力/边界/输出验证和稳定性检查

**参考文档整合（2 项）**：
- 整合：`reference-skill-review-framework.md` 进入主入口参考索引，并在 `quality-assessor` 中作为 Skill 规格审查补充框架使用
- 补充：`README.md` 新增「当前限制」说明，更明确区分 Flow A 的已实现能力与 Flow B/C/D 对外部环境的依赖

**工程化增强（3 项）**：
- 重构：`scripts/skill-structure-validator.py` 拆分为 CLI 外壳 + `scripts/skill_structure_validator_core.py` 核心逻辑，降低入口脚本复杂度
- 增强：`scripts/validate-framework.py` 开始编译 `scripts/*.py` 下的全部 Python 脚本，并将 `reference-skill-review-framework.md` 纳入必检清单
- 修复：`skill_structure_validator_core` 将同目录 Python 模块识别为本地依赖，不再误报为外部 import

---

### v0.9.14（2026-04-06）

**规范收敛 + 文档瘦身 + 校验器增强**：

**现行规范收敛（4 项）**：
- 修复：移除当前规范链路中的 HMAC / `.nexus-hmac-salt` / `signature` 要求，批准机制改为仅依赖 `approval-records.json`、`rejection-count.json` 和阶段审计日志
- 修复：`reference-approval-mechanism.md` 重写为现行批准/拒绝/无响应/No-Go 规则，不再与 `DEFINITIONS.md` 冲突
- 修复：`reference-production-readiness.md` 删除对不存在脚本和矩阵文件的引用，改为只引用仓库中真实存在的脚本与交付物
- 修复：废弃角色 `compatibility-tester-skill.md` 从活跃 `roles/` 目录移至 `archive/roles/`

**入口与角色文档瘦身（3 项）**：
- 重写：`SKILL.md`，移除与 `DEFINITIONS.md` 的大段重复定义，只保留路由、阶段合同、门禁和引用索引
- 精简：`roles/functional-tester.md`、`roles/requirement-analyst.md`、`roles/experience-tester-a.md`、`roles/experience-tester-b.md`、`roles/report-integrator.md`，删除大块模板和重复规范，改为职责/输入输出/最低交付格式
- 更新：`README.md` 活跃角色统计与运行期产物说明，区分活跃角色与归档模板

**工程化增强（3 项）**：
- 增强：`scripts/validate-framework.py` 新增对 HMAC 残留、废弃角色回流、额外 reference 文件缺失的校验
- 增强：`scripts/validate-framework.py` 新增标准 CLI 参数、`--json` 机读输出和 Windows 控制台编码容错
- 兼容：`SKILL.md` 补充 `Description`、`Usage`、`Examples`，使 `skill-structure-validator.py` 对本仓库的结构评分提升到 `EXCELLENT`

---

### v0.9.13（2026-04-04）

**深度一致性修复 + 验证体系增强**：

**P0 框架断裂修复（2 项）**：
- 修复：flows/web-api-testing.md A 模式缺失阶段零（环境就绪检查），直接跳到阶段一，违反标准 8 阶段定义
- 修复：DEFINITIONS.md 和 README.md B 模式阶段数错误（「总计 10 个阶段」→「总计 11 个阶段 B-阶段零~十」），表中列出 11 行但描述写 10

**P1 信息不一致修复（2 项）**：
- 修复：flows/web-api-testing.md playwright 工具表中 Step 7.4/7.5 引用过时（上轮重编号后遗留），改为明确标注 A/B 模式对应 Step
- 修复：roles/skill-tester.md 和 roles/test-designer.md 缺失 DEFINITIONS.md 统一引用声明（20 个角色中仅此 2 个未引用）

**工程化增强（2 项）**：
- 增强：scripts/validate-framework.py 新增 `role definitions ref` 校验，确保所有活跃角色文件都引用 DEFINITIONS.md
- 当前验证项从 9 项增至 10 项

---

### v0.9.12（2026-04-04）

**跨文档一致性修复 + 验证增强**：

**P0 框架断裂修复（3 项）**：
- 修复：flows/web-api-testing.md A 模式阶段编号错误（「阶段五后：缺陷分析」→「阶段六：缺陷分析」，「阶段六：报告整合」→「阶段七：报告整合」），v0.9.10 CHANGELOG 标注已修复但未实际应用
- 修复：flows/web-api-testing.md A 模式缺失证据收集步骤（阶段五后 evidence-collector），补齐完整并行角色清单
- 修复：flows/web-api-testing.md B 模式缺失 B-阶段零（环境就绪检查）和 B-阶段七（用例评估，需批准），直接跳过用例评审进入并行测试

**P1 信息不一致修复（3 项）**：
- 修复：flows/web-api-testing.md B 模式未使用 B-阶段 前缀（「阶段三」→「B-阶段三」等），与 DEFINITIONS.md 第四节约定不一致
- 修复：DEFINITIONS.md 目录树中 `android-results.md` 为幽灵条目（无角色产出），已移除
- 修复：DEFINITIONS.md 目录树 `compatibility-results.md` 标注「Flow B/C/D 必出」但 Flow D 无 compatibility-tester，改为「Flow B/C 必出」

**P2 补充修复（2 项）**：
- 修复：SKILL.md subagent I/O 表 compatibility-tester 标注「Flow B/C/D 专用」→「Flow B/C 专用，Flow A/D 不使用」
- 修复：flows/web-api-testing.md 流程对比表过时，重写为与 DEFINITIONS.md 第四节对齐的 11 阶段对比

**工程化增强（2 项）**：
- 增强：scripts/validate-framework.py 新增 7 个缺失的 reference 文件到必检清单
- 增强：scripts/validate-framework.py 新增 role reference 校验（检查 flow 文件引用的角色是否存在）
- 增强：.gitignore 补充 node_modules、.env、IDE 配置等常见忽略模式

---

### v0.9.11（2026-04-04）

**工程化与可维护性优化**：

- 新增：`.gitignore`，忽略 `memory/nexus-reports/`、`.nexus-sandbox/`、`.nexus-hmac-salt` 等运行期产物
- 新增：`.gitattributes` 和 `.editorconfig`，统一 Markdown / Shell / Python / JSON 的编码与换行约定
- 新增：`scripts/validate-framework.py`，自动校验核心文件、Markdown 链接、frontmatter、README 版本同步、Flow 单一事实源声明和角色版本漂移
- 新增：`.github/workflows/validate-framework.yml`，在 CI 中执行仓库校验和 `bash -n` 语法检查
- 修复：`README.md` 当前状态、仓库结构说明、自检说明和版本号落后于实际项目状态
- 修复：`roles/defect-analyst.md` 与 `roles/report-integrator.md` 的内联版本号漂移问题，避免后续继续失真

---

### v0.9.10（2026-04-04）

**全项目审计修复（30 个问题）**：

**P0 框架断裂修复（4 项）**：
- 修复：SKILL.md 多选提示「六阶段」→「八阶段（阶段零~七）」（过时文案）
- 修复：flows/android-testing.md 缺失阶段零（环境就绪检查），已补充
- 修复：flows/mcp-testing.md 缺失阶段零（环境就绪检查），已补充
- 修复：DEFINITIONS.md 目录树 `evidence-collection.md` 从 `TEST-EXECUTION/` 移至 `DEFECTS/`

**P1 信息不一致修复（6 项）**：
- 修复：flows/web-api-testing.md A 模式阶段编号偏移（「阶段五后」→「阶段六」，「阶段六」→「阶段七」）
- 修复：DEFINITIONS.md Section 6 五个角色输入定义与实际角色文件不一致（performance-tester / reality-checker / security-tester / compatibility-tester / accessibility-auditor）
- 修复：SKILL.md 自动推进阶段列表缺失阶段零
- 修复：DEFINITIONS.md Section 3 缺失 `functional-results.md`、`accessibility-results.md`、`reality-results.md` 三个输出文件
- 修复：DEFINITIONS.md Section 6 security-tester Flow 列不完整（`A/D` → `A/B/C/D`）
- 修复：DEFINITIONS.md `performance-results.md` 注释只标 `Flow D` → `Flow B/C/D`

**P2 功能缺口修复（5 项）**：
- 新增：flows/android-testing.md 阶段五添加沙箱执行引用
- 新增：flows/mcp-testing.md 阶段五添加沙箱执行引用
- 新增：roles/test-designer.md 引用 `reference-agent-evaluation-methodology.md` 和 `reference-test-case-templates.md`
- 修复：flows/mcp-testing.md 阶段七输出错误包含 `DEFECT-REPORT.md`（属于阶段六）
- 修复：roles/defect-analyst.md 硬编码「3 次」拒绝上限，补充引用 `DEFINITIONS.md` 第九节

**P3 孤立/低优修复（6 项）**：
- 修复：roles/tool-evaluator.md 标记为辅助角色并补充 DEFINITIONS.md 引用
- 修复：roles/workflow-optimizer.md 标记为辅助角色并补充 DEFINITIONS.md 引用
- 修复：DEFINITIONS.md 「Flow B B 模式」双 B 连写歧义 → 「Flow B（B 模式）」
- 修复：roles/requirement-analyst.md 补充 DEFINITIONS.md 引用
- 修复：roles/report-integrator.md 补充 DEFINITIONS.md 和 reference-report-format.md 引用
- 保留：roles/compatibility-tester-skill.md 保留但标注废弃（格式参考模板）

---

### v0.9.9（2026-04-03）

**沙箱执行环境 + 外部 Case 获取**：

**新增能力**：
- 新增：`reference-sandbox-spec.md`（沙箱执行环境规格参考）— 目录结构/5 阶段生命周期/安全边界/命令参考/集成点
- 新增：`scripts/sandbox-create.sh`（沙箱创建脚本）— 自动创建隔离 session、探测运行时、生成 META.json
- 新增：`scripts/sandbox-exec.sh`（沙箱执行脚本）— 命令安全校验/超时执行/日志捕获/exit code 记录
- 新增：`scripts/sandbox-cleanup.sh`（沙箱清理脚本）— 路径遍历防护/安全删除/清理验证
- 新增：`reference-external-case-sourcing.md`（外部测试用例获取规范）— 搜索策略/评估评分卡/集成流程/来源追溯

**框架集成**：
- 新增：DEFINITIONS.md 第十四节「沙箱执行环境」— 沙箱根路径/Session ID 格式/能力级别/超时配置
- 新增：DEFINITIONS.md 第十五节「外部测试用例获取」— EXT-TC-NN 编号/来源追溯/评估最低分
- 新增：SKILL.md 参考文档索引 — 引用 `reference-sandbox-spec.md` 和 `reference-external-case-sourcing.md`
- 新增：SKILL.md 阶段零「Flow A 沙箱能力检测」— 4 项沙箱能力检测表
- 新增：flows/skill-testing.md 阶段零沙箱能力检测 + Step 5.0 沙箱准备步骤
- 新增：roles/test-designer.md 方法 4「沙箱执行」+ 外部 Case 集成子节
- 新增：roles/skill-tester.md 第 11 节「沙箱执行模式」— 6 步执行流程 + 执行证明合规说明
- 新增：roles/evidence-collector.md 审计检查项「沙箱日志证据」

**修复**：
- 修复：降级阶梯第 2 级「沙箱执行」从空口号变为可操作（有实际脚本支撑）
- 修复：skill-tester 降级路径中「尝试 2」细化为沙箱脚本可用/不可用两条分支
- 修复：test-designer 环境模拟方法库新增方法 4（沙箱执行），补充方法 1-3 的能力上限

**新增能力（AI 测试资料包整合）**：
- 新增：`reference-agent-evaluation-methodology.md`（Agent 智能体评测方法论）— 整合华为五维评测模型、支付宝行业智能体评测维度、字节 Agent 单元测试评分体系，提炼分层评测架构、种子集+扰动生成、Judge 辅助判定、鲁棒性测试等模式
- 新增：`reference-test-case-templates.md`（测试用例模板与反模式参考）— 整合 qa-test-planner 8 种用例模板（标准/功能/UI/集成/安全/性能/回归/元测试）+ 5 类测试反模式清单（测试 Mock 行为/生产代码测试污染/不理解就 Mock/不完整 Mock/事后补充）+ 回归套件三层架构（Smoke/定向/全量）
- 新增：Flow B 推荐测试工具 — playwright-cli（首选，多浏览器自动化/网络 Mock/截图/视频/无障碍树）+ chrome-cdp（辅助，SPA 动态扫描/真实浏览器连接），含工具选择决策树

---

### v0.9.8（2026-04-03）

**Flow A 阶段零依赖环境检测**：
- 新增：SKILL.md 阶段零增加「Flow A 依赖环境检测」— 扫描被测 Skill 的源码和 SKILL.md，自动识别并验证 npm/Python/其他 OpenClaw 插件/系统命令等运行时依赖
- 新增：6 项依赖检测维度（Node.js/npm 环境、Python 环境、Python 依赖包、npm 依赖包、引用的 OpenClaw 插件、系统命令依赖），每项含明确检测方法和三态状态标记（✅/❌/⏭️）
- 新增：依赖检测逻辑流程 — 未检测到依赖则跳过，必要依赖缺失则阶段零不通过，仅警告时用户确认后可继续
- 新增：环境就绪报告格式增加「依赖环境检测」区块
- 新增：flows/skill-testing.md 补充阶段零定义（此前 Flow A 流程文件缺少阶段零）
- 约束：OpenClaw 环境本身假定已就绪，不作为检测项

---

### v0.9.7（2026-04-03）

**测试严谨性全面强化**：

**反偷懒审计闭环（Critical Fix）**：
- 新增：evidence-collector 增加「执行证明审计」职能 — 对阶段五所有测试结果（含通过用例）逐条审计执行证明合规性
- 新增：执行率计算规则明确定义 — 有完整执行证明或标注降级的用例计入已执行，静态分析和证明缺失不计入
- 新增：审计结果直接影响后续阶段 — 执行率 < 50% 直接 No-Go，50%~69% 强制打回阶段五

**Flow B 双模式阶段映射标准化（Critical Fix）**：
- 新增：DEFINITIONS.md 第四节「Flow B 双模式阶段定义」— 明确 B 模式 10 个阶段的编号（B-阶段零~B-阶段十）、执行者、批准要求
- 修复：Flow B B-模式阶段编号与主框架混淆 — 改用「B-阶段X」前缀，消除歧义
- 修复：B 模式门禁规则缺失 — 明确 B-阶段二和 B-阶段七适用标准批准/拒绝规则
- 修复：flows/web-api-testing.md A 模式缺少阶段零 — 补齐标准 8 阶段映射

**安全测试覆盖对称化（Critical Fix）**：
- 新增：security-tester.md Web/API 扩展安全测试（8 维度：供应链/第三方脚本/HTTP 安全头/Cookie/CORS/文件上传/速率限制/信息泄露）
- 新增：security-tester.md MCP 安全测试（7 维度：权限/注入/隔离/协议 DoS/参数越界/连接劫持/错误泄露）
- 新增：security-tester.md APK 安全测试（9 维度：反编译/权限/存储/通信/Intent IPC/ContentProvider/WebView/日志/剪贴板）
- 修复：flows/android-testing.md 安全测试内容补充 Intent/IPC/WebView/日志泄露等维度
- 修复：flows/mcp-testing.md 安全测试补充协议层 DoS/连接认证/错误信息泄露

**Evidence Collector 时序矛盾修复（Important Fix）**：
- 新增：evidence-collector 增加「证据补充时序约束」— 明确 subagent 终止后的 3 级分级处理方案
- 修复：subagent 已终止后无法补充证据的死循环 — 改为 evidence-collector 自行复现或交由缺陷分析师降级处理

**Flow A 性能测试补充（Important Fix）**：
- 新增：skill-tester.md 第 8 节「运行时性能测试」— Token 消耗/响应延迟/Token 爆炸/多轮累积/并发稳定性
- 修复：DEFINITIONS.md Flow A 标注 skill-tester 含运行时性能测试
- 修复：flows/skill-testing.md 标注性能测试已集成在 skill-tester 中

**阶段门禁执行者与审计日志（Important Fix）**：
- 新增：DEFINITIONS.md 第九节明确门禁执行者为主 agent 自身
- 新增：`stage-transition-log.json` 阶段转换审计日志格式 — 记录每次转换的交付物/批准/门禁检查状态
- 新增：主 agent 阶段转换前 5 步自检清单
- 新增：报告目录结构补充 `stage-transition-log.json`

**降级验证机制（Important Fix）**：
- 新增：DEFINITIONS.md 第十节「降级合规性验证」— 由 evidence-collector 审计降级标注/理由/尝试记录
- 修复：不合规的降级用例不计入执行率

**Token 预算监控职责明确（Important Fix）**：
- 新增：DEFINITIONS.md 第七节明确 Token 监控职责分工（主 agent 监控 + subagent 自报 + 用户授权无限模式）

**HMAC 盐值安全修复（Minor Fix）**：
- 修复：HMAC 盐值从硬编码改为环境变量 `NEXUS_HMAC_SALT` + 运行时自动生成 `.nexus-hmac-salt` 文件
- 修复：reference-approval-mechanism.md 同步更新盐值来源

**其他改进**：
- 新增：reference-report-format.md 第三节「测试执行结果报告统一格式」— 含执行证明、降级标注、Token 消耗模板
- 新增：experience-tester-b.md 增加「B 独有视角」差异化要求 — 入口路径/设备视角/用户角色/异常场景 6 维度差异化
- 新增：mcp-tester.md 错误码合规性基于 JSON-RPC 2.0 规范 — 5 个标准错误码 + MCP 扩展错误码测试方法
- 新增：DEFINITIONS.md 第十二节「回归套件维护职责」— 报告整合师/测试设计师/主 agent 分工
- 优化：compatibility-tester-skill.md 强化废弃标记 — 明确禁止引用

**废弃命名更新**：
| 废弃名称 | 正确名称 | 说明 |
|---------|---------|------|
| HMAC 盐值 `nexus-testing-v0.9.5-hmac-salt` | 环境变量 `NEXUS_HMAC_SALT` | 禁止硬编码 |

---

### v0.9.6（2026-04-03）

**阶段门禁强制约束（防止跳阶段）**：
- 新增：DEFINITIONS.md 第九节「阶段门禁强制规则」— 明确禁止提前执行、禁止合并输出、禁止重复审批、违反须回退
- 新增：DEFINITIONS.md 第九节「安全防护配置」— HMAC 盐值 `nexus-testing-v0.9.5-hmac-salt` 补充定义（修复 DEF-P1-001）
- 新增：SKILL.md 批准环节「阶段门禁执行顺序」— 5 条硬性约束 + 执行流程图，违反视为严重流程错误
- 修复：Agent 在阶段三完成后、阶段四批准前就执行了阶段四（测试用例评估），违反阶段门禁
- 修复：阶段四批准请求重复发送两次，违反禁止重复审批规则
- 修复：批准后跳过阶段四直接进入阶段五，违反禁止提前执行规则

**HMAC 盐值一致性修复（DEF-P1-001）**：
- 修复：CHANGELOG.md 记录「HMAC 盐值更新为 v0.9.5」，但 DEFINITIONS.md 未定义该盐值 — 现已在 DEFINITIONS.md 第九节补充定义，与 `reference-approval-mechanism.md` 保持一致

### v0.9.5（2026-04-03）

**安全扫描增强（吸收 skill-vetter + OpenClaw 安全审计）**：
- 新增：`reference-security-scan.md`（六阶段安全扫描参考规范：提示词注入/恶意代码/凭证泄露/结构命令/供应链/权限审计）
- 新增：skill-tester 安装前安全门禁增加提示词注入预扫描（系统提示提取/越狱/编码混淆/上下文污染/分段注入）
- 新增：skill-tester 安装前安全门禁增加凭证泄露预扫描（API Key/Token/Base64 隐写/OAuth 凭证）
- 新增：skill-tester 安装前安全门禁增加危险 Shell 命令预扫描（rm -rf/curl|bash/eval+动态输入）
- 新增：skill-tester 安装前安全门禁增加供应链预扫描（install.sh 审计/依赖来源/postinstall 钩子）
- 新增：skill-tester 安装前安全判定门禁（BLOCKED/REVIEW/SAFE 三级判定 + 标准化输出格式）
- 新增：security-tester Skill 安全测试增加六阶段扫描架构和预扫描判定
- 新增：安全扫描外部工具集成支持（aguara 提示词注入扫描 + skill-scanner Cisco AI 漏洞扫描），可选安装、降级兼容
- 新增：SKILL.md 参考文档索引添加 `reference-security-scan.md`

**一致性与可执行性优化**：
- 修复：全仓报告路径模板统一为 `memory/nexus-reports/{date}-{test-type}-{flow}/`，消除 `{flow}` 缺失导致的路径漂移
- 修复：主入口”混合执行模型”中的阶段定义，阶段六恢复为缺陷分析，阶段七为报告整合
- 修复：执行率阈值与 `DEFINITIONS.md` 对齐，统一为 70%~89% 覆盖不足、50%~69% 强制打回、<50% No-Go
- 修复：阶段推进语义收口，阶段零确认、阶段二/四批准，其余阶段按前置产物自动推进
- 修复：SKILL.md 执行原则编号冲突（8/9/10 → 9/10/11）
- 修复：Flow B 交叉核对文件名与 DEFINITIONS.md 命名不一致（a-by-b ↔ b-by-a 互换）
- 修复：SKILL.md 执行率阈值补齐 ≥90% 档，与 DEFINITIONS.md SSOT 对齐

**测试流程增强（吸收 Anthropic webapp-testing / Playwright Skill / Testing Automation Expert / QA Test Planner）**：
- 新增：functional-tester 添加「侦察-后-行动模式」（Reconnaissance-then-Action）+ networkidle 等待策略 + 服务器生命周期管理 + 断链检测矩阵
- 新增：compatibility-tester 添加多视口测试矩阵（7 种设备/分辨率 × 4 浏览器）+ 移动端触控目标间距规则
- 新增：test-case-evaluator 添加测试反模式检查表（9 种反模式）+ 分层质量检查清单（Unit/Integration/E2E）+ 覆盖率矩阵模板
- 新增：report-integrator 添加结构化发布通过/失败标准（6 维度判定表 + 判定逻辑决策树）
- 新增：test-designer 添加测试金字塔参考比例（4 层：单元 50-60% / 集成 20-25% / E2E 10-15% / 契约 5-10%）
- 新增：DEFINITIONS.md 添加回归套件分层定义（Smoke/Sanity/Targeted/Full 四级）+ 复测策略关联

**结构优化**：
- 优化：主入口移除 `sessions_spawn`、`runTimeoutSeconds`、`Promise.allSettled` 等实现细节，改为平台能力描述
- 优化：`skill-tester` 从“直接与用户交互”改为“只产出结果和 blocker，由主 agent 统一升级处理”
- 优化：`skill-tester` 安全扫描改为阻断项 / 警告项 / 观察项三级处理，避免对高权限 Skill 一刀切误杀
- 优化：当前会话信息不再写死本地绝对工作目录，改为运行时注入

### v0.9.5（2026-04-02）

**执行验证强化（反偷懒机制）**：
- 新增：SKILL.md 执行原则第 8 条「真实执行原则」+ 执行降级阶梯 + 执行率硬性要求
- 新增：skill-tester.md 第 0 节「反偷懒执行规则」+ 强制执行证明格式 + 环境降级路径
- 新增：skill-tester.md 第 7 节「逻辑分支覆盖」— 每个决策分支必须有独立测试
- 新增：skill-tester.md 渠道测试执行要求 — 禁止仅检查配置就写通过，必须真实发送
- 新增：test-designer.md 逻辑分支覆盖矩阵 + 强制逆向思维清单
- 新增：DEFINITIONS.md 第十节「执行验证标准」— 执行证明格式 + 执行率要求 + 降级阶梯
- 新增：所有 executor 角色（security/functional/compatibility/performance/mcp/reality/accessibility/experience-a/b）添加执行证明引用
- 新增：所有 flow 文件添加 DEFINITIONS.md 第十节引用

**引用一致性**：
- 修复：reference-flow-skill.md "34 项检测结果"无来源 → 改为动态描述
- 修复：compatibility-tester-skill.md 标记为已合并（功能已集成到 skill-tester）
- 修复：Flow B 阶段映射表重写（区分 A/B 模式，与实际内容同步）

**一致性修复**：
- 修复：evidence-collector 时机矛盾（三处描述统一为"阶段五所有 subagent 完成后执行一次性验证"）
- 修复：defect-analyst 打回次数（2→3，与 DEFINITIONS.md 统一）
- 修复：Flow A 缺少阶段六（补充缺陷分析阶段）
- 修复：Flow C/D 阶段六与阶段七合并（拆分为独立的缺陷分析+报告整合）
- 修复：Flow B/C/D 输出路径缺少 `TEST-EXECUTION/` 前缀
- 修复：Flow B evidence-collector 描述（"贯穿全程"→"完成后一次性验证"）
- 修复：HMAC 盐值版本号（v0.8→v0.9.5）
- 修复：report-integrator 版本号（v1.0→v0.9.5）
- 修复：defect-analyst 版本号（v0.6→v0.9.5）

**结构优化**：
- 新增：`reference-security-blacklist.md`（XSS 注入字符黑名单独立参考文件）
- 新增：`reference-approval-mechanism.md`（批准机制完整规范独立参考文件）
- 新增：DEFINITIONS.md 第十一节「增量复测流程」（P0 全量复测 / P1 关联复测 / P2-P3 单用例复测）
- 精简：SKILL.md 中的 XSS 黑名单替换为引用（减少约 20 行）
- 精简：SKILL.md 中的批准机制规范提取为引用（减少约 120 行）
- 精简：SKILL.md 中的 JavaScript 代码示例替换为自然语言指令
- 精简：SKILL.md 中的进度监控改为完成时写入（非每分钟轮询）
- 精简：移除 SKILL.md 中的过时版本标签（v0.6.3 更新）
- 精简：defect-analyst 移除过时的新增标记（"新增 v0.6"）

**产品无关化**：
- 修复：defect-analyst Step 3 误杀判定表移除 AgentGuard 特定示例（DEF-P1-001/002/003/006/007、guard-hook.js、patrol setup），替换为通用场景描述
- 修复：defect-analyst Step 4 漏检补充表移除 AgentGuard 特定条目（checkup-report.js、patrol --timeout-seconds、action-policies.md、patrol-checks.md、AgentGuard 自扫），替换为通用检查项（exec/execFile 字符串拼接、SPEC 追踪断链、逆向测试覆盖）
- 修复：DEFINITIONS.md Flow B B 模式目录结构添加 `EXPERIENCE/` 子目录（与 experience-tester-a/b 实际输出路径一致）

**废弃命名更新**：
| 废弃名称 | 正确名称 | 说明 |
|---------|---------|------|
| HMAC 盐值 `nexus-testing-v0.8-hmac-salt` | `nexus-testing-v0.9.5-hmac-salt` | 版本号同步 |

### v0.7（2026-04-02）
- 新增：Dual Mode（生成模式 + 评审模式）
- 新增：DEFINITIONS.md 单一事实源
- 新增：reference-*.md 参考文档（5 个）
- 新增：Token 90% 预警、100% 强制停止
- 新增：rejection-count.json HMAC 签名防护
- 新增：evidence-collector TOCTOU 原子化写入
- 新增：打回理由 10 字符最低长度限制
- 新增：打回循环 3 轮上限
- 修复：Flow A 并行角色数冲突（2 个）
- 修复：experience-tester-b name 错误
- 修复：XSS 黑名单扩充（20+ 向量）
- 修复：阶段编号统一为阶段零~七

### v0.6.3（2026-04-01）
- 首次引入 8 阶段流程（阶段零~七）
- 引入 evidence-collector 独立角色
- 引入打回机制（最多 3 次拒绝）
- 引入 Token 预算规则（50K/角色）

---

## 已知平台限制（无法通过文档修复）

| 问题 | 说明 | 影响 |
|------|------|------|
| subagent 无法自我终止 | Token 100% 时 subagent 无法主动停止，需 Gateway 层实现 | Token 上限无法真正强制 |
| OpenClaw 平台约束 | argument-hint、allowed-tools 等由平台控制，非 Skill 可配置 | 部分安全规则受平台限制 |
