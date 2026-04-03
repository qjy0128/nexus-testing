# Nexus Testing Framework — 单一事实源

> 所有阶段、角色、文件、超时、Flow 配置均以此文件为准。主入口和 Flow/Role 文件只引用，不重复手写。

---

## 一、阶段定义（8 阶段，编号零~七）

| 阶段编号 | 阶段名称 | 执行者 | 输出文件 | 需批准 | 可打回 |
|----------|----------|--------|---------|--------|--------|
| 阶段零 | 环境就绪检查 | 主 agent | 环境就绪报告（内存中） | ✅ 需确认 | ❌ |
| 阶段一 | 需求解析 | 主 agent（需求解析师角色） | `SPEC.md` | ❌ | ❌ |
| 阶段二 | 质量评估 | 主 agent（质量评估师角色） | `PRODUCT-QUALITY-REVIEW.md` | ✅ 需批准 | ✅ 打回阶段一 |
| 阶段三 | 测试设计 | 主 agent（测试设计师角色） | `TEST-DESIGN.md` | ❌ | ❌ |
| 阶段四 | 用例评估 | 主 agent（用例评估师角色） | `TEST-CASE-REVIEW.md` | ✅ 需批准 | ✅ 打回阶段三 |
| 阶段五 | 并行测试执行 | 各 Flow 并行角色 subagent | `TEST-EXECUTION/*.md` | ❌ | ✅ 打回阶段三/五 |
| 阶段六 | 缺陷分析 | 主 agent（缺陷分析师角色） | `DEFECTS/DEFECT-REPORT.md` | ❌ | ✅ 打回阶段三/五 |
| 阶段七 | 报告整合 | 主 agent（报告整合师角色） | `FINAL-TEST-REPORT.md` | ❌ | ❌ |

**阶段零~七共 8 个阶段**。沟通时统一使用「阶段零」「阶段一」…「阶段七」。

---

## 二、阶段间上下文传递（唯一路径）

```
阶段一 → SPEC.md
阶段二 → PRODUCT-QUALITY-REVIEW.md
阶段三 → TEST-DESIGN.md
阶段四 → TEST-CASE-REVIEW.md
阶段五 → TEST-EXECUTION/*.md（各 subagent 输出各自文件）
阶段六 → DEFECTS/DEFECT-REPORT.md（汇总所有缺陷）
阶段七 → FINAL-TEST-REPORT.md
```

---

## 三、报告目录结构

所有报告输出到：`memory/nexus-reports/{date}-{test-type}-{flow}/`

```
{date}-{test-type}-{flow}/
├── SPEC.md                          # 阶段一
├── PRODUCT-QUALITY-REVIEW.md        # 阶段二
├── TEST-DESIGN.md                   # 阶段三
├── TEST-CASE-REVIEW.md              # 阶段四
├── rejection-count.json              # 拒绝计数持久化（动态生成）
├── stage-transition-log.json         # 阶段转换审计日志（动态生成）
├── TEST-EXECUTION/
│   ├── progress-{角色}.txt         # 进度文件（动态生成）
│   ├── skill-results.md             # Flow A 必出
│   ├── security-results.md           # Flow A/D 必出
│   ├── compatibility-results.md      # Flow B/C/D 必出
│   ├── performance-results.md        # Flow D 必出
│   ├── mcp-results.md               # Flow D 必出
│   ├── android-results.md            # Flow C 必出
│   └── evidence-collection.md       # 证据收集（阶段五后执行）
├── DEFECTS/
│   ├── DEFECT-REPORT.md             # 阶段六
│   ├── evidence/                    # 缺陷证据截图/日志
│   └── rejection-records.md          # 拒绝记录
├── FINAL-TEST-REPORT.md             # 阶段七
└── archive/                         # 复测归档目录（复测时旧报告移入）
    └── {timestamp}/                  # 时间戳子目录，不覆盖已有内容
```

**路径变量约定**：
- `{date}`、`{test-type}`、`{flow}` 三者缺一不可
- Flow/Role 文档引用报告路径时，必须保留完整模板，禁止省略 `{flow}`

**Flow B B 模式扩展文件**（双边体验流程特有）：
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
| Flow A | Skill 测试 | `skill-tester`（含运行时性能测试） + `security-tester` | 2 | ✅ 阶段五后执行 |
| Flow B | 网页+接口测试 | `functional-tester` + `compatibility-tester` + `security-tester` + `performance-tester` + `accessibility-auditor` | 5 | ✅ 阶段五后执行 |
| Flow C | 安卓测试 | `functional-tester` + `compatibility-tester` + `security-tester` + `performance-tester` + `reality-checker` | 5 | ✅ 阶段五后执行 |
| Flow D | MCP 测试 | `mcp-tester` + `security-tester` + `performance-tester` + `reality-checker` | 4 | ✅ 阶段五后执行 |

**注意**：
- Flow A **不含** `compatibility-tester`，渠道适配检测已集成在 `skill-tester` 内
- `evidence-collector` 不在并行数组中，在所有 subagent 完成后**独立执行**

### Flow B 双模式阶段定义（B 模式扩展）

Flow B 支持 A 模式（文档完整）和 B 模式（文档不全/无文档）。**A 模式严格遵循标准 8 阶段（阶段零~七）**。B 模式在标准阶段之间插入 3 个独有阶段，总计 10 个阶段：

| B 模式阶段编号 | 对应主框架阶段 | 内容 | 执行者 | 需批准 |
|--------------|-------------|------|--------|--------|
| B-阶段零 | 阶段零 | 环境就绪检查 | 主 agent | ✅ 需确认 |
| B-阶段一 | 阶段一 | 需求解析 | 主 agent（需求解析师） | ❌ |
| B-阶段二 | 阶段二 | 质量评估 + 文档判定（判定走 A/B 模式） | 主 agent（质量评估师） | ✅ 需批准 |
| B-阶段三 | —（B 模式独有） | 双边深度体验 | experience-tester-a + experience-tester-b（并行） | ❌ |
| B-阶段四 | —（B 模式独有） | 交叉核对 | experience-tester-a + experience-tester-b（交叉） | ❌ |
| B-阶段五 | —（B 模式独有） | 争议复检 + 补充体验 | experience-tester-a + experience-tester-b | ❌ |
| B-阶段六 | 阶段三 | 测试用例生成 | 主 agent（测试设计师） | ❌ |
| B-阶段七 | 阶段四 | 用例评估 | 主 agent（用例评估师） | ✅ 需批准 |
| B-阶段八 | 阶段五 | 并行测试执行 + 证据收集 | 各 Flow B 并行角色 subagent | ❌ |
| B-阶段九 | 阶段六 | 缺陷分析 | 主 agent（缺陷分析师） | ❌ |
| B-阶段十 | 阶段七 | 报告整合 | 主 agent（报告整合师） | ❌ |

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

## 六、角色输入/输出约定（阶段五 subagent）

| 角色 | 读取文件 | 输出文件 | Flow |
|------|---------|---------|------|
| skill-tester | `SPEC.md`、`TEST-DESIGN.md`、Skill 源码 | `TEST-EXECUTION/skill-results.md` | A |
| security-tester | `SPEC.md`、Skill 源码、测试日志 | `TEST-EXECUTION/security-results.md` | A/D |
| functional-tester | `SPEC.md`、`TEST-DESIGN.md` | `TEST-EXECUTION/functional-results.md` | B/C |
| compatibility-tester | `SPEC.md`、框架输出样本 | `TEST-EXECUTION/compatibility-results.md` | B/C |
| performance-tester | `SPEC.md`、执行日志 | `TEST-EXECUTION/performance-results.md` | B/C/D |
| accessibility-auditor | `SPEC.md`、界面截图 | `TEST-EXECUTION/accessibility-results.md` | B |
| mcp-tester | `SPEC.md`、MCP Server | `TEST-EXECUTION/mcp-results.md` | D |
| reality-checker | `SPEC.md`、执行结果 | `TEST-EXECUTION/reality-results.md` | C/D |
| evidence-collector | 监听 `TEST-EXECUTION/` 目录 | `DEFECTS/evidence-collection.md` | 全部 |

---

## 七、Token 预算规则（统一值）

| 阈值 | 动作 |
|------|------|
| 50K/角色（建议值） | 预算上限 |
| 90% | 预警，通知用户，确认是否继续 |
| 100% | 立即强制停止，保留已产出文件 |
| 用户授权「无限模式」 | 恢复运行，无上限（仅当前阶段有效） |

**Token 监控职责**：
| 阶段 | 监控者 | 职责 |
|------|--------|------|
| 阶段一~四（主 agent 执行） | **主 agent 自身** | 每阶段完成后记录 Token 消耗到 `stage-transition-log.json` |
| 阶段五（subagent 并行） | **主 agent 监控** | 主 agent 在 subagent 启动时记录起始点，完成/超时时记录终止点；总 Token = 各 subagent Token 之和 |
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

> ⚠️ 禁止在 `compatibility-tester.md`、`compatibility-tester-skill.md` 等文件中重复手写渠道降级规则，均引用本文件或主入口。

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

### 安全防护配置（HMAC 签名）

| 配置项 | 值 |
|--------|---|
| HMAC 盐值 | 从环境变量 `NEXUS_HMAC_SALT` 读取；未设置时使用运行时随机生成的 UUID 并写入 `.nexus-hmac-salt` 文件（该文件不纳入版本控制） |
| 签名算法 | HMAC-SHA256 |
| 密钥派生 | `HMAC-SHA256("{date}-{test-type}", <HMAC盐值>)` |
| 用途 | 拒绝计数签名验证，防止篡改 |

> **安全说明**：HMAC 盐值**禁止硬编码在文档或代码中**。生产环境必须通过环境变量 `NEXUS_HMAC_SALT` 注入。本地测试时自动生成的 `.nexus-hmac-salt` 文件须加入 `.gitignore`。

> 完整签名规范引用 `reference-approval-mechanism.md` 第四节。

### 阶段门禁强制规则（禁止跳阶段）

以下规则为**硬性约束**，主 agent 必须严格遵守：

| 规则 | 说明 |
|------|------|
| 禁止提前执行 | **所有阶段**：阶段 N 的交付物**独立发送完毕**之前，**禁止开始执行**阶段 N+1 的任何工作（包括读取输入、生成输出）。此规则不限于需批准的阶段，自动推进阶段（阶段一、三、五、六）同样必须先发送交付物再执行下一阶段 |
| 禁止合并输出 | 每个阶段的交付物必须**独立发送**，禁止将两个阶段的输出合并在同一条消息中。**无论是否需要批准，阶段 N 和阶段 N+1 的交付物绝不能在同一条消息中出现** |
| 禁止先执行后批准 | 需批准的阶段（阶段二、阶段四）完成前，**禁止预先偷偷执行**下一阶段再事后补发批准请求。批准请求发出时，下一阶段的交付物**必须不存在** |
| 禁止重复审批 | 每个阶段的批准请求**只发送一次**，重复发送视为流程错误 |
| 状态前置检查 | 进入任何阶段前，必须验证上一阶段的交付物已存在且（如需批准）已获批准 |
| 违反处理 | 任何违反以上规则的行为，视为**严重流程错误**，必须回退到最近的批准点重新执行 |
| 执行者 | **主 agent 自身**负责门禁检查，每个阶段开始前必须自检 |
| 审计日志 | 每次阶段转换必须写入 `stage-transition-log.json`（见下方格式） |

**正确执行顺序**（所有阶段通用，无一例外）：
```
阶段 N 完成 → 生成阶段 N 交付物
    ↓
发送阶段 N 交付物（独立消息，禁止夹带阶段 N+1 内容）+ 批准请求（如需） → 立即停止
    ↓
[分支A] 需批准（阶段二/四）：等待批准 → 收到批准后才执行阶段 N+1
[分支B] 自动推进（阶段零/一/三/五/六）：发送完毕后可执行阶段 N+1
    ↓
阶段 N+1 完成 → 生成阶段 N+1 交付物 → 独立发送 → 立即停止
    ↓
重复以上步骤
```

**⚠️ 自动推进 ≠ 合并执行**：「自动推进」仅表示不需要用户显式批准。**绝不意味着**可以将两个阶段的交付物合并生成或合并发送。即使阶段 N 自动推进到阶段 N+1，仍须：
1. 先单独发送阶段 N 的交付物
2. 再执行阶段 N+1
3. 再单独发送阶段 N+1 的交付物

**❌ 典型错误模式（阶段三→四最常见）**：
```
阶段三完成 → 同时生成 TEST-DESIGN.md + TEST-CASE-REVIEW.md → 合并一条消息发送 → 问「是否批准进入阶段四？」→ 阶段四已经偷偷做完了，批准毫无意义
```

**✅ 正确模式**：
```
阶段三完成 → 仅发 TEST-DESIGN.md（独立消息）→ 自动推进
    → 阶段四执行完成 → 仅发 TEST-CASE-REVIEW.md（独立消息）+「是否批准进入阶段五？」→ 等待批准
```

### 阶段转换审计日志（强制写入）

每次阶段转换时，主 agent **必须**写入审计记录到 `memory/nexus-reports/{date}-{test-type}-{flow}/stage-transition-log.json`：

```json
[
  {
    "from_stage": 1,
    "to_stage": 2,
    "timestamp": "YYYY-MM-DD HH:mm:ss",
    "deliverable_exists": true,
    "deliverable_file": "SPEC.md",
    "approval_required": false,
    "approval_status": null,
    "gate_check_passed": true
  },
  {
    "from_stage": 2,
    "to_stage": 3,
    "timestamp": "YYYY-MM-DD HH:mm:ss",
    "deliverable_exists": true,
    "deliverable_file": "PRODUCT-QUALITY-REVIEW.md",
    "approval_required": true,
    "approval_status": "approved",
    "gate_check_passed": true
  }
]
```

**主 agent 阶段转换前自检清单**（每次必查，记录到审计日志）：
1. 上一阶段交付物文件是否存在
2. 上一阶段交付物是否已发送给用户
3. 如需批准：批准状态是否为 approved
4. 以上全部通过 → `gate_check_passed: true` → 进入下一阶段
5. 任一不通过 → `gate_check_passed: false` → 拒绝转换，报告原因

### 主/子 agent 交互边界

- 主 agent 负责所有对用户可见的确认、批准、跳过方案和阶段推进
- 阶段五 subagent 只负责执行、写结果、写 blocker，不直接要求用户做选择
- subagent 遇到超时、权限不足、环境不足时，保留已产出文件并写明未完成范围，由主 agent 统一决定是否跳过或缩减范围

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

| 优先级 | 方案 | 标注 |
|--------|------|------|
| 1 | 真实执行 | 无需标注 |
| 2 | 沙箱执行 | 标注「沙箱执行」 |
| 3 | 构造模拟输入/输出 | 标注「模拟执行」+ 实际构造的输入输出 |
| 4 | 部分执行可执行部分 | 标注「部分执行」+ 已执行步骤 |
| 5 | 降级为静态分析（最后手段） | 必须标注「P1 未执行，仅静态分析，无法验证运行时行为」 |

### 降级合规性验证（由 evidence-collector 审计）

降级阶梯的合规性由 evidence-collector 在执行证明审计中一并检查：

| 检查项 | 合规标准 | 不合规判定 |
|--------|---------|-----------|
| 降级级别标注 | 非真实执行的用例必须标注降级级别（沙箱/模拟/部分/静态） | 未标注降级级别 |
| 降级理由 | 必须说明为什么无法使用更高优先级的执行方式 | 无理由直接降级到静态分析 |
| 降级尝试记录 | 标注尝试过哪些更高级别的执行方式及失败原因 | 未尝试直接跳到最低级别 |
| 静态分析标注 | 降级为静态分析时必须标注「P1 未执行，仅静态分析，无法验证运行时行为」 | 静态分析未标注 P1 |

**不合规的降级用例不计入执行率**，等同于未执行。

### 渠道测试执行要求

**禁止**的行为：
- 仅检查「渠道配置文件存在」→ 写「渠道适配通过」
- 仅检查「API Key 已配置」→ 写「渠道连通性通过」

**必须**的行为：
- 真实发送一条测试消息到每个已配置的渠道
- 记录实际送达状态（成功/失败/超时）
- 如果渠道 API Key 缺失或环境不可达，执行降级阶梯方案 2-5

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

---

## 十四、沙箱执行环境

> **完整规格统一引用** `reference-sandbox-spec.md`。以下为关键定义速查。

### 沙箱根路径

`.nexus-sandbox/`（相对于测试报告目录）

### Session ID 格式

`{YYYYMMDD-HHmmss}-{random6hex}`（如 `20260403-143025-a1b2c3`）

### 能力级别

| 级别 | 条件 | 对应降级阶梯 |
|------|------|------------|
| Full | Node.js + Python 均可用 | 等同真实执行（非降级） |
| Partial | 仅一个运行时可用 | 等同真实执行（受限运行时） |
| Minimal | 无运行时，仅文件系统 | 等同降级阶梯第 3 级 |

### 超时配置

| 场景 | 超时值 |
|------|--------|
| 单命令执行 | 30 秒（可通过 `--timeout` 调整） |
| 沙箱总时长 | 10 分钟（600 秒） |
| 依赖安装（npm/pip） | 120 秒 |

### 与降级阶梯的关系

沙箱执行在降级阶梯中的定位：

| 降级阶梯级别 | 沙箱状态 |
|------------|---------|
| 1. 真实执行 | 沙箱 **本身就是** 一种真实执行（隔离环境） |
| 2. 沙箱执行 | 沙箱可用时执行，不可用时跳到级别 3 |
| 3. 构造模拟 | 沙箱不可用或能力不足时 |
| 4. 部分执行 | 沙箱超时或资源限制时 |
| 5. 静态分析 | 最后手段 |

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
