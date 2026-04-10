# Nexus Testing Framework — 单一事实源

> 此文件定义共享阶段、角色、文件、超时和 Flow 基线；Flow/Reference 文件可按第六节-B 的优先级补充更具体的场景规则，主入口和 Role 文件默认引用这里的公共定义。

**目录**：[一 阶段定义](#一阶段定义8-阶段编号零七) | [二 上下文传递](#二阶段间上下文传递唯一路径) | [三 报告目录](#三报告目录结构) | [四 Flow 配置](#四flow-配置并行角色定义) | [五 超时](#五超时配置统一值) | [六 角色分类](#六角色分类体系) | [六-B 文档优先级](#六-b文档优先级规则) | [六-C 轻量模式](#六-c轻量模式) | [六-D 角色输入输出约定](#六-d角色输入输出约定阶段角色-subagent) | [七 Token 预算](#七token-预算规则统一值) | [八 渠道降级](#八渠道降级规则统一描述) | [九 审批打回](#九审批与打回规则统一) | [十 执行验证](#十执行验证标准反偷懒机制) | [十一 增量复测](#十一增量复测流程) | [十二 回归套件](#十二回归套件分层定义) | [十三 动态测试](#十三ai-动态测试增强) | [十四 沙箱环境](#十四沙箱执行环境) | [十五 外部用例](#十五外部测试用例获取) | [十六 Skill 分类](#十六skill-类型分类体系) | [十七 测试维度矩阵](#十七能力驱动测试维度矩阵)

---

## 一、阶段定义（8 阶段，编号零~七）

| 阶段编号 | 阶段名称 | 执行者 | 输出文件 | 需批准 | 可打回 |
|----------|----------|--------|---------|--------|--------|
| 阶段零 | 环境就绪检查 | `environment-checker` subagent（执行检查） + 主 agent（发送确认） | `STAGE-SUBAGENT-PLAN.json` + 环境就绪报告（内存中） | ✅ 需确认 | ❌ |
| 阶段一 | 需求解析 + 规格一致性校验 | `requirement-analyst` subagent + `spec-consistency-validator` subagent | `PRODUCT-FINGERPRINT.json` + `SPEC.md` + `SPEC-CONSISTENCY-REVIEW.md` | ❌ | ❌ |
| 阶段二 | 质量评估 | `quality-assessor` subagent | `PRODUCT-QUALITY-REVIEW.md` | ✅ 需批准 | ✅ 打回阶段一 |
| 阶段三 | 测试设计 | `test-designer` subagent | `TEST-DESIGN.md` + `SURFACE-EXECUTION-PLAN.json` | ❌ | ❌ |
| 阶段四 | 用例评估 | `test-case-evaluator` subagent | `TEST-CASE-REVIEW.md` | ✅ 需批准 | ✅ 打回阶段三 |
| 阶段五 | 并行测试执行 | 各 Flow 并行角色 subagent | `TEST-EXECUTION/*.md` + `TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md` + `TEST-EXECUTION/SURFACE-COVERAGE.json` | ❌ | ✅ 打回阶段三/五 |
| 阶段六 | 缺陷分析 | `defect-analyst` subagent | `DEFECTS/DEFECT-REPORT.md` | ❌ | ✅ 打回阶段三/五 |
| 阶段七 | 报告整合 | `report-integrator` subagent | `FINAL-TEST-REPORT.md` | ❌ | ❌ |

**阶段零~七共 8 个阶段**。沟通时统一使用「阶段零」「阶段一」…「阶段七」。

---

## 二、阶段间上下文传递（唯一路径）

```
阶段零 → STAGE-SUBAGENT-PLAN.json
阶段一 → PRODUCT-FINGERPRINT.json + SPEC.md + SPEC-CONSISTENCY-REVIEW.md
阶段二 → PRODUCT-QUALITY-REVIEW.md
阶段三 → TEST-DESIGN.md + SURFACE-EXECUTION-PLAN.json
阶段四 → TEST-CASE-REVIEW.md
阶段五 → TEST-EXECUTION/*.md + TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md + TEST-EXECUTION/SURFACE-COVERAGE.json
阶段六 → DEFECTS/DEFECT-REPORT.md（汇总所有缺陷）
阶段七 → FINAL-TEST-REPORT.md
```

---

## 三、报告目录结构

所有报告输出到：`memory/nexus-reports/{date}-{test-type}-{flow}/`

发送约束补充：
- `memory/nexus-reports/...` 是归档路径，不直接作为平台发文件路径
- 对用户发送交付物前，先用 `python scripts/prepare_report_delivery.py --report-file <memory-report-file>` 镜像到工作区 `files/nexus-reports/...`
- 平台消息中的 `filePath` 必须使用相对工作区的 `files/...` 路径

```
{date}-{test-type}-{flow}/
├── STAGE-SUBAGENT-PLAN.json         # 阶段零调度计划
├── PRODUCT-FINGERPRINT.json         # 阶段一事实指纹
├── SPEC.md                          # 阶段一规格文档
├── SPEC-CONSISTENCY-REVIEW.md       # 阶段一事实一致性门禁
├── PRODUCT-QUALITY-REVIEW.md        # 阶段二
├── TEST-DESIGN.md                   # 阶段三
├── SURFACE-EXECUTION-PLAN.json      # 阶段三多表面执行计划
├── TEST-CASE-REVIEW.md              # 阶段四
├── approval-records.json            # 阶段二/四批准交互记录（动态生成）
├── rejection-count.json              # 拒绝计数持久化（动态生成）
├── stage-transition-log.json         # 阶段转换审计日志（动态生成）
├── TEST-EXECUTION/
│   ├── SKILL-SURFACE-WORKLIST.md       # Flow A 阶段五 surface 执行工单
│   ├── SURFACE-COVERAGE.json           # Flow A 阶段五 surface 覆盖状态
│   ├── progress-{角色}.txt         # 进度文件（动态生成）
│   ├── skill-results.md             # Flow A 必出
│   ├── security-results.md           # Flow A/D 必出
│   ├── compatibility-results.md      # Flow B/C 必出
│   ├── performance-results.md        # Flow B/C/D 必出
│   ├── mcp-results.md               # Flow D 必出
│   ├── functional-results.md          # Flow B/C 必出
│   ├── accessibility-results.md       # Flow B 必出
│   ├── reality-results.md             # Flow C/D 必出
├── DEFECTS/
│   ├── DEFECT-REPORT.md             # 阶段六
│   ├── evidence-collection.md       # 证据收集（阶段五后执行）
│   ├── evidence/                    # 缺陷证据截图/日志
│   └── rejection-records.md          # 拒绝记录
├── FINAL-TEST-REPORT.md             # 阶段七
└── archive/                         # 复测归档目录（复测时旧报告移入）
    └── {timestamp}/                  # 时间戳子目录，不覆盖已有内容
```

**路径变量约定**：
- `{date}`、`{test-type}`、`{flow}` 三者缺一不可
- Flow/Role 文档引用报告路径时，必须保留完整模板，禁止省略 `{flow}`

**Flow B（B 模式）扩展文件**（双边体验流程特有）：
```
{date}-{test-type}-{flow}/
├── EXPERIENCE/
│   ├── experience-report-a.md          # 体验工程师 A 报告（B 模式阶段三）
│   ├── experience-report-b.md          # 体验工程师 B 报告（B 模式阶段三）
│   ├── cross-check-a-by-b.md           # B 核对 A 的结果（B 模式阶段四）
│   └── cross-check-b-by-a.md           # A 核对 B 的结果（B 模式阶段四）
```

---

## 四、Flow 配置（并行角色定义）

| Flow | 测试类型 | 并行角色（阶段五） | 数量 | evidence-collector |
|------|---------|-------------------|------|-------------------|
| Flow A | Skill 测试 | `skill-tester`（含运行时性能测试） + `security-tester` | 2 | ✅ 阶段五完成后执行 |
| Flow B | 网页+接口测试 | `functional-tester` + `compatibility-tester` + `security-tester` + `performance-tester` + `accessibility-auditor` | 5 | ✅ 阶段五完成后执行 |
| Flow C | 安卓测试 | `functional-tester` + `compatibility-tester` + `security-tester` + `performance-tester` + `reality-checker` | 5 | ✅ 阶段五完成后执行 |
| Flow D | MCP 测试 | `mcp-tester` + `security-tester` + `performance-tester` + `reality-checker` | 4 | ✅ 阶段五完成后执行 |

**注意**：
- Flow A **不含** `compatibility-tester`，渠道适配检测已集成在 `skill-tester` 内
- `evidence-collector` 不在并行数组中，在所有 subagent 完成后**独立执行**

### Flow B 双模式阶段定义（B 模式扩展）

Flow B 支持 A 模式（文档完整）和 B 模式（文档不全/无文档）。**A 模式严格遵循标准 8 阶段（阶段零~七）**。B 模式在标准阶段之间插入 3 个独有阶段，总计 11 个阶段（B-阶段零~十）：

| B 模式阶段编号 | 对应主框架阶段 | 内容 | 执行者 | 需批准 |
|--------------|-------------|------|--------|--------|
| B-阶段零 | 阶段零 | 环境就绪检查 | `environment-checker` subagent（执行检查） + 主 agent（发送确认） | ✅ 需确认 |
| B-阶段一 | 阶段一 | 需求解析 | `requirement-analyst` subagent | ❌ |
| B-阶段二 | 阶段二 | 质量评估 + 文档判定（判定走 A/B 模式） | `quality-assessor` subagent | ✅ 需批准 |
| B-阶段三 | —（B 模式独有） | 双边深度体验 | experience-tester-a + experience-tester-b（并行） | ❌ |
| B-阶段四 | —（B 模式独有） | 交叉核对 | experience-tester-a + experience-tester-b（交叉） | ❌ |
| B-阶段五 | —（B 模式独有） | 争议复检 + 补充体验 | experience-tester-a + experience-tester-b | ❌ |
| B-阶段六 | 阶段三 | 测试用例生成 | `test-designer` subagent | ❌ |
| B-阶段七 | 阶段四 | 用例评估 | `test-case-evaluator` subagent | ✅ 需批准 |
| B-阶段八 | 阶段五 | 并行测试执行 + 证据收集 | 各 Flow B 并行角色 subagent | ❌ |
| B-阶段九 | 阶段六 | 缺陷分析 | `defect-analyst` subagent | ❌ |
| B-阶段十 | 阶段七 | 报告整合 | `report-integrator` subagent | ❌ |

**B 模式门禁规则**：
- B-阶段二（质量评估）和 B-阶段七（用例评估）适用标准批准/拒绝规则（第九节）
- B-阶段二拒绝 → 打回 B-阶段一；B-阶段七拒绝 → 打回 B-阶段六
- B 模式独有阶段（B-阶段三/四/五）不需批准，前置交付物齐备后自动推进
- 沟通时统一使用「B-阶段X」前缀，避免与标准阶段编号混淆

**B 模式扩展输出文件**：
| 阶段 | 输出文件 | 目录 |
|------|---------|------|
| B-阶段三 | `experience-report-a.md` + `experience-report-b.md` | `EXPERIENCE/` |
| B-阶段四 | `cross-check-a-by-b.md` + `cross-check-b-by-a.md` | `EXPERIENCE/` |
| B-阶段五 | 更新后的 `experience-report-a.md` + `experience-report-b.md` | `EXPERIENCE/` |

---

## 五、超时配置（统一值）

| 场景 | 超时值 | 说明 |
|------|--------|------|
| subagent 单次超时 | **15 分钟（900 秒）** | 任何 subagent 运行超过此值则触发超时处理 |
| subagent 启动重试 | 最多 3 次，间隔 5 秒 | gateway closed 时触发 |
| subagent 超时后重试 | 1 次，等 30 秒后重启 | 超时处理规则 |
| 无响应自动继续 | 30 分钟（催 3 次，每 10 分钟一次） | 批准/拒绝环节 |
| 微信降级重试 | 3 次，间隔 5 秒，总超时 30 秒 | 第一条消息发送失败 |
| 阶段五并行总时长 | **15 分钟**（= 900 秒） | 所有 subagent 须在此窗口内完成 |

---

## 六、角色分类体系

每个角色按职责分为三种类型，影响调度策略：

| 类型 | 定义 | 可跨阶段 | 示例 |
|------|------|---------|------|
| `orchestrator` | 主流程调度、用户交互、批准请求 | ✅ | 主 agent（唯一） |
| `executor` | 负责产出阶段交付物，不直接与用户交互 | ❌ | environment-checker, requirement-analyst, test-designer, skill-tester, report-integrator |
| `validator` | 审计、评估、覆盖检查或缺陷归并 | ❌ | spec-consistency-validator, quality-assessor, test-case-evaluator, evidence-collector, defect-analyst |

**调度规则**：
- 主 agent 是唯一 `orchestrator`，负责路由、阶段推进、批准请求、打回决策和对外发送
- 除主 agent 外，阶段零到阶段七的角色默认都以对应 `subagent` 执行；串行阶段启动 1 个阶段角色，阶段五或 B 模式体验阶段按模板并行启动多个角色
- `executor` / `validator` 都可以作为 subagent；区别在于前者偏生产交付物，后者偏审计评估
- `evidence-collector` 不参与并行组，只在所有测试执行角色结束后再启动

**辅助角色**：
- `tool-evaluator`、`workflow-optimizer` 属于按需触发的辅助 `validator`，不进入标准 8 阶段或 Flow B 11 阶段调度表。
- 这两个角色只在用户主动请求工具评估、流程优化或质量争议仲裁时启动。

### 角色依赖图

```
requirement-analyst ──PRODUCT-FINGERPRINT.json / SPEC.md──→ spec-consistency-validator
       │                                                      │
       │                                           SPEC-CONSISTENCY-REVIEW.md
       ↓                                                      ↓
  quality-assessor ←────────────读取──────────── spec-consistency-validator
       │
PRODUCT-QUALITY-REVIEW.md
       ↓
  test-designer ←────参考─────── quality-assessor
       │
   TEST-DESIGN.md
       ↓
  test-case-evaluator
       │
   TEST-CASE-REVIEW.md
       ↓
  ┌──────────────────────────────────┐
  │ skill-tester    security-tester  │  ← 并行 executor
  │ functional-tester  compatibility-tester  │
  │ performance-tester  accessibility-auditor│
  │ mcp-tester        reality-checker        │
  └──────────────────────────────────┘
       │
       ↓
  evidence-collector  ← 依赖所有 executor 完成
       │
       ↓
  defect-analyst
       │
       ↓
  report-integrator
```

**数据契约**：每个角色的输入来源和输出消费者必须在角色文件中声明 `## 输入来源` 和 `## 下游消费者`。

### 标准调度模板

```text
阶段零：
  主 agent 路由测试类型
    -> 生成 STAGE-SUBAGENT-PLAN.json
    -> 启动 environment-checker subagent
    -> 汇总环境就绪结果
    -> 向用户请求确认

阶段一：
  启动 requirement-analyst subagent
    -> 产出 PRODUCT-FINGERPRINT.json / SPEC.md
  启动 spec-consistency-validator subagent
    -> 产出 SPEC-CONSISTENCY-REVIEW.md
  主 agent 发送阶段一交付物

阶段二：
  启动 quality-assessor subagent
    -> 产出 PRODUCT-QUALITY-REVIEW.md
  主 agent 发送交付物并请求批准

阶段三：
  启动 test-designer subagent
    -> 产出 TEST-DESIGN.md / SURFACE-EXECUTION-PLAN.json
  主 agent 发送阶段三交付物

阶段四：
  启动 test-case-evaluator subagent
    -> 产出 TEST-CASE-REVIEW.md
  主 agent 发送交付物并请求批准

阶段五：
  按 Flow 模板并行启动测试角色 subagent
    -> 所有角色完成后
    -> 启动 evidence-collector subagent

阶段六：
  启动 defect-analyst subagent
    -> 产出 DEFECT-REPORT.md

阶段七：
  启动 report-integrator subagent
    -> 产出 FINAL-TEST-REPORT.md
```

**硬规则**：
- 主 agent 不能跳过阶段角色，直接代写对应阶段交付物
- 阶段角色只负责产出本阶段结果，不直接向用户发起批准或选择题
- 需批准阶段的批准动作只能由主 agent 发起和处理

---

## 六-B、文档优先级规则

当多个文档对同一问题的描述出现冲突时，按以下优先级处理：

| 优先级 | 文档类型 | 说明 |
|--------|---------|------|
| 1（最高） | Flow 文件（`flows/*.md`） | 最具体的执行模板 |
| 2 | Reference 文件（`reference-*.md`） | 专项规范 |
| 3 | DEFINITIONS.md | 统一事实源 |
| 4 | Role 文件（`roles/*.md`） | 角色行为定义 |
| 5（最低） | SKILL.md 主入口 | 调度逻辑 |

**原则**：越具体的文档优先级越高。Flow 文件 > Reference 文件 > DEFINITIONS.md > Role 文件 > SKILL.md。

---

## 六-C、轻量模式

当被测对象规模较小时，自动合并部分阶段以降低流程开销：

### 触发条件（满足任一即进入轻量模式）

| 条件 | 阈值 |
|------|------|
| Skill 文件总行数 | < 100 行 |
| 能力地图能力数（CAP-ID） | ≤ 3 个 |
| 测试维度矩阵必测维度 | ≤ 5 个 ★ |
| 用户显式要求 | "快速测试"、"轻量模式" |

### 轻量模式变更

| 标准阶段 | 轻量模式 | 说明 |
|---------|---------|------|
| 阶段零 + 阶段一 | 合并为「阶段零-A」 | 环境检查 + 需求解析一次完成 |
| 阶段二 | 保留，但批准改为自动确认 | 质量评估仍执行，门禁降级 |
| 阶段三 + 阶段四 | 合并为「阶段三-A」 | 测试设计 + 自检合并，跳过独立评估门禁 |
| 阶段五~七 | 不变 | 执行、缺陷分析、报告整合保持完整 |

**轻量模式必须在环境就绪报告中显式声明**，格式：`模式：轻量 | 触发条件：{行数/能力数/维度数/用户要求}`。

---

## 六-D、角色输入/输出约定（阶段角色 subagent）

| 角色 | 读取文件 | 输出文件 | Flow |
|------|---------|---------|------|
| spec-consistency-validator | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、被测仓库事实源 | `SPEC-CONSISTENCY-REVIEW.md` | A/B/C/D |
| skill-tester | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md`、`SURFACE-EXECUTION-PLAN.json`、Skill 源码 | `TEST-EXECUTION/skill-results.md` | A |
| security-tester | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md`、目标系统 | `TEST-EXECUTION/security-results.md` | A/B/C/D |
| functional-tester | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md` | `TEST-EXECUTION/functional-results.md` | B/C |
| compatibility-tester | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md`、目标系统 | `TEST-EXECUTION/compatibility-results.md` | B/C |
| performance-tester | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md`、目标系统 | `TEST-EXECUTION/performance-results.md` | B/C/D |
| accessibility-auditor | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md`、目标 URL / 页面截图 | `TEST-EXECUTION/accessibility-results.md` | B |
| mcp-tester | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、MCP Server | `TEST-EXECUTION/mcp-results.md` | D |
| reality-checker | `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`TEST-DESIGN.md`、目标系统 | `TEST-EXECUTION/reality-results.md` | C/D |
| evidence-collector | 监听 `TEST-EXECUTION/` 目录 | `DEFECTS/evidence-collection.md` | 全部 |

---

## 七、Token 预算规则（统一值）

### 黑盒优先原则

在信息收集阶段，优先使用低成本手段获取信息，避免消耗大量 Token 读取完整源文件：

| 优先级 | 手段 | 适用场景 | Token 消耗 |
|--------|------|---------|-----------|
| 1 | `--help` / `--version` 输出 | 了解工具用法和版本 | 极低 |
| 2 | API schema / OpenAPI spec | 了解接口结构和字段 | 低 |
| 3 | `head` / `tail` 部分读取 | 确认文件格式和关键行 | 低 |
| 4 | 截图 + DOM 检查 | 了解页面结构和元素 | 中 |
| 5 | 完整读取源文件 | 必须深入分析逻辑时 | 高 |

**规则**：
- 阶段零和阶段一的信息收集，默认使用优先级 1-3 的手段
- 只有在低成本手段无法满足需求时，才读取完整文件
- 读取文件时优先使用 `offset` + `limit` 分段读取，不要一次读取整个大文件
- 每次完整文件读取必须在 Token 日志中记录消耗估算

### 预算阈值

| 阈值 | 动作 |
|------|------|
| 50K/角色（建议值） | 预算上限 |
| 90% | 预警，通知用户，确认是否继续 |
| 100% | 立即强制停止，保留已产出文件 |
| 用户授权「无限模式」 | 恢复运行，无上限（仅当前阶段有效） |

**Token 监控职责**：
| 阶段 | 监控者 | 职责 |
|------|--------|------|
| 主 agent 编排过程 | **主 agent 自身** | 记录阶段切换、批准交互、打回动作的 Token 消耗到 `stage-transition-log.json` |
| 阶段零~七角色 subagent | **主 agent 监控** | 主 agent 在阶段角色 subagent 启动时记录起始点，完成/超时时记录终止点；阶段总 Token = 各阶段角色 Token 之和 |
| 单个 subagent | **subagent 自身** | 在结果文件末尾追加 `Token 消耗：约 XXXK`（估算值即可） |
| 90% 预警触发 | **主 agent** | 主 agent 检测到任一 subagent 接近预算时，向用户发送预警并确认是否继续 |
| 100% 强制停止 | **主 agent** | 主 agent 发送停止指令（如平台支持），或标记该 subagent 为「Token 耗尽，部分完成」 |
| 无限模式授权 | **用户** | 用户回复「无限模式」后，主 agent 解除当前阶段的 Token 限制 |

---

## 八、渠道降级规则（统一描述）

主入口统一引用，**不允许**在各 Flow/Role 中重复手写渠道规则。

| 渠道 | 降级行为 |
|------|---------|
| 微信 | 第一条文字 + 第二条文件（间隔 5 秒，最多重试 3 次，总超时 30 秒） |
| QQ | 同微信降级逻辑 |
| 飞书 | 原生支持，优先使用 |
| Telegram | 原生支持，优先使用 |

> ⚠️ 禁止在 `compatibility-tester.md` 或任何归档模板中重复手写渠道降级规则，均引用本文件或主入口。

---

## 九、审批与打回规则（统一）

| 规则 | 值 |
|------|---|
| 需批准的阶段 | 阶段二、阶段四 |
| 每阶段最多拒绝次数 | 3 次 |
| 第 3 次拒绝后 | 自动 No-Go，终止测试流程 |
| 打回理由最低长度 | 10 字符 |
| 打回路径 | 阶段二拒绝 → 阶段一；阶段四拒绝 → 阶段三 |
| 阶段五/六打回循环上限 | 3 轮，第 3 轮后强制进阶段七 |
| 拒绝计数持久化文件 | `rejection-count.json`（JSON 格式） |

### 阶段门禁规则

| 规则 | 说明 |
|------|------|
| 主动发送 | 阶段交付物一旦生成，主 agent 必须立即发送给用户；用户未追问不能作为延迟发送理由 |
| 逐阶段推进 | 阶段 N 交付物独立发送后，才能开始阶段 N+1 |
| 禁止合并输出 | 每个阶段的交付物必须独立发送，禁止合并 |
| 批准前置 | 需批准的阶段（二、四）获批后才能继续 |
| 状态前置检查 | 进入任何阶段前，验证上一阶段交付物已存在 |
| 发送路径 | 交付物发送必须使用 `files/...` 中转路径，不得直接发送 `memory/...` |
| 语言一致性 | 交付物描述性内容必须使用用户发起测试请求的语言 |

**执行顺序**：
```
阶段 N 完成 → 立即独立发送交付物（+ 批准请求如需）→ 等待批准（如需）→ 执行阶段 N+1
```

补充判定：

- 阶段文件已写入但尚未发送给用户，不算阶段完成
- 用户追问“把文件发我”时，视为上一轮漏发；应立即补发交付物，而不是重新解释阶段状态
- 若平台拒绝 `memory/...` 路径，必须改走 `prepare_report_delivery.py` 生成的 `files/...` 路径；仍失败时要在同轮消息里明确告知报告工作区路径

### 阶段转换审计日志

每次阶段转换写入 `stage-transition-log.json`：

```json
{
  "from_stage": 1, "to_stage": 2,
  "timestamp": "YYYY-MM-DD HH:mm:ss",
  "deliverable_file": "SPEC.md",
  "approval_required": false,
  "gate_check_passed": true
}
```

### 主/子 agent 交互边界

- 主 agent 负责用户交互、批准、阶段推进、打回与重跑决策
- 阶段角色 subagent 只负责执行、写结果、写 blocker，不直接要求用户做选择
- 阶段角色 subagent 遇阻时保留已产出文件并写明未完成范围，由主 agent 决定后续

---

## 十、执行验证标准（反偷懒机制）

> **核心规则：读文档 ≠ 测试。静态分析 ≠ 验证。检查配置 ≠ 执行。**

### 执行证明格式（阶段五每个测试用例必须包含）

| 字段 | 含义 | 示例 |
|------|------|------|
| 执行动作 | 具体执行了什么 | `执行命令 skill-tester --trigger "xxx"` |
| 实际输入 | 真实传入的参数 | `{"message": "帮我测试", "channel": "telegram"}` |
| 实际输出 | 真实返回的内容（非预期结果） | `{"status": 200, "body": "已触发测试流程"}` |
| 判定 | ✅ 通过 / ❌ 失败 | ✅ |

### 执行率硬性要求

| 执行率 | 处理方式 |
|--------|---------|
| ≥ 90% | 正常通过 |
| 70%~89% | 标注「测试覆盖不足」但允许继续 |
| 50%~69% | 强制打回，补充执行后重新提交 |
| < 50% | 测试报告标记 No-Go |

### 环境不足时的降级阶梯（按优先级，禁止直接跳过）

| 优先级 | 方案 | 标注 | 适用说明 |
|--------|------|------|---------|
| 1 | 真实调用（`sandbox-skill-invoke --mode live`） | 无需标注 | Skill 在沙箱中通过 OpenClaw CLI 真实调用，完整调用链 |
| 2 | 本地真实执行（`sandbox-skill-invoke --mode shim-live`） | 无需标注 | 无 OpenClaw CLI，但 Skill 提供 `testing.json` 或 `scripts/test-entry.*`，可在沙箱内真实执行 |
| 3 | 追踪调用（`sandbox-skill-invoke --mode trace`） | 标注「追踪调用」 | 解析 `SKILL.md` 追踪决策树，不实际执行工具 |
| 4 | 沙箱命令执行（`sandbox-exec`） | 标注「沙箱执行」 | 支持 `host-logged` 与 `container` 两种后端；默认 `host-logged` 不构成容器/VM 级安全隔离，`container` 提供容器级隔离 |
| 5 | 构造模拟输入/输出 | 标注「模拟执行」+ 实际构造的输入输出 | 手动构造工具调用和响应 |
| 6 | 部分执行可执行部分 | 标注「部分执行」+ 已执行步骤 | 仅执行可执行的子步骤 |
| 7 | 降级为静态分析（最后手段） | 必须标注「P1 未执行，仅静态分析，无法验证运行时行为」 | 仅读文档分析 |

**降级合规要求**：

- `live` / `shim-live` 是仅有的真实执行级别。
- `trace` 不得写成“功能通过”或计入真实执行率。
- 仅有静态分析或 `trace` 证据时，不得给出 `PASS`、`PARTIAL PASS`、功能覆盖率、API 覆盖率或规则覆盖率。
- 关键功能用例要求真实执行时，必须使用 `--strict-real`；若只能退到 `trace`，结果应为 blocker。
- `auto --strict-real` 在存在独立 verifier 时应优先选择 `shim-live`；否则再尝试 `live`，最后才是 `shim-live` / blocker。
- `live --strict-real` 必须拿到 OpenClaw CLI 原生回传的 runtime telemetry protocol（当前版本：`nexus-live-telemetry/v1`）；没有协议或协议字段不完整时不得返回成功。
- `shim-live --strict-real` 必须提供独立的 `--verification-manifest`；该文件必须位于 Skill 目录外，且在可识别仓库根时不能与 Skill 同仓库。没有 verifier 时不得返回成功。
- `openclaw-extension` 若要证明真实 OpenClaw runtime / subagent 行为，优先通过 `testing.json.openclawExtensionRuntimeHarness` 产出 `behaviorVerified`、`runtimeVerified`、`runtimeTransport`、`registeredHooks`；没有 runtime harness 但 live runtime 可用时，至少先留下 `runtime-probed=true` 的 live probe 证据，不能直接降级成“无 runtime”。
- 负向触发用例必须拿到显式 `triggerMatched=false`；`unknown` 不算通过。
- 上下文保持用例必须拿到显式 `contextReferences`；关键词猜测不算通过。
- 渠道用例必须拿到显式 `deliveryStatus` 和送达证据；本地渲染文件不算送达证明。
- `sandbox-exec --backend host-logged` 仅适用于可信命令验证，并且必须显式传 `--ack-unsafe-exec`。
- `sandbox-exec --backend container` 用于不可信或高风险命令验证；默认关闭容器网络，只有显式传 `--allow-network` 才能放开。

### 渠道测试执行要求

- 真实发送测试消息到已配置渠道，记录送达状态
- **禁止**仅检查配置存在就写「通过」
- 送达状态必须可追溯到 receipt / delivery evidence
- 渠道不可达时按降级阶梯处理

---

## 十一、增量复测流程

当缺陷修复后需要复测时，支持增量复测而非全量重跑。

### 复测范围判定

| 修复范围 | 复测要求 |
|---------|---------|
| P0 缺陷修复 | 必须全量重跑阶段五（该缺陷可能影响其他模块） |
| P1 缺陷修复 | 复测该缺陷相关模块 + 关联模块 |
| P2/P3 缺陷修复 | 仅复测该缺陷对应用例 |

### 增量复测步骤

1. 读取 DEFECT-REPORT.md 中标记为「已修复」的缺陷
2. 按复测范围判定表确定复测范围
3. 仅执行受影响的 subagent 角色（非全部角色）
4. 输出到 `TEST-EXECUTION/retest-{角色}-{timestamp}.md`
5. 更新 DEFECT-REPORT.md 中的缺陷状态

### 复测报告格式

```
## 复测记录

### 缺陷 {ID}
• 原始级别：P0/P1/P2/P3
• 修复说明：（开发者提供的修复描述）
• 复测结果：✅ 已修复 / ❌ 未修复 / ⚠️ 部分修复
• 复测证据：（实际执行结果）
• 新发现问题：（如有）
```

---

## 十二、回归套件分层定义

| 套件类型 | 时长 | 频率 | 覆盖范围 | 通过标准 |
|---------|------|------|---------|---------|
| Smoke | 15-30 min | 每次提交 | 核心用户路径（P0 用例） | 100% 通过 |
| Sanity | 10-15 min | 热修复后 | 修复验证 + 关联功能 | 100% 通过 |
| Targeted | 30-60 min | 按变更 | 变更影响的模块 + 关联模块 | ≥ 95% 通过 |
| Full | 2-4 hours | 版本发布前 | 全量用例 | ≥ 90% 通过 |

**执行顺序**：Smoke 先跑 → 失败则停止修复构建 → P0 全过再跑 Targeted/Full

**复测策略**（引用第十一节）：
- P0 修复 → 全量重跑（可能影响其他模块）
- P1 修复 → Targeted 回归（关联模块）
- P2/P3 修复 → 仅复测该用例

### 回归套件维护职责

| 职责 | 负责者 | 说明 |
|------|--------|------|
| Smoke 套件抽取 | **报告整合师**（阶段七） | 从阶段五结果中提取所有 P0 用例，标记为 Smoke 套件 |
| 回归套件输出 | **报告整合师**（阶段七） | 在 `FINAL-TEST-REPORT.md` 中输出「推荐回归套件」节，列出 Smoke/Targeted 用例清单 |
| 套件更新 | **测试设计师**（阶段三） | 复测时读取上一轮的回归套件，更新变更影响的用例 |
| 套件执行频率 | **主 agent** | 根据触发场景（每次提交/热修复/版本发布）选择对应套件类型 |

**报告整合师输出格式（追加到 FINAL-TEST-REPORT.md）**：
```
## 推荐回归套件

### Smoke 套件（核心路径，每次提交必跑）
| 用例 ID | 用例名称 | 关联功能 | 预计时长 |
|---------|---------|---------|---------|
| TC-001 | xxx | 核心功能 | 2 min |

### Targeted 套件（变更影响范围）
| 用例 ID | 用例名称 | 关联模块 | 预计时长 |
|---------|---------|---------|---------|
| TC-010 | xxx | 模块 A | 5 min |
```

---

## 十三、AI 动态测试增强

### 核心原则

AI 测试工程师相比人工测试，具有**动态生成测试资产**的独特优势。测试角色必须充分利用这一能力，不得将自身限制在「读取现有内容→验证」的静态模式。

### 动态测试资产类型

| 资产类型 | 何时生成 | 设计者 | 执行者 | 示例 |
|---------|---------|--------|--------|------|
| 测试 Skill | 被测产品是测试框架/验证工具 | test-designer 设计规格 | skill-tester 创建并使用 | 合格 Skill、含缺陷 Skill、极端 Skill |
| 测试配置文件 | 被测产品处理配置 | test-designer 设计规格 | 对应 tester 创建 | 正确配置、错误配置、缺失配置 |
| 测试数据文件 | 被测产品处理数据 | test-designer 设计规格 | 对应 tester 创建 | CSV/JSON/文本、空文件、超大文件 |
| 模拟服务响应 | 被测产品依赖外部服务 | test-designer 设计规格 | skill-tester / security-tester | mock 响应、错误响应、超时响应 |
| 测试脚本/命令 | 被测产品需要特定触发条件 | test-designer 设计规格 | 对应 tester 创建并执行 | CLI 命令、API 调用、文件操作 |

### 生成流程

```
test-designer 分析被测产品功能
    ↓
识别需要动态生成的测试资产（基于产品类型和功能模块）
    ↓
在 TEST-DESIGN.md 中定义资产规格（FX 编号、内容、用途、创建方式、清理方式）
    ↓
阶段五执行时，测试工程师读取 FX 规格 → 按规格实际创建资产 → 用资产执行测试 → 记录实际结果 → 清理资产
```

### 元测试（Meta-Testing）分层规范

当被测产品是**测试/验证/分析类工具**时，测试设计必须包含以下四层：

| 层次 | 内容 | 目的 | 最低用例数 |
|------|------|------|-----------|
| M1: 基础通过 | 用完全合格的测试 Skill 验证核心流程 | 验证框架基础可用，零误报 | ≥ 2 |
| M2: 缺陷检出 | 用含已知缺陷的 Skill 验证检测能力（每类缺陷一个独立夹具） | 验证框架能发现问题，零漏检 | ≥ 核心功能模块数 |
| M3: 健壮性 | 用极端/异常 Skill 验证容错能力 | 验证框架不崩溃，错误信息明确 | ≥ 2 |
| M4: 端到端 | 用标准 Skill 走完完整测试流程（阶段零→七） | 验证端到端闭环 | ≥ 1 |

### 测试夹具编号与追溯

| 编号格式 | 说明 | 示例 |
|---------|------|------|
| FX-{NN} | 测试夹具编号，全局唯一 | FX-01, FX-02 |
| META-TC-{NN} | 元测试用例编号，与 FX 关联 | META-TC-01 使用 FX-01 |
| TC-{NN} | 常规测试用例编号（可引用 FX） | TC-15 使用 FX-03 |

**追溯要求**：TEST-DESIGN.md 中每个 FX 必须关联至少一个 TC/META-TC；每个 META-TC 必须引用一个 FX。

### 数据驱动用例扩展（复杂 Skill / 安全工具强制）

当能力清单中存在**规则、决策路径、检查项**等可枚举 inventory 时，阶段三必须按 inventory 展开，而不是每个 capability 只写 1 条泛化用例：

- 规则清单：每条规则至少 2 个用例
  - 能检出
  - 不误报
- 决策路径：每条路径至少 1 个独立用例
  - 如 `DENY` / `CONFIRM` / `ALLOW`
- 检查项：每项检查至少 1 个真实执行用例
  - 如 patrol / monitor / health / runtime checks
- 若 capability 看起来是规则/决策/检查项驱动，但事实指纹未抽取到明细 inventory，阶段四必须判定测试设计不通过

---

## 十四、沙箱执行环境

> **完整规格统一引用** `reference-sandbox-spec.md`。以下为关键定义速查。

### 沙箱根路径

`.nexus-sandbox/`（相对于仓库根目录）

### Session ID 格式

`{YYYYMMDD-HHmmss}-{random6hex}`（如 `20260403-143025-a1b2c3`）

### 能力级别

| 级别 | 条件 | 对应降级阶梯 |
|------|------|------------|
| Full | Node.js + Python 均可用 | 等同真实执行（非降级） |
| Partial | 仅一个运行时可用 | 等同真实执行（受限运行时） |
| Minimal | 无运行时，仅文件系统 | 通常只能到降级阶梯第 3 级或更低，不能宣称真实执行 |

### 超时配置

| 场景 | 超时值 |
|------|--------|
| 单命令执行 | 30 秒（可通过 `--timeout` 调整） |
| 沙箱总时长 | 10 分钟（600 秒） |
| 依赖安装（npm/pip） | 120 秒 |

### 与降级阶梯的关系

> **完整降级阶梯定义见** `reference-sandbox-spec.md` **第八节。**以下仅为速查映射。

| 降级阶梯级别 | 沙箱状态 |
|------------|---------|
| 1–2 (`live` / `shim-live`) | 真实执行，沙箱提供隔离目录和运行时 |
| 3 (`trace`) | 仅静态路径追踪 |
| 4 (`sandbox-exec`) | 通用命令执行，可信 `host-logged` / 不可信 `container` |
| 5–7 | 沙箱不可用或能力不足时的降级手段 |

---

## 十五、外部测试用例获取

> **完整规格统一引用** `reference-external-case-sourcing.md`。以下为关键定义速查。

### 编号约定

| 编号格式 | 说明 | 示例 |
|---------|------|------|
| EXT-TC-{NN} | 外部获取的测试用例，全局唯一 | EXT-TC-01, EXT-TC-02 |
| EXT-FX-{NN} | 外部获取的测试夹具 | EXT-FX-01 |

**编号规则**：EXT-TC/EXT-FX 独立于 TC/FX/META-TC/FX 编号序列，不占用内部编号。

### 何时必须获取

| 场景 | 要求 |
|------|------|
| 安全类产品 | **必须**搜索 CVE/NVD/漏洞库 |
| 有已知测试套件的产品 | **必须**搜索并评估官方测试套件 |
| 测试框架/验证工具 | **建议**搜索同类框架的测试方案 |
| 其他产品 | **可选** |

### 来源追溯要求

TEST-DESIGN.md 中引用的外部用例必须包含来源追溯表：

```
| Case ID | Source | URL | License | Adapted From | Notes |
|---------|--------|-----|---------|-------------|-------|
| EXT-TC-01 | GitHub user/repo | https://... | MIT | test/scan.test.ts L45-60 | 适配为 CLI 调用 |
```

### 评估最低分

外部用例必须通过评估评分卡（6 维度加权），加权平均分 ≥ 2.0/3.0 方可采纳。详见 `reference-external-case-sourcing.md`。

---

## 十六、Skill 类型分类体系

> **适用范围**：Flow A（Skill 测试）。阶段一需求解析师必须对被测 Skill 进行分类，分类结果写入 SPEC.md，后续所有阶段引用。

### 六种 Skill 类型

| 类型 ID | Skill 类型 | 特征 | 测试侧重 | 典型例子 |
|---------|-----------|------|---------|---------|
| ST-1 | 简单转换型 | 1 触发, 0-1 工具, 文本进/文本出, 无状态 | 输入输出格式、编码边界、空值处理 | 文本格式化、单位换算、翻译 |
| ST-2 | 数据获取型 | 调用外部 API、数据抓取、结果转换 | API 错误处理、超时、数据格式、缓存、降级 | 天气查询、股票行情、新闻摘要 |
| ST-3 | 多工具编排型 | 2+ 工具串联/并联, 决策逻辑, 中间状态 | 工具链完整性、中间状态、部分失败恢复、执行顺序 | 代码审查（读→分析→写报告）、数据管道 |
| ST-4 | 交互对话型 | 多轮对话, 上下文管理, 状态追踪, 澄清追问 | 上下文保持、轮次上限、状态损坏、话题切换 | 问答助手、教学导师、任务引导 |
| ST-5 | 代码生成/分析型 | 复杂输入解析, 代码/结构化输出, 语言感知 | 语言覆盖、边界语法、输出正确性、格式一致性 | 代码生成、代码审查、文档生成 |
| ST-6 | 系统操作型 | 文件操作, 命令执行, 环境变更, 有副作用 | 权限边界、回滚机制、安全隔离、副作用验证 | 项目脚手架、自动部署、文件批处理 |

### 分类规则

1. **主类型 + 次类型**：一个 Skill 必须有且仅有一个主类型，可选一个次类型。例：`ST-3（主）+ ST-5（次）` 表示多工具编排型 Skill，以代码分析为主要输出。
2. **分类依据**：根据 SPEC.md 的能力地图（Capability Map）综合判断，不是根据 Skill 名称或描述猜测。
3. **当能力地图包含多种类型特征时**：以占比最大的能力类型为主类型，第二大为次类型。
4. **分类不确定时**：选择测试要求更高的类型（宁可多测不可少测）。

### 分类输出格式（写入 SPEC.md）

```
## Skill 类型分类

| 维度 | 值 |
|------|---|
| 主类型 | ST-X（类型名称） |
| 次类型 | ST-Y（类型名称）或 无 |
| 分类依据 | （简述判断理由，引用能力地图中的具体 CAP-ID） |
| 测试策略影响 | （该分类导致哪些额外测试维度被激活） |
```

---

## 十七、能力驱动测试维度矩阵

> **适用范围**：Flow A（Skill 测试）。测试设计师（阶段三）必须根据 Skill 类型从此矩阵中选取必测维度，用例评估师（阶段四）根据此矩阵验证覆盖完整性。

### 维度定义

| 维度 ID | 维度名称 | 说明 |
|---------|---------|------|
| TD-01 | 触发准确性 | 正向/逆向/模糊触发，验证 Skill 是否准确识别用户意图 |
| TD-02 | 参数空间穷举 | 每个工具的每个参数在有效/无效/边界值各测一遍 |
| TD-03 | 工具链序列验证 | 多工具编排的执行顺序、数据传递、中间状态 |
| TD-04 | 多轮上下文保持 | 多轮对话中上下文是否正确保留和引用 |
| TD-05 | 多轮上下文边界 | 上下文窗口溢出、话题切换、上下文重置 |
| TD-06 | 模糊意图处理 | 用户意图不明确时 Skill 的澄清/降级/拒绝行为 |
| TD-07 | 能力边界探测 | 发送"刚好超出 Skill 能力范围"的请求，验证优雅降级 |
| TD-08 | 外部服务 Mock/故障 | 外部 API 超时/错误/空数据时的降级行为 |
| TD-09 | 并发调用 | 快速连续触发多次，验证无竞态/重复/丢失 |
| TD-10 | 输出格式跨渠道 | 同一响应在不同渠道（Telegram/飞书/QQ/微信）的格式正确性 |
| TD-11 | Token 效率 | 单次调用/多轮累积的 Token 消耗合理性 |
| TD-12 | 部分失败恢复 | 工具链中间步骤失败时的恢复/降级/报错行为 |
| TD-13 | 权限边界 | 尝试超出声明权限的操作，验证安全隔离 |
| TD-14 | 副作用验证 | 执行后的文件/环境/状态变更是否符合预期，是否可回滚 |
| TD-15 | 意图解释广度 | 同一能力用 ≥3 种不同措辞触发，验证理解鲁棒性 |
| TD-16 | 中间状态检查 | 多步流程中每一步的中间输出是否正确 |
| TD-17 | 代码混淆与安全深度检测 | 编码混淆、加密调用、高熵字符串、动态代码执行、反调试（由 security-tester 覆盖） |

### Skill 类型 × 测试维度矩阵

| 维度 | ST-1 简单转换 | ST-2 数据获取 | ST-3 多工具编排 | ST-4 交互对话 | ST-5 代码生成 | ST-6 系统操作 |
|------|:-----------:|:-----------:|:------------:|:-----------:|:-----------:|:-----------:|
| TD-01 触发准确性 | ★ | ★ | ★ | ★ | ★ | ★ |
| TD-02 参数空间穷举 | ○ | ★ | ★ | ○ | ★ | ★ |
| TD-03 工具链序列验证 | — | ○ | ★ | — | ○ | ★ |
| TD-04 多轮上下文保持 | — | — | ○ | ★ | — | — |
| TD-05 多轮上下文边界 | — | — | — | ★ | — | — |
| TD-06 模糊意图处理 | ★ | ★ | ★ | ★ | ★ | ★ |
| TD-07 能力边界探测 | ★ | ★ | ★ | ★ | ★ | ★ |
| TD-08 外部服务故障 | — | ★ | ★ | ○ | ○ | ○ |
| TD-09 并发调用 | ○ | ★ | ★ | ★ | ○ | ★ |
| TD-10 输出格式跨渠道 | ★ | ★ | ★ | ★ | ★ | ★ |
| TD-11 Token 效率 | ★ | ★ | ★ | ★ | ★ | ★ |
| TD-12 部分失败恢复 | — | ★ | ★ | ○ | ○ | ★ |
| TD-13 权限边界 | — | ○ | ○ | — | ○ | ★ |
| TD-14 副作用验证 | — | — | ○ | — | ○ | ★ |
| TD-15 意图解释广度 | ★ | ★ | ★ | ★ | ★ | ★ |
| TD-16 中间状态检查 | — | ○ | ★ | ○ | ○ | ★ |
| TD-17 安全深度检测 | — | — | ○ | — | ○ | ★ |

**图例**：★ = 必测（必须有用例覆盖）| ○ = 选测（建议覆盖）| — = 不适用

### 覆盖率计算

- **必测覆盖率** = 已覆盖的「★ 必测」维度数 / 该 Skill 类型的「★ 必测」维度总数
- 必测覆盖率 **≥ 95%** 方可通过阶段四用例评估
- 选测维度缺失需在 TEST-CASE-REVIEW.md 中说明理由

### 综合评分体系

综合评分 = 功能正确性(25%) + 安全合规(25%) + 性能达标(20%) + 边界覆盖(15%) + 文档一致(15%)

| 综合评分 | 等级 | 说明 |
|----------|------|------|
| 90-100 | A | 优秀，可直接投入生产 |
| 75-89 | B | 良好，有小问题待修复 |
| 60-74 | C | 一般，有中等问题需修复 |
| 45-59 | D | 较差，有重大问题 |
| 0-44 | F | 不合格，阻断发布 |

各维度评分标准由报告整合师根据测试结果综合判定，每维度 0-100 分。

### 能力地图（Capability Map）

由阶段一需求解析师生成，写入 SPEC.md。格式：

```
| Cap-ID | 能力名称 | 触发条件 | 使用工具 | 输出类型 | 已知边界 | 能力链依赖 |
|--------|---------|---------|---------|---------|---------|-----------|
| CAP-01 | ... | ... | ... | ... | ... | 无 / CAP-XX |
```

### 能力→用例追溯

- TEST-DESIGN.md 中每个用例标注 `capability-id` + `test-dimension`
- 阶段四构建 CAP × TD 覆盖矩阵，验证必测维度被覆盖
- 阶段六/七根据 CAP-ID 定位缺陷和展示覆盖率
