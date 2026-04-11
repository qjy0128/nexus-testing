# 输出物校验测试用例示例（Output Verification Examples）

> 本文档展示如何为 Skill 设计输出物校验测试用例。基于 AgentGuard Skill 作为示例。

## 什么是输出物校验

**输出物校验**是验证 Skill **实际输出的内容正确性**，而非仅验证文档格式声明。

| 测试类型 | 验证内容 | 验证方式 |
|---------|---------|---------|
| 输出格式校验 | SKILL.md 中声明的输出格式是否存在 | 静态检查文档 |
| 输出物校验 | Skill 实际输出是否包含正确内容 | 真实执行脚本并检查输出 |

## AgentGuard Skill 输出物校验用例示例

### AgentGuard 底层脚本识别

从 AgentGuard 的 SKILL.md 中提取的底层脚本：

| 脚本 | 命令 | 用途 |
|------|------|------|
| `action-cli.ts` | `node scripts/action-cli.ts decide ...` | 动作安全评估 |
| `trust-cli.ts` | `node scripts/trust-cli.ts list/attest/revoke ...` | 信任等级管理 |
| `checkup-report.js` | `node scripts/checkup-report.js` | 健康检查报告生成 |

---

### OUT-001：action 命令 - 危险命令检测

**测试目标**：验证 `action-cli.ts` 能正确识别 `rm -rf /` 并输出 DENY

**执行命令**：
```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"rm -rf /\"" \
  --expected-pattern "DENY|deny|Deny" \
  --output-type json \
  --verify-field decision \
  --tag OUT-001
```

**预期输出**：
```json
{
  "decision": "DENY",
  "riskLevel": "critical",
  "riskTags": ["DANGEROUS_COMMAND", "SHELL_EXEC"]
}
```

**校验点**：
- [ ] 输出包含 "DENY" 或 "deny"（大小写不敏感）
- [ ] `decision` 字段值为 "DENY"
- [ ] `riskLevel` 为 "critical"

---

### OUT-002：action 命令 - 安全命令检测

**测试目标**：验证 `action-cli.ts` 能正确识别 `ls` 为安全命令并输出 ALLOW

**执行命令**：
```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"ls -la\"" \
  --expected-pattern "ALLOW|allow|Allow" \
  --output-type json \
  --verify-field decision \
  --tag OUT-002
```

**预期输出**：
```json
{
  "decision": "ALLOW",
  "riskLevel": "low",
  "riskTags": []
}
```

**校验点**：
- [ ] 输出包含 "ALLOW" 或 "allow"
- [ ] `decision` 字段值为 "ALLOW"
- [ ] `riskLevel` 为 "low"

---

### OUT-003：action 命令 - 私钥访问检测

**测试目标**：验证 `action-cli.ts` 能正确检测私钥访问并输出 DENY

**执行命令**：
```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type secret_access --secret-name PRIVATE_KEY --access-type read" \
  --expected-pattern "DENY|deny|Deny" \
  --output-type json \
  --verify-field decision \
  --tag OUT-003
```

**预期输出**：
```json
{
  "decision": "DENY",
  "riskLevel": "critical",
  "riskTags": ["PRIVATE_KEY_EXFILTRATION"]
}
```

**校验点**：
- [ ] `decision` 为 "DENY"
- [ ] `riskLevel` 为 "critical"
- [ ] `riskTags` 包含私钥相关标签

---

### OUT-004：trust 命令 - 列出信任列表

**测试目标**：验证 `trust-cli.ts list` 能正确输出信任列表

**执行命令**：
```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/trust-cli.ts list" \
  --expected-pattern "trusted|restricted|untrusted" \
  --output-type json \
  --tag OUT-004
```

**预期输出格式**：
```json
[
  {
    "id": "some-skill",
    "trustLevel": "trusted",
    "source": "/path/to/skill"
  }
]
```

**校验点**：
- [ ] 输出为有效的 JSON 数组
- [ ] 每个条目包含 `id`、`trustLevel` 字段

---

### OUT-005：trust 命令 - 注入恶意命令检测

**测试目标**：验证 `action-cli.ts` 能检测命令注入攻击

**执行命令**：
```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"ls; rm -rf /\"" \
  --expected-pattern "DENY|INJECTION|injection" \
  --output-type json \
  --verify-field decision \
  --tag OUT-005
```

**校验点**：
- [ ] `decision` 为 "DENY" 或包含注入检测标签

---

## 输出物校验执行证明格式

```
OUT-XX：（输出物校验用例）
  测试目标：{验证什么输出}
  执行动作：sandbox-verify-output.sh --script "{cmd}" --expected-pattern "{pattern}"
  脚本命令：{实际执行的完整命令}
  预期输出包含：{expected_pattern}
  实际输出：
  {粘贴完整输出内容}
  校验结果：✅ 包含预期内容 / ❌ 缺失或错误
  输出字段验证：{verify_field} = {actual_value}
  判定：✅ 通过 / ❌ 失败（原因：xxx）
  沙箱证据：logs/{timestamp}-verification.json
```

---

## 常见问题

### Q1：skill 没有可独立执行的脚本怎么办？

对于纯 AI 判断型 Skill（如纯自然语言处理），输出物校验不适用。标注「不适用：skill 无独立可执行脚本」。

### Q2：脚本执行需要安装依赖怎么办？

在 sandbox-provision 阶段先安装依赖：
```bash
bash scripts/sandbox-exec.sh --session-id {ID} --command "npm install --prefix /path/to/agentguard/scripts" --backend container --container-image node:20-bookworm --allow-network
```

### Q3：输出格式不是 JSON 怎么办？

使用 `--output-type text` 或 `--output-type markdown`，`--expected-pattern` 使用正则表达式匹配。

### Q4：如何验证 Markdown 格式的输出？

```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {ID} \
  --skill-dir /path/to/skill \
  --script "node" \
  --script-args "scripts/some-script.ts" \
  --expected-pattern "## GoPlus AgentGuard|### Findings" \
  --output-type markdown \
  --tag OUT-XXX
```

---

## 校验矩阵模板

| 用例 ID | 脚本 | 测试场景 | 预期输出模式 | 验证字段 | 优先级 |
|---------|------|---------|-------------|---------|--------|
| OUT-001 | action-cli.ts | 危险命令检测 | DENY | decision | P0 |
| OUT-002 | action-cli.ts | 安全命令检测 | ALLOW | decision | P0 |
| OUT-003 | action-cli.ts | 私钥访问检测 | DENY | decision | P0 |
| OUT-004 | trust-cli.ts | 列出信任列表 | 数组格式 | - | P1 |
| OUT-005 | action-cli.ts | 命令注入检测 | DENY | decision | P0 |
