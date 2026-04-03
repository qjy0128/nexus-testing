# 流程 A：OpenClaw Skill 测试

> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**

## 触发条件
用户请求测试一个 OpenClaw Skill（包含 "skill" 关键词）

## 测试目标
验证 Skill 的：触发条件、工具调用、输出格式、错误处理、跨渠道适配

## 执行步骤

### 阶段零：环境就绪检查
**执行角色**：主 agent

输入：Skill 源码路径 / SKILL.md
输出：环境就绪报告（内存中）
任务：
- 基础检查：Skill 源码路径存在性、SKILL.md 可读性、YAML frontmatter 完整性
- **依赖环境检测**：扫描 SKILL.md 和 Skill 源码，识别并验证所需的运行时依赖（npm/Python/其他 OpenClaw 插件/系统命令），详见 `SKILL.md` 阶段零「Flow A 依赖环境检测」
- 通用检查：输出目录可写性、渠道配置

> **注意**：OpenClaw 环境本身假定已就绪，不作为检测项。仅检测被测 Skill 额外依赖的运行时环境。

**需用户确认后才能进入阶段一**

### 阶段一：需求解析
**执行角色**：`roles/requirement-analyst.md`

输入：Skill 的 SKILL.md 文件路径或内容
输出：`SPEC.md`
任务：提取 Skill 的触发条件、工具列表、输入输出规范、边界行为

### 阶段二：质量评估（评估产品本身）
**执行角色**：`roles/quality-assessor.md`

输入：`SPEC.md`
输出：产品质量评估报告
任务：评估 SKILL.md 编写质量、Agent 执行流畅度、内容缺失提示、多渠道适配、Token 消耗、安全策略合规
**需批准后才能进入阶段三**

### 阶段三：测试设计
**执行角色**：`roles/test-designer.md`

输入：`SPEC.md`
输出：`TEST-DESIGN.md`
任务：设计测试用例——触发条件用例、工具调用验证、输出格式校验、错误处理、边界值测试

### 阶段四：用例评估（评估测试用例本身）
**执行角色**：`roles/test-case-evaluator.md`

输入：`TEST-DESIGN.md` + `SPEC.md`
输出：用例评估报告
任务：评估测试用例覆盖率（≥80%通过）、边界条件覆盖、测试数据充分性
**需批准后才能进入阶段五**

### 阶段五：并行测试执行

**重要**：每个角色必须独立执行并输出各自的交付物，禁止合并。发送文件时优先使用 caption；平台不支持时，必须随文件附带摘要说明。

> **执行验证标准**：统一引用 `DEFINITIONS.md` 第十节「执行验证标准」。每个测试用例必须包含真实的执行动作和实际输出，禁止仅读文档写验证结论。

**Flow A 并行角色（与主 SKILL.md 保持一致，共 2 个）**：
- `roles/skill-tester.md`（Skill 核心功能测试 + 运行时性能测试）
- `roles/security-tester.md`（安全与 Token 测试）

> **说明**：Flow A 不设独立 performance-tester，运行时性能测试（Token 消耗、响应延迟、Token 爆炸检测）已集成在 skill-tester 中。

#### Step 5.1：Skill 核心功能测试
**执行角色**：`roles/skill-tester.md`

输入：`SPEC.md` + `TEST-DESIGN.md` + Skill 源码
输出：`TEST-EXECUTION/skill-results.md`
测试内容：
- SKILL.md YAML frontmatter 语法验证
- name/description 规范性检查
- 触发条件测试（正向+逆向）
- 工具调用验证（使用 skill 声明的工具）
- 输出格式校验
- 错误处理测试
- 跨渠道适配检测（集成在 skill-tester 内，不单独拆分）

#### Step 5.2：安全与 Token 测试
**执行角色**：`roles/security-tester.md`

输入：Skill 源码 + 测试执行日志
输出：`TEST-EXECUTION/security-results.md`
测试内容：
- 高危工具调用检测
- 提示词注入风险
- Token 消耗评估

#### 阶段五后：证据收集
**执行角色**：`roles/evidence-collector.md`

所有 subagent 完成后的独立步骤，收集阶段五所有缺陷证据
输出：`DEFECTS/evidence-collection.md`

**文件发送要求**：每个角色的交付物必须单独发送，并附带内容摘要和下一步说明。

### 阶段六：缺陷分析
**执行角色**：`roles/defect-analyst.md`

输入：`TEST-EXECUTION/*.md` + `DEFECTS/evidence-collection.md`
输出：`DEFECTS/DEFECT-REPORT.md`
任务：汇总所有缺陷，去重、定级、误杀排查、漏检补充
**打回机制**：有问题 → 打回测试设计师/测试工程师重新测试 → 循环阶段五/六（最多 3 轮）

### 阶段七：报告整合
**执行角色**：`roles/report-integrator.md`

输入：所有测试结果（`DEFECTS/DEFECT-REPORT.md` + 各 TEST-EXECUTION/*.md）
输出：`FINAL-TEST-REPORT.md`
任务：缺陷定级（P0-P3）、汇总所有问题、输出 Go/No-Go 建议
