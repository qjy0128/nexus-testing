# 安全扫描参考规范

> 统一安全扫描标准，吸收 skill-vetter 四阶段扫描 + OpenClaw 安全审计 + Nexus 自有检测规则。
> **security-tester 和 skill-tester 的安全扫描统一引用本文件。**

---

## 一、安全扫描概览

### 六阶段扫描架构

| 阶段 | 名称 | 检测目标 | 工具依赖 |
|------|------|---------|---------|
| S1 | 提示词注入检测 | 恶意 prompt 注入、越狱指令、系统提示提取、编码混淆 | 内置 + aguara（可选） |
| S2 | 恶意代码与漏洞检测 | 已知恶意模式、CVE、危险函数调用、可执行文件 | 内置 + skill-scanner（可选） |
| S3 | 凭证泄露检测 | 硬编码 API Key、Token、密码、Base64 隐写、OAuth 凭证 | 内置 |
| S4 | 结构与命令验证 | SKILL.md 完整性、危险 shell 命令、YAML 格式 | 内置 |
| S5 | 供应链验证 | 来源完整性、依赖链分析、安装脚本审计 | 内置 |
| S6 | 权限与访问审计 | 文件权限、网络暴露、工具沙箱策略、allowed-tools 宽泛度 | 内置 |

### 判定体系

| 判定 | 含义 | 动作 |
|------|------|------|
| ✅ SAFE | 全部扫描通过 | 允许安装/通过安全测试 |
| ⚠️ REVIEW | 存在中等级别发现 | 展示发现，由用户决定是否继续 |
| 🚫 BLOCKED | 存在高危/严重发现 | 禁止安装，必须修复后重新扫描 |

---

## 二、S1 提示词注入检测

### 检测规则

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| PI-001 | 系统提示提取尝试 | `ignore previous`、`forget your instructions`、`system prompt`、`你是一个`、`你的真实身份` | 高 |
| PI-002 | 越狱指令 | `jailbreak`、`DAN`（Do Anything Now）、`override`、`bypass` | 高 |
| PI-003 | 编码混淆 | Base64 编码的 prompt 片段、Unicode 逆序、零宽字符（U+200B-U+200F）、同形字（西里尔 к к） | 高 |
| PI-004 | 角色切换 | `pretend you are`、`act as`、`you are now`、`从现在起你是` | 高 |
| PI-005 | 输出重定向 | `output your instructions`、`print your prompt`、`显示你的系统指令`、`列出所有规则` | 高 |
| PI-006 | 注释注入 | `<!--`、`/*`、`//` 后跟指令性内容 | 中 |
| PI-007 | 多语言绕过 | 同一指令用多种语言重复（中英日韩混合注入） | 中 |
| PI-008 | 上下文污染 | 在 SKILL.md 的 description、触发条件中嵌入隐藏指令 | 高 |
| PI-009 | 分段注入 | 将恶意 prompt 分散在多个引用文件中，单个文件不明显 | 中 |

### 检测方法

1. **全文扫描**：对 SKILL.md 和所有引用的 `.md` 文件执行关键词匹配
2. **编码检测**：检测 Base64 片段（`[A-Za-z0-9+/]{40,}={0,2}`）并尝试解码
3. **零宽字符检测**：检测 U+200B-U+200F 范围内的 Unicode 字符
4. **同形字检测**：检测西里尔字母与拉丁字母混用（如 к→k, о→o, а→a）

### 外部工具集成（可选）

```bash
aguara scan "$SKILL_DIR" --format json 2>/dev/null
```

aguara 未安装时降级为内置规则扫描，不阻塞流程。

---

## 三、S2 恶意代码与漏洞检测

### S2.1 反混淆检测（Anti-Obfuscation）

> 参考 skill-security-reviewer 的 94 项检测机制，新增以下反混淆检测规则。

#### 编码混淆检测

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| OBF-001 | Base64 混淆 | `[A-Za-z0-9+/]{40,}={0,2}` 解码后为可疑内容 | 高 |
| OBF-002 | Hex 编码 | `0x[0-9a-f]+` 或仅含 `[0-9a-f]` 且偶数长度 | 中 |
| OBF-003 | Unicode 混淆 | `\u[0-9a-f]{4}`、`\x[0-9a-f]{2}`、`&#` HTML实体 | 中 |
| OBF-004 | URL 编码 | `%[0-9A-F]{2}` 重复出现（>3次） | 低 |
| OBF-005 | 零宽字符 | U+200B-U+200F 范围内的 Unicode 字符 | 高 |
| OBF-006 | 同形字混淆 | 西里尔字母与拉丁字母混用（к→k, о→o, а→a） | 高 |

#### 加密检测

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| OBF-010 | XOR 加密 | 相同长度模式重复出现、可疑 key 变量引用 | 高 |
| OBF-011 | AES/DES 加密 | 调用 `crypto`、`aes`、`des`、`cipher`、`encrypt` 模块 | 高 |
| OBF-012 | ROT13 替换 | 字母位移13位特征 | 低 |
| OBF-013 | 加密常量 | 大于20字符的 hex 字符串（可能是加密块） | 中 |

#### 熵分析规则

| 规则 ID | 检测内容 | 计算方法 | 阈值 |
|---------|---------|---------|------|
| OBF-020 | 高熵字符串 | Shannon entropy > 7.0 bits/byte | 高 |
| OBF-021 | 哈希特征 | `[0-9a-f]{32,}`（MD5/SHA系列） | 中 |
| OBF-022 | 随机填充 | Base64 字符串解码后熵 > 7.5 | 高 |

#### 字符串混淆检测

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| OBF-030 | 拼接字符串 | 多个字符串用 `+` 或 `.concat()` 连接 | 中 |
| OBF-031 | 字符码转换 | `String.fromCharCode()`、`chr()`、`\x##` | 高 |
| OBF-032 | 动态变量名 | 变量名含随机字符或数字模式 `[a-z]+[0-9]+` | 中 |
| OBF-033 | 注释隐藏代码 | 代码写在 `//` 或 `/* */` 或 `#` 注释中执行 | 高 |
| OBF-034 | 字符串反转 | `.reverse()`、`.split('').reverse().join('')` | 中 |

#### 动态代码执行检测

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| OBF-040 | eval 变体 | `eval(atob())`、`exec(base64_decode())` | 极高 |
| OBF-041 | Function 构造 | `new Function()`、`(function(){...})()` | 高 |
| OBF-042 | 延迟执行 | `setTimeout(code, 0)`、`setInterval(code, 0)` | 高 |
| OBF-043 | 动态 import | `import()`、`__import__()`、`require()` 动态拼接 | 高 |
| OBF-044 | 反射执行 | `getattr()`、`__getattribute__()`、`apply()` | 高 |
| OBF-045 | VM 沙箱 | `vm.runInNewContext()`、`vm.runInThisContext()` | 高 |

#### 反调试检测

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| OBF-050 | debugger 语句 | `debugger;`、无限循环 debugger | 中 |
| OBF-051 | 进程检测 | 检测是否在 docker/虚拟机中运行 | 中 |
| OBF-052 | 时间检测 | 调试时间差检测（两次调用时间异常） | 低 |
| OBF-053 | 控制流干扰 | `window.onerror` 覆盖、`console.log` 禁用 | 中 |

### 危险函数模式

| 函数/调用 | 风险 | 说明 |
|-----------|------|------|
| `eval()` | P0 | 动态代码执行 |
| `exec()` / `execSync()` | P0 | 命令执行 |
| `spawn()` / `execFile()` | P0 | 子进程执行 |
| `subprocess.Popen()` | P0 | Python 子进程 |
| `new Function()` | P1 | 动态函数构造 |
| `vm.runInNewContext()` | P1 | VM 沙箱逃逸 |
| `setTimeout/setInterval(fn_string, ...)` | P2 | 字符串形式的延迟执行 |
| `import()` / `require()` 动态拼接 | P1 | 动态模块加载（路径可控时） |

### 可执行文件检测

**Windows 扩展名黑名单**：
`.sh` / `.ps1` / `.bat` / `.cmd` / `.exe` / `.dll` / `.vbs` / `.scr` / `.msi` / `.reg` / `.psm1` / `.psd1` / `.cpl`

**Unix shebang 检测**：
`#!/bin/bash`、`#!/bin/sh`、`#!/usr/bin/python`、`#!/usr/bin/ruby`、`#!/usr/bin/perl`、`#!/usr/bin/node` 及任何 `#!/` 开头的解释器路径

**二进制文件头检测**：
- ELF：`0x7F 'ELF'`
- Mach-O：`0xFE 0xFA 0xED`（ARM）/ `0xFE 0xEE`（x86）
- setuid/setgid 位检测

**容器/虚拟化危险命令**：
- `docker exec`、`docker run --privileged`
- `kubectl exec`、`kubectl apply -f`
- `chroot`、`mount --bind`

### 外部工具集成（可选）

```bash
skill-scanner scan "$SKILL_DIR" --format json 2>/dev/null
```

skill-scanner 未安装时降级为内置规则扫描。

---

## 四、S3 凭证泄露检测

### 检测规则

| 规则 ID | 检测内容 | 模式 | 风险级别 |
|---------|---------|------|---------|
| CR-001 | 硬编码 API Key | `(api_key|apikey|api-key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]` | 高 |
| CR-002 | 硬编码 Token | `(token|bearer|access_token)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{20,}['\"]` | 高 |
| CR-003 | 硬编码密码 | `(password|passwd|pwd|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]` | 高 |
| CR-004 | OAuth 凭证 | `client_secret|consumer_secret|oauth_token` | 高 |
| CR-005 | 私钥内容 | `-----BEGIN (RSA |EC |DSA |OPENSSH) PRIVATE KEY-----` | 极高 |
| CR-006 | Base64 隐写 | `[A-Za-z0-9+/]{40,}={0,2}`（在 .sh/.py/.js 文件中） | 中 |
| CR-007 | 云厂商凭证 | `AKIA`（AWS）、`AIza`（GCP）、`sg_`（SendGrid）等前缀 | 高 |
| CR-008 | 连接字符串 | `mongodb://.*:.*@`、`mysql://.*:.*@`、`postgres://.*:.*@` | 高 |
| CR-009 | 环境变量泄露 | `process.env`、`os.environ` 后直接输出或记录 | 中 |

### 检测范围

- SKILL.md 及所有引用的 `.md` 文件
- `scripts/` 目录下所有脚本文件
- `package.json` / `requirements.txt` / `Gemfile` 等依赖文件
- 安装脚本（`install.sh` 等）

### 误杀排除

以下模式不算凭证泄露：
- 示例中的占位符（如 `your-api-key-here`、`<API_KEY>`、`$API_KEY`）
- 文档中说明性的模式描述
- 公开的测试 Token（如 Stripe 测试 Key `sk_test_`）

---

## 五、S4 结构与命令验证

### SKILL.md 结构检查

| 检查项 | 要求 | 风险 |
|--------|------|------|
| SKILL.md 存在 | 必须 | ❌ 缺失 = 阻断 |
| YAML frontmatter | 必须包含 `---` 开始和结束 | ⚠️ 缺失 = 警告 |
| name 字段 | 必须非空 | ❌ 缺失 = 阻断 |
| description 字段 | 必须非空且 ≥ 10 字符 | ⚠️ 过短 = 警告 |
| 引用文件存在 | 所有引用的 `.md` 文件必须存在 | ❌ 不存在 = 阻断 |

### 危险命令检测

在所有脚本和代码文件中检测以下命令模式（排除安全扫描工具自身）：

| 命令模式 | 风险 | 说明 |
|----------|------|------|
| `rm -rf` / `rm -r /` | 极高 | 递归强制删除 |
| `curl ...\| bash` / `curl ...\| sh` | 极高 | 远程代码执行 |
| `wget ...\| sh` / `wget ...\| bash` | 极高 | 远程代码执行 |
| `eval `...`` / `eval "$..."` | 高 | 动态代码执行 |
| `exec `...`` / `exec "$..."` | 高 | 命令替换执行 |
| `chmod 777` / `chmod a+rwx` | 高 | 过度权限授予 |
| `> /etc/` / `>> /etc/` | 极高 | 系统目录写入 |
| `mkfs` / `dd if=` | 极高 | 磁盘操作 |
| `:(){ :\|:& };:` | 极高 | Fork 炸弹 |
| `npm publish` / `npm install -g` | 中 | 发布/全局安装 |

---

## 六、S5 供应链验证

### 来源验证

| 检查项 | 要求 | 风险 |
|--------|------|------|
| 来源 URL 可追溯 | ClawHub / GitHub / 本地路径明确 | ❌ 无法追溯 = 警告 |
| install.sh 内容审计 | 安装脚本必须可读、无混淆 | ❌ 混淆/加密 = 阻断 |
| 依赖声明完整 | package.json / requirements.txt 声明所有依赖 | ⚠️ 未声明依赖 = 警告 |
| 依赖版本固定 | 关键依赖使用精确版本号（非范围） | ⚠️ 版本范围 = 警告 |

### 安装脚本审计

**必须检查**：
1. 安装脚本是否下载并执行额外代码（curl|bash 模式）
2. 安装路径是否写入敏感系统目录（/etc、/usr、/System32）
3. 是否修改系统配置（crontab、systemctl、launchd、注册表）
4. 是否创建网络监听（nc -l、socat、socket 绑定）
5. 是否修改 PATH 或其他环境变量
6. 安装后是否保留清理机制（卸载能力）

### 依赖链分析

| 检查项 | 风险 |
|--------|------|
| 依赖包名含混淆字符（如 `lI0l`、`n₀de`） | 高 |
| 依赖包名与知名包相似但不完全相同（typosquatting） | 高 |
| 安装来源为非官方 registry | 中 |
| postinstall 钩子中执行脚本 | 高 |

---

## 七、S6 权限与访问审计

### 文件权限

| 检查项 | 正常值 | 风险 |
|--------|--------|------|
| SKILL 目录权限 | 755 (owner rwx) | ❌ world-writable = 阻断 |
| SKILL.md 权限 | 644 (owner rw) | ❌ world-writable = 阻断 |
| 脚本文件权限 | 755 或 644 | ❌ setuid/setgid = 阻断 |
| 配置文件权限 | 600 或 640 | ❌ world-readable 且含凭证 = 阻断 |

### 网络暴露

| 检查项 | 风险 |
|--------|------|
| Skill 内含 `0.0.0.0` 或 `::` 绑定 | 极高 |
| Skill 内含反向 shell（nc -e、bash -i >&） | 极高 |
| Skill 主动外联到非服务域名 | 中 |
| Skill 使用 DNS 隧道或 ICMP 隧道 | 极高 |

### allowed-tools 宽泛度审计

| 模式 | 风险 | 说明 |
|------|------|------|
| `Bash(*)` | 极高 | 完全无限制的 Bash 访问 |
| `Bash(node *)` | 极高 | 可执行任意 node 脚本 |
| `Bash(npm *)` | 极高 | 可执行任意 npm 命令 |
| `Bash(curl *)` | 高 | 可发起任意 HTTP 请求 |
| `Bash(wget *)` | 高 | 可下载任意文件 |
| `Bash(find *)` | 高 | 可遍历任意路径 |
| `Bash(cat *)` | 中 | 可读取任意文件 |
| `Read` 无路径限制 | 高 | 可读取任意文件 |
| `Write` 无路径限制 | 极高 | 可写入任意文件 |
| `Edit` 无路径限制 | 极高 | 可修改任意文件 |

---

## 八、外部扫描器集成

### aguara（提示词注入检测）

- **安装**：`go install github.com/garagon/aguara/cmd/aguara@latest`
- **调用**：`aguara scan "$SKILL_DIR" --format json`
- **输出**：JSON 格式的 findings 数组，每个 finding 含 severity（1-5）、rule_id、description、file_path、line
- **降级**：未安装时使用本文件 S1 内置规则替代

### skill-scanner（Cisco AI 漏洞扫描）

- **安装**：`pip install cisco-ai-skill-scanner`
- **调用**：`skill-scanner scan "$SKILL_DIR" --format json`
- **输出**：JSON 格式的 severity（critical/high/medium/low/none）和 description
- **降级**：未安装时使用本文件 S2 内置规则替代

### 集成原则

1. 外部工具**可选**，不阻塞核心流程
2. 内置规则是**最低保障**，外部工具是增强
3. 所有扫描结果统一汇总到 verdict 判定
4. 工具缺失时明确标注「降级扫描」

---

## 九、攻击链检测矩阵（Attack Chain Detection）

> 参考 guardskills 的攻击链检测机制。当多个相关发现同时出现时，触发链式加成，表示组合攻击策略。

### 链式发现类型

| 发现类型 | 缩写 | 说明 |
|----------|------|------|
| `SECRET_READ` | SR | 读取敏感文件或凭证源 |
| `NETWORK_POST` | NP | 外部网络请求 |
| `DECODE_EXEC` | DE | 解码/解混淆后执行 |
| `REMOTE_CODE_EXEC` | RCE | 远程代码执行 |
| `ENV_ACCESS` | EA | 环境变量访问 |
| `FILE_STAGE` | FS | 临时文件写入 |
| `DESTRUCTIVE_OP` | DO | 破坏性操作 |
| `PRIV_ESCALATION` | PE | 权限提升 |

### 攻击链矩阵

| Chain ID | 必需发现组合 | 加成分值 | 攻击意图 |
|----------|-------------|---------|----------|
| `CHAIN_SECRET_EXFIL` | `SECRET_READ` + `NETWORK_POST` | +25 | 凭证/数据窃取 |
| `CHAIN_DECODE_EXEC` | `DECODE_EXEC` + `REMOTE_CODE_EXEC` | +30 | 混淆载荷执行 |
| `CHAIN_ENV_STAGE_EXFIL` | `ENV_ACCESS` + `FILE_STAGE` + `NETWORK_POST` | +20 | 环境信息窃取 |
| `CHAIN_DESTRUCTIVE_EXFIL` | `DESTRUCTIVE_OP` + `NETWORK_POST` | +25 | 破坏后数据外传 |
| `CHAIN_PRIV_ESC_RCE` | `PRIV_ESCALATION` + `REMOTE_CODE_EXEC` | +35 | 权限提升后执行 |
| `CHAIN_DOWNLOAD_EXEC` | `FILE_STAGE` + `REMOTE_CODE_EXEC` | +20 | 下载并执行 |

### 链式检测执行证明格式

```
SEC-CHAIN-XXX：（攻击链名称）
  Chain ID：{CHAIN_XXX}
  检测到的发现：
    - {发现类型1}：{位置}
    - {发现类型2}：{位置}
  链式加成：+{分数}
  攻击意图：{描述}
  风险评级：{CRITICAL/HIGH/MEDIUM/LOW}
```

---

## 十、量化风险评分系统

### 风险评分公式

```
风险分 = clamp(Σ(基础分 × 置信度) + 链式加成 - 信任积分, 0, 100)
```

### 基础分（Base Points）

| 严重级别 | 基础分 |
|----------|--------|
| `CRITICAL` | 50 |
| `HIGH` | 25 |
| `MEDIUM` | 12 |
| `LOW` | 5 |
| `INFO` | 0 |

### 置信度乘法器（Confidence Multipliers）

| 置信度 | 乘法器 |
|--------|--------|
| `high` | 1.0 |
| `medium` | 0.7 |
| `low` | 0.4 |

### 信任积分（Trust Credits）

- 仅在无 `HIGH`/`CRITICAL` 发现时授予
- 上限：`20` 分

### 判定阈值

| 模式 | 0-29 | 30-59 | 60-79 | 80-100 |
|------|------|-------|-------|--------|
| **Standard** | ✅ SAFE | ⚠️ WARNING | 🔴 UNSAFE | 🚫 CRITICAL |
| **Strict** | ✅ SAFE | ⚠️ WARNING | 🔴 UNSAFE | 🚫 CRITICAL |

Strict 模式阈值下移 10 分。

### 分数计算示例

```
发现1: CRITICAL (50) × high (1.0) = 50
发现2: HIGH (25) × medium (0.7) = 17.5
链式加成: CHAIN_DECODE_EXEC (+30)
-----------------
原始分: 50 + 17.5 + 30 = 97.5
最终分: clamp(97.5, 0, 100) = 97.5 → CRITICAL
```

---

## 十一、硬阻断策略（Hard-Block Policy）

> 只有同时满足所有条件时，才触发硬阻断（无条件阻止安装/通过测试）。

### 硬阻断触发条件（必须同时满足）

| 条件 | 要求 |
|------|------|
| 严重级别 | `CRITICAL` |
| 置信度 | `high` |
| 发现类型 | 以下之一：`CREDENTIAL_EXFIL`、`DESTRUCTIVE_OP`、`REMOTE_CODE_EXEC`、`PRIV_ESCALATION` |

### 可硬阻断的类型定义

| 类型 | 描述 | 示例规则 |
|------|------|----------|
| `CREDENTIAL_EXFIL` | 凭证窃取外传 | R001（读取凭证+网络发送） |
| `DESTRUCTIVE_OP` | 破坏性操作 | R003（rm -rf /） |
| `REMOTE_CODE_EXEC` | 远程代码执行 | R002（curl|pipe bash）、R011（PowerShell下载执行） |
| `PRIV_ESCALATION` | 权限提升 | R004（sudo 滥用） |

### 硬阻断执行证明格式

```
SEC-BLOCK-XXX：（阻断项）
  阻断原因：{类型} + {严重级别} + {置信度}
  发现详情：
    - 规则ID：{RXXX}
    - 位置：{文件:行号}
    - 匹配内容：{代码片段}
  硬阻断触发：CRITICAL + high + {类型} = TRUE
  判定结果：🚫 BLOCKED
```

---

## 十二、扫描报告格式

```
════════════════════════════════════════════════════════════
SECURITY SCAN — {Skill 名称}
Path: {SKILL_DIR}
Scanners: {已安装的扫描器列表}
════════════════════════════════════════════════════════════

[S1] 提示词注入........... ✅ PASS / ❌ FAIL (X high) / ⚠️ WARN (X medium)
[S2] 恶意代码............. ✅ PASS / ❌ FAIL (X high) / ⚠️ WARN (X medium)
[S3] 凭证泄露............. ✅ PASS / ❌ FAIL (X high) / ⚠️ WARN (X medium)
[S4] 结构与命令........... ✅ PASS / ❌ FAIL (X high) / ⚠️ WARN (X medium)
[S5] 供应链验证........... ✅ PASS / ❌ FAIL (X high) / ⚠️ WARN (X medium)
[S6] 权限与访问........... ✅ PASS / ❌ FAIL (X high) / ⚠️ WARN (X medium)

════════════════════════════════════════════════════════════
RISK SCORE: {0-100} ({SAFE/WARNING/UNSAFE/CRITICAL})
Chain Bonuses: +{分数}
════════════════════════════════════════════════════════════
VERDICT: 🚫 BLOCKED / ⚠️ REVIEW / ✅ SAFE
Reasons: X HIGH, Y MEDIUM
════════════════════════════════════════════════════════════

详细发现：
[S1] PI-003: Base64 encoded prompt in scripts/run.sh:12
[S3] CR-001: Hardcoded API key in SKILL.md:47
...
```
