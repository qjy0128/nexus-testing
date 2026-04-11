# Expected Outputs 验证机制

> 本文档说明如何使用 `expected_outputs/` 目录进行 Skill 输出物校验。

## 概念

**Expected Outputs** 是 OpenClaw skill-tester 采用的输出校验方法：
- 被测 Skill 的每个可执行脚本对应一个预期输出目录
- 目录内存放多个校验文件（精确匹配、模式匹配、包含检查）
- 测试时对比实际输出与预期输出，报告差异

这解决了之前的问题：**只验证格式不验证内容**。

---

## 目录结构

```
expected_outputs/
└── {script-name}/              # 脚本名称（不含扩展名）
    └── {args-hash}/             # 参数的 MD5 哈希
        ├── expected.txt         # 精确匹配（可选）
        ├── patterns.txt         # 正则模式（可选）
        └── contains.txt         # 必须包含的字符串（可选）
```

### 文件说明

| 文件 | 用途 | 示例 |
|------|------|------|
| `expected.txt` | 精确匹配 | 输出必须与文件内容完全一致 |
| `patterns.txt` | 正则模式 | 每行是一个正则，输出必须匹配所有模式 |
| `contains.txt` | 字符串包含 | 每行是一个子串，输出必须包含所有子串 |

### 示例结构

```
expected_outputs/
└── action-cli/
    └── a1b2c3d4/
        ├── expected.txt      # {"decision": "DENY", ...}
        ├── patterns.txt     # "DENY"
                              # "critical"
        └── contains.txt     # "riskTags"
                              # "DANGEROUS_COMMAND"
```

---

## 使用方式

### 方式 1：使用 --expected-dir（推荐）

自动查找对应目录并执行所有校验：

```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"rm -rf /\"" \
  --expected-dir /path/to/expected_outputs/ \
  --tag OUT-001
```

### 方式 2：使用 --expected-file

对比单个预期文件：

```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"rm -rf /\"" \
  --expected-file /path/to/expected_outputs/action-cli/a1b2c3d4/expected.txt \
  --compare-mode strict \
  --tag OUT-002
```

### 方式 3：使用 --expected-pattern

只检查是否包含特定模式：

```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"rm -rf /\"" \
  --expected-pattern "DENY|decision.*deny" \
  --tag OUT-003
```

---

## 对比模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `strict` | 精确匹配 expected.txt | 输出固定不变的脚本 |
| `pattern` | 匹配 patterns.txt 中所有正则 | 输出包含动态数据（时间戳等） |
| `contains` | 包含 contains.txt 中所有字符串 | 输出部分固定，部分动态 |

---

## 生成 expected_outputs 目录

### 手动创建

```bash
# 创建目录结构
mkdir -p expected_outputs/action-cli

# 运行脚本获取实际输出
ACTUAL_OUTPUT=$(node scripts/action-cli.ts decide --type exec_command --command "rm -rf /")

# 保存为 expected.txt
echo "$ACTUAL_OUTPUT" > expected_outputs/action-cli/$(echo -n "decide --type exec_command --command rm -rf /" | md5sum | cut -d' ' -f1)/expected.txt
```

### 使用脚本自动生成（推荐）

```bash
# 当前没有内置自动生成器，建议先手动建立 expected_outputs 目录结构
mkdir -p /path/to/skill/expected_outputs/action-cli
```

---

## 在 TEST-DESIGN.md 中使用

```markdown
### OUT-001：action 命令 - 危险命令检测

• capability-id：CAP-01
• test-dimension：TD-02
• 执行环境：sandbox
• 预期输出目录：expected_outputs/action-cli/

**执行动作**：
```bash
bash scripts/sandbox-verify-output.sh \
  --session-id {SESSION_ID} \
  --skill-dir /path/to/agentguard \
  --script "node" \
  --script-args "scripts/action-cli.ts decide --type exec_command --command \"rm -rf /\"" \
  --expected-dir /path/to/expected_outputs/
```

**预期结果**：
- patterns.txt 中所有正则匹配成功
- contains.txt 中所有字符串存在
- 输出物校验：✅ 通过
```

---

## 局限性

1. **Args Hash 冲突**：不同参数可能产生相同哈希（概率极低）
2. **大输出**：如果输出非常大，expected.txt 会占用大量空间
3. **动态内容**：时间戳、UUID 等动态数据需要用 pattern 模式

---

## 与 OpenClaw 的区别

| 特性 | OpenClaw skill-tester | Nexus Testing |
|------|----------------------|--------------|
| 校验文件格式 | JSON + human-readable | 纯文本 |
| 对比方式 | 运行时传入 | 目录自动查找 |
| 多脚本支持 | 手动指定 | 自动发现 |
| Sandbox 集成 | 无 | 完全集成 |
