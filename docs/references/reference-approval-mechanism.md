# 批准机制详细规范

> 本文件定义阶段二和阶段四的批准、拒绝、阶段回退入口、无响应处理与拒绝计数持久化规则。阶段门禁本身仍以 `DEFINITIONS.md` 为准。

---

## 一、适用范围

- 阶段二：质量评估完成后，进入阶段三前
- 阶段四：用例评估完成后，进入阶段五前

任何平台下都必须显式请求批准。支持按钮时优先使用按钮；不支持时退化为明确文本批准。

---

## 二、标准流程

```text
阶段二/四角色 subagent 完成
    ↓
主 agent 接收交付物
    ↓
发送交付物 + 批准请求
    ↓
写入 approval-records.json
    ↓
等待用户批准 / 拒绝 / 继续等待
    ↓
更新记录
    ↓
批准 → 进入下一阶段
拒绝 → 终止当前阶段，并由主 agent 重新进入指定前置阶段
无响应超时 → 自动继续并留痕
```

硬规则：

- “阶段完成”默认包含“交付物已发送”；只写文件未发送，不算完成
- 阶段角色 subagent 只负责产出交付物；发送交付物与发起批准请求由主 agent 负责
- 交付物发送与批准请求必须同轮触发；不能先说“已完成”再等待用户索要文件
- 若用户追问文件，按漏发处理：立即补发交付物，并保持当前批准状态不变
- 发送前若交付物还在 `memory/...`，必须先通过 `python scripts/prepare_report_delivery.py --report-file <memory-report-file>` 镜像到 `files/...` 再发
- 若平台拒绝文件发送，优先重试 `files/...` 中转路径；仍失败时要在同轮消息里明确给出工作区文件路径

**禁止行为**

- 发送交付物后不发批准请求，直接推进下一阶段
- 用模糊措辞代替明确的批准动作
- 在收到批准前提前生成下一阶段交付物
- 将两个阶段的交付物合并到一条消息中发送

---

## 三、批准记录文件

每次发起批准请求后，必须写入 `memory/nexus-reports/{date}-{test-type}-{flow}/approval-records.json`。

```json
{
  "phase_2": {
    "transport": "button",
    "interaction_id": "msg-123",
    "sent_at": "YYYY-MM-DD HH:mm:ss",
    "user_response": null,
    "response_at": null
  },
  "phase_4": {
    "transport": "text",
    "interaction_id": null,
    "sent_at": "YYYY-MM-DD HH:mm:ss",
    "user_response": null,
    "response_at": null
  }
}
```

字段说明：

- `transport`：`button` 或 `text`
- `interaction_id`：平台返回的消息 ID、交互 token，拿不到时可为 `null`
- `sent_at`：发起批准请求时间
- `user_response`：`approved`、`rejected`、`wait` 或 `auto-continue`
- `response_at`：收到有效响应的时间
- 实现层可额外写入 `waiting_since`、`reminder_count`、`last_reminder_at`、`reminder_history`，用于无响应催复与自动继续，不影响基础兼容性

---

## 四、拒绝计数持久化

每个需批准阶段最多拒绝 3 次。拒绝计数写入 `rejection-count.json`。

```json
{
  "phase": 2,
  "count": 1,
  "last_rejection": "YYYY-MM-DD HH:mm:ss",
  "last_reason": "需求边界不清，无法进入测试设计"
}
```

规则：

- 同一阶段每次被拒绝都必须更新 `count`
- 用户批准通过后，该阶段拒绝计数归零
- Session 重启后从文件恢复，避免通过重启绕过限制
- 读取失败时按“未知状态”处理，禁止直接推进

---

## 五、阶段回退入口

| 被拒绝阶段 | 重新进入阶段 | 说明 |
|-----------|--------|------|
| 阶段二 | 阶段一 | 终止当前评估结论，重新生成需求/规格交付物 |
| 阶段四 | 阶段三 | 终止当前用例评审结论，重新生成测试设计交付物 |

阶段回退规则：

- 阶段回退必须附带理由，长度不少于 10 个字符
- 无理由或理由过短时，提示用户补充原因，不执行阶段回退
- 每次阶段回退都要在 `rejection-count.json` 和拒绝记录中留痕

建议记录格式：

```text
【拒绝记录 #1】
阶段：阶段二
原因：需求边界仍不完整，缺少核心输入输出约束
重新进入阶段：阶段一
时间：YYYY-MM-DD HH:mm:ss
```

---

## 六、无响应处理

| 等待时长 | 动作 |
|---------|------|
| 0 分钟 | 发起批准请求 |
| 10 分钟 | 第 1 次催复 |
| 20 分钟 | 第 2 次催复 |
| 30 分钟 | 第 3 次催复后仍无响应，自动继续 |

催复文案应保持明确：

```text
阶段四已完成，等待你的批准。10 分钟后自动继续，如需暂停请直接回复。
```

自动继续时必须：

- 更新 `approval-records.json` 为 `user_response: "auto-continue"`
- 明确告知用户“因无响应已自动继续”
- 在后续报告中保留该自动推进记录

CLI 对账约束：

- `nexus_stage_executor.py process-approval-timeout` 负责把当前审批门对账到结构化状态：10/20 分钟补记 `approval-reminder`，30 分钟写入 `auto-continue`
- `run_openclaw_stage_demo.py` 的 `start` / `continue` / `recover` / `detect-existing` 应在读取当前 gate 前先做一次 timeout 对账，避免 session 重启后丢失无响应推进

---

## 七、响应解析

按以下规则解析用户回应：

- 批准：按钮批准，或文本 `批准` / `approve` / `yes` / `y`
- 拒绝：按钮拒绝，或文本 `拒绝` / `reject` / `no` / `n`
- 继续等待：文本 `继续等待`
- 重复批准：提示“该阶段已批准，无需重复确认”

收到有效响应后立即更新 `approval-records.json`，并按阶段门禁执行后续动作。

---

## 八、自动 No-Go

同一阶段拒绝计数达到 3 次时，流程自动终止并标记为 No-Go。

```text
【测试流程终止】
阶段四已连续拒绝 3 次，自动标记为 No-Go。
原因：{最后一次拒绝理由}
建议：修复上一阶段输出后重新开始测试流程。
```

---

## 九、实现约束

- 本文件只定义批准机制，不重复定义阶段编号、门禁顺序、目录结构
- 当前规范不要求额外签名字段；批准与拒绝状态以结构化记录和审计日志为准
- 如平台支持消息 ID 或交互 token，应写入记录；不支持时允许为空
