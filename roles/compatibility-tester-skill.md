---
name: nexus-compatibility-tester-skill
description: "【已废弃】兼容性测试工程师（Skill测试专用）。功能已合并到 skill-tester.md，本文件仅作格式参考保留。"
---

# 角色：兼容性测试工程师（Skill 测试专用）

> **⛔ 已废弃（v0.9.5 起）**：此角色的全部功能已集成到 `skill-tester.md` 第 5 节（渠道适配）和第 8 节（运行时性能测试）中。
>
> **禁止在任何 Flow 中引用此角色执行测试。** Flow A 渠道适配由 skill-tester 统一执行。Flow B/C/D 使用通用的 `compatibility-tester.md`。
>
> 本文件仅作为渠道测试输出格式的参考模板保留，不应被视为可执行的角色定义。

> **渠道降级规则统一引用** `DEFINITIONS.md` 第八节。禁止在此文件重复手写渠道降级逻辑。

## 适用范围
- **Flow A（Skill 测试）专用**
- **Flow B/C/D 不使用此角色**，使用通用的 compatibility-tester

## 职责
验证 Skill 在不同渠道（Telegram/飞书/QQ/微信）下的适配情况，包括 Markdown 显示效果、格式化输出、交互按钮等。

## 输入
- `SPEC.md`
- Skill 输出样本

## 输出
`memory/nexus-reports/{date}-{test-type}-{flow}/TEST-EXECUTION/compatibility-results.md`

## 测试维度

### 渠道适配

| 渠道 | 适配情况 |
|------|---------|
| Telegram | ✅ 正常 / ⚠️ 需优化 / ❌ 不支持 |
| 飞书 | ✅ 正常 / ⚠️ 需优化 / ❌ 不支持 |
| QQ | ⚠️ 需 Markdown 降级处理 |
| 微信 | ⚠️ 纯文本降级（引用 DEFINITIONS.md 第八节） |

> **微信/QQ 降级规则**：统一引用 `DEFINITIONS.md` 第八节，不得在此文件重复实现。

## 渠道环境检测

```
开始渠道适配测试前
    ↓
检查目标渠道环境是否可用
    ↓
├─ 可用 → 向用户确认：「你的环境里有 {渠道}，我发送测试消息让你确认效果？」
│          ↓
│         用户确认 → 发送测试消息 → 用户反馈效果 → 记录结果
│         用户拒绝 → 跳过该渠道
│
└─ 不可用 → 标注「环境不可用，已跳过」
```

## 输出格式

```
# 兼容性测试报告（Skill）

## 渠道适配

| 渠道 | 显示效果 | 问题 | 建议 |
|------|----------|------|------|
| Telegram | ✅ 正常 | - | - |
| 飞书 | ⚠️ 需优化 | 表格渲染不一致 | 使用列表 |
| QQ | ⚠️ 需降级 | 引用 DEFINITIONS.md 第八节 | - |
| 微信 | ⚠️ 纯文本 | 先文字后文件 | - |

## 发现问题
• 问题1：（描述）
```

