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
