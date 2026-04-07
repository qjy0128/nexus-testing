# SPEC.md — GoPlus AgentGuard v1.1.10

## 1. 项目概述

| 字段 | 内容 |
|------|------|
| **名称** | GoPlus AgentGuard |
| **版本** | v1.1.10 |
| **类型** | Security Skill（AI Agent 安全检测） |
| **描述** | 检测 AI Agent 运行时的安全风险，支持 8 类风险分类、240+ 检测规则 |
| **许可证** | Apache-2.0 |

## 2. 核心规格

### 2.1 风险分类（8 大类）

| ID | 分类 | 规则数 | 说明 |
|----|------|--------|------|
| R1 | Dangerous | 20 | 危险操作 |
| R2 | Data Leak | 16 | 数据泄露 |
| R3 | Web3 | 27 | Web3 安全 |
| R4 | Rebot | 18 | 机器人检测 |
| R5 | Suppress | 11 | 内容抑制 |
| R6 | Malicious | 14 | 恶意代码 |
| R7 | Outbound | 14 | 出站风险 |
| R8 | All Risk | 120+ | 综合风险 |

### 2.2 Trust Level

| Level | 含义 |
|-------|------|
| Block | 直接阻止，终止执行 |
| Review | 捕获风险，提交人工审核 |
| Pass | 放行，无风险 |

### 2.3 核心流程

```
用户输入 → Guard.Scan() → 规则匹配 → RiskResult[]
```

### 2.4 覆盖场景

- Prompt 注入检测
- 密钥/私钥泄露检测
- Web3 风险（合约代币授权）
- DApp 安全交互
- 恶意指令检测

## 3. 交付清单

- [x] SKILL.md - 技能入口
- [x] action-policies.md - 行为策略（15项）
- [x] scan-rules.md - 扫描规则（8类）
- [x] patrol-checks.md - 巡检项（11项）
- [x] README.md - 使用文档
- [x] web3-patterns.md - Web3 风险模式

## 4. 技术规格

- **语言**：Go 1.18+
- **部署方式**：Go library
- **核心模块**：Guard, Scanner, Rules

---
*生成时间: 2026-04-07 18:21 GMT+8*
