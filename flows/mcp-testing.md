# 流程 D：MCP Server 测试

## 触发条件
用户请求测试 MCP Server（包含 "MCP"、"mcp" 关键词）

## 测试目标
验证 MCP Server 的协议合规性、工具列表完整性、JSON-RPC 调用、错误码处理、并发稳定性

## 执行步骤

### 阶段一：需求解析
**执行角色**：`roles/requirement-analyst.md`

输入：MCP Server 实现文档 / protocol spec / 源码
输出：`SPEC.md`
任务：提取工具列表、调用契约、错误码规范、协议版本

### 阶段二：质量评估（评估产品本身）
**执行角色**：`roles/quality-assessor.md`

输入：`SPEC.md`
输出：产品质量评估报告
任务：评估需求完整性、协议可行性、非功能需求
**需批准后才能进入阶段三**

### 阶段三：测试设计
**执行角色**：`roles/test-designer.md` + `roles/mcp-tester.md` 协作

输入：`SPEC.md`
输出：`TEST-DESIGN.md`
任务：设计测试用例——协议合规用例、工具调用用例、错误码测试、并发测试

### 阶段四：用例评估（评估测试用例本身）
**执行角色**：`roles/test-case-evaluator.md`

输入：`TEST-DESIGN.md` + `SPEC.md`
输出：用例评估报告
任务：评估测试用例覆盖率、边界条件覆盖、测试数据充分性
**需批准后才能进入阶段五**

### 阶段五：并行测试执行

**重要**：4 个测试工程师角色**必须并行执行**，不等待彼此。evidence-collector 独立于并行组，**在所有 subagent 全部完成后**执行一次性验证（非实时监控）。

> **执行验证标准**：统一引用 `DEFINITIONS.md` 第十节「执行验证标准」。每个测试用例必须包含真实的 JSON-RPC 请求和实际响应，禁止仅读协议文档写验证结论。

#### Step 5.1：MCP 协议测试
**执行角色**：`roles/mcp-tester.md`

输入：`SPEC.md` + MCP Server
输出：`TEST-EXECUTION/mcp-results.md`
测试内容：
- 工具列表完整性
- JSON-RPC 请求/响应格式
- 错误码合规性（基于 JSON-RPC 2.0 规范 + MCP 协议规范，详见 `roles/mcp-tester.md` 第 4 节）
- 连接/断开/重连行为

#### Step 5.2：安全测试
**执行角色**：`roles/security-tester.md`

输入：MCP Server
输出：`TEST-EXECUTION/security-results.md`
测试内容：
- 工具调用权限检查
- 注入攻击测试（JSON-RPC 参数注入）
- 数据隔离验证
- 协议层 DoS 测试（大量并发连接/超大 payload/畸形请求）
- 连接认证保护（WebSocket/SSE 认证）
- 错误信息泄露检查（详见 `roles/security-tester.md` MCP 安全测试节）

#### Step 5.3：性能测试
**执行角色**：`roles/performance-tester.md`

输入：MCP Server
输出：`TEST-EXECUTION/performance-results.md`
测试内容：
- 工具调用延迟
- 并发吞吐量
- 断连重连时间

#### Step 5.4：现实场景测试
**执行角色**：`roles/reality-checker.md`

输入：MCP Server
输出：`TEST-EXECUTION/reality-results.md`
测试内容：
- 异常输入稳定性
- 断连重连测试
- 超时处理

**证据收集**（独立角色，非并行）：
`roles/evidence-collector.md` 在阶段五所有 subagent 完成后执行一次性验证，收集证据并输出到 `DEFECTS/evidence-collection.md`

**文件发送要求**：每个角色的交付物必须单独发送，并附带内容摘要和下一步说明。

### 阶段六：缺陷分析
**执行角色**：`roles/defect-analyst.md`

输入：`TEST-EXECUTION/*.md` + `DEFECTS/evidence-collection.md`
输出：`DEFECTS/DEFECT-REPORT.md`
任务：汇总所有缺陷，去重、定级、误杀排查、漏检补充
**打回机制**：有问题 → 打回测试设计师/测试工程师重新测试 → 循环阶段五/六（最多 3 轮）

### 阶段七：报告整合
**执行角色**：`roles/report-integrator.md`

输入：所有测试结果
输出：
- `DEFECTS/DEFECT-REPORT.md`（缺陷分析师）
- `FINAL-TEST-REPORT.md`（报告整合师）
任务：缺陷定级、汇总所有问题、输出 Go/No-Go 建议
