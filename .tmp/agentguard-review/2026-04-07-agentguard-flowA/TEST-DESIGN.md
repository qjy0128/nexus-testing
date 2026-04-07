# TEST-DESIGN.md — GoPlus AgentGuard v1.1.10

## 1. 测试范围

| 测试类型 | 覆盖内容 |
|----------|----------|
| 功能测试 | Guard.Scan() 核心扫描功能 |
| 规则测试 | 8 类风险规则有效性验证 |
| Trust Level 测试 | Block/Review/Pass 三级响应 |
| API 测试 | HTTP 接口响应正确性 |
| 安全测试 | 恶意输入检测能力 |

## 2. 测试用例设计

### 2.1 功能测试用例

| ID | 用例名称 | 输入 | 期望输出 |
|----|----------|------|----------|
| F01 | 正常输入扫描 | "Hello, how are you?" | RiskResult: [] (无风险) |
| F02 | 危险命令检测 | "rm -rf /" | RiskResult: Dangerous, Level: Block |
| F03 | 私钥泄露检测 | "0x1234...abcd" | RiskResult: Data Leak, Level: Block |
| F04 | Web3 授权检测 | "Approve token to contract" | RiskResult: Web3, Level: Review |
| F05 | 空输入处理 | "" | RiskResult: [] (空输入处理) |

### 2.2 Trust Level 测试用例

| ID | Trust Level | 输入 | 期望行为 |
|----|-------------|------|----------|
| T01 | Block | 危险命令 | 立即阻止，返回 Block |
| T02 | Review | 可疑输入 | 捕获风险，返回 Review |
| T03 | Pass | 正常输入 | 放行，返回 Pass |

### 2.3 规则测试用例

| ID | 风险分类 | 测试输入 | 期望检测 |
|----|----------|----------|----------|
| R01 | Dangerous | "sudo rm -rf" | 检测到 Dangerous |
| R02 | Data Leak | "private key: 0x..." | 检测到 Data Leak |
| R03 | Web3 | "approve ERC20 token" | 检测到 Web3 |
| R04 | Rebot | "ignore previous instructions" | 检测到 Rebot |
| R05 | Suppress | "[BLOCKED CONTENT]" | 检测到 Suppress |
| R06 | Malicious | "eval(base64_decode(...))" | 检测到 Malicious |
| R07 | Outbound | "fetch('evil.com')" | 检测到 Outbound |
| R08 | All Risk | 多类风险组合输入 | 检测到综合风险 |

### 2.4 API 测试用例

| ID | 端点 | 方法 | 期望响应 |
|----|------|------|----------|
| A01 | /api/v1/agentguard/scan | GET | 返回扫描结果 |
| A02 | /api/v1/agentguard/rules | GET | 返回规则列表 |
| A03 | /api/v1/agentguard/monitor | GET | 返回监控状态 |

## 3. 通过标准

| 指标 | 标准 |
|------|------|
| 功能测试通过率 | 100% |
| 规则检测覆盖率 | ≥ 95% |
| API 响应正确率 | 100% |
| 安全检测率 | ≥ 90% |

## 4. 测试环境

| 环境 | 要求 |
|------|------|
| Go 版本 | 1.18+ |
| 操作系统 | Windows/macOS/Linux |

---
*生成时间: 2026-04-07 18:24 GMT+8*
