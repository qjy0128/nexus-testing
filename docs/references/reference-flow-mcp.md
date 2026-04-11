# Flow D（MCP 测试）详细模板参考

> 本文件供 MCP Server 测试时查阅，补充 SKILL.md 和 mcp-testing.md 中的详细格式要求。

---

## 一、MCP 接口测试用例模板

### 1.1 工具调用测试

| 用例 ID | 工具名 | 输入参数 | 预期结果 | 优先级 |
|---------|--------|---------|---------|--------|
| TC-MCP-01 | `tool_name` | `{valid params}` | 返回正确结果 | P0 |
| TC-MCP-02 | `tool_name` | `{empty params}` | 报错或默认值 | P0 |
| TC-MCP-03 | `tool_name` | `{invalid params}` | 明确错误信息 | P0 |

### 1.2 JSON-RPC 协议测试

| 用例 ID | 场景 | 请求 | 预期响应 | 优先级 |
|---------|------|------|---------|--------|
| TC-PROTO-01 | 正常调用 | `{jsonrpc: "2.0", method: "...", id: 1}` | `{jsonrpc: "2.0", result: ..., id: 1}` | P0 |
| TC-PROTO-02 | 无效 method | `{jsonrpc: "2.0", method: "invalid", id: 1}` | `{jsonrpc: "2.0", error: ..., id: 1}` | P0 |
| TC-PROTO-03 | 缺少 id | `{jsonrpc: "2.0", method: "..."}` | `-32700 Invalid Request` | P1 |

### 1.3 连接与认证测试

| 用例 ID | 场景 | 预期结果 | 优先级 |
|---------|------|---------|--------|
| TC-CONN-01 | 正常连接 | 连接成功 | P0 |
| TC-CONN-02 | 错误地址 | 连接失败+错误提示 | P0 |
| TC-CONN-03 | 无效 token | 认证失败 401 | P0 |

---

## 二、性能测试参考值

| 指标 | 目标值 | 告警阈值 |
|------|--------|---------|
| 工具调用响应时间（p95） | < 2000ms | > 5000ms |
| 并发连接数 | ≥ 10 | - |
| 错误率 | < 1% | > 5% |

---

## 三、Flow D 阶段产出清单

| 阶段 | 文件名 | 必填字段 |
|------|--------|---------|
| 阶段一 | `SPEC.md` | MCP Server 地址、工具列表 |
| 阶段二 | `PRODUCT-QUALITY-REVIEW.md` | 风险评估 |
| 阶段三 | `TEST-DESIGN.md` | 用例清单 |
| 阶段四 | `TEST-CASE-REVIEW.md` | 覆盖率 |
| 阶段五 | `TEST-EXECUTION/mcp-results.md` | 工具调用结果 |
| 阶段五 | `TEST-EXECUTION/security-results.md` | 安全检测 |
| 阶段五 | `TEST-EXECUTION/performance-results.md` | 性能数据 |
| 阶段五 | `TEST-EXECUTION/reality-results.md` | 真实验证 |
| 阶段六 | `DEFECTS/DEFECT-REPORT.md` | 缺陷清单 |
| 阶段七 | `FINAL-TEST-REPORT.md` | Go/No-Go 判定 |
