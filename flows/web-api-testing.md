# 流程 B：网页 + 接口测试

> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**

## 适用范围

当用户请求测试网页、页面、web、接口或 API 时，进入 Flow B。

## 测试目标

- 页面功能与关键用户路径
- 接口可用性、鉴权、错误处理
- 兼容性、性能、无障碍

## 模式选择

Flow B 有两种模式：

- `A 模式`：已有较完整的规格、流程或接口文档，按标准 8 阶段执行
- `B 模式`：文档不全、仅有 URL/截图，或登录/用户中心/复杂交互必须靠探索确认时，进入扩展的 11 阶段流程

进入 B 模式的常见信号：

- 只有 URL、截图或零散描述，无法直接形成稳定用例
- 需要通过真实体验补齐功能清单
- 关键路径依赖登录态、复杂状态流转或多页面交互

## 工具策略

浏览器自动化优先级：

- 默认使用 `playwright-cli`
- 需要连接用户正在使用的浏览器时使用 `chrome-cdp`
- 两者都不可用时，退化为手动测试或受限沙箱验证
- 主 agent 应在阶段零先生成 `STAGE-SUBAGENT-PLAN.json`，后续按计划启动阶段角色

详细工具模板见 `docs/references/reference-flow-web-api.md`。

## A 模式流程

| 阶段 | 执行者 | 核心输出 |
|------|--------|---------|
| 阶段零 | `roles/environment-checker.md` | 环境就绪报告 |
| 阶段一 | `roles/requirement-analyst.md` + `roles/spec-consistency-validator.md` | `PRODUCT-FINGERPRINT.json` + `SPEC.md` + `SPEC-CONSISTENCY-REVIEW.md` |
| 阶段二 | `roles/quality-assessor.md` | `PRODUCT-QUALITY-REVIEW.md` |
| 阶段三 | `roles/test-designer.md` | `TEST-DESIGN.md` + `SURFACE-EXECUTION-PLAN.json` |
| 阶段四 | `roles/test-case-evaluator.md` | `TEST-CASE-REVIEW.md` |
| 阶段五 | 并行测试角色 | `TEST-EXECUTION/*.md` |
| 阶段五后置校验 | `roles/evidence-collector.md` | `DEFECTS/evidence-collection.md` |
| 阶段六 | `roles/defect-analyst.md` | `DEFECTS/DEFECT-REPORT.md` |
| 阶段七 | `roles/report-integrator.md` | `FINAL-TEST-REPORT.md` |

并行测试角色：

- `roles/functional-tester.md`
- `roles/compatibility-tester.md`
- `roles/security-tester.md`
- `roles/performance-tester.md`
- `roles/accessibility-auditor.md`

## B 模式流程

| 阶段 | 执行者 | 核心输出 |
|------|--------|---------|
| B-阶段零 | `roles/environment-checker.md` | 环境就绪报告 |
| B-阶段一 | `roles/requirement-analyst.md` | `SPEC.md`（允许不完整） |
| B-阶段二 | `roles/quality-assessor.md` | `PRODUCT-QUALITY-REVIEW.md` + 模式判定 |
| B-阶段三 | `roles/experience-tester-a.md` + `roles/experience-tester-b.md` | `EXPERIENCE/experience-report-a.md` + `EXPERIENCE/experience-report-b.md` |
| B-阶段四 | `roles/experience-tester-a.md` + `roles/experience-tester-b.md` | `EXPERIENCE/cross-check-*.md` |
| B-阶段五 | `roles/experience-tester-a.md` + `roles/experience-tester-b.md` | 更新后的体验报告 |
| B-阶段六 | `roles/test-designer.md` | `TEST-DESIGN.md` |
| B-阶段七 | `roles/test-case-evaluator.md` | `TEST-CASE-REVIEW.md` |
| B-阶段八 | 并行测试角色 | `TEST-EXECUTION/*.md` |
| B-阶段八后置校验 | `roles/evidence-collector.md` | `DEFECTS/evidence-collection.md` |
| B-阶段九 | `roles/defect-analyst.md` | `DEFECTS/DEFECT-REPORT.md` |
| B-阶段十 | `roles/report-integrator.md` | `FINAL-TEST-REPORT.md` |

## 并行执行约束

- 阶段五和 B-阶段八的测试角色必须并行启动
- `roles/evidence-collector.md` 不参与并行，只在全部测试角色结束后执行
- 任一角色失败、超时或降级执行时，必须保留部分结果并在阶段六、阶段七显式标注未覆盖范围

## 门禁约束

- 阶段零和 B-阶段零完成后，必须等待用户确认
- 阶段二、阶段四、B-阶段二、B-阶段七结束后，必须等待批准
- 每个阶段交付物都必须单独发送，禁止合并相邻阶段输出

## 侦察优先决策树

阶段五执行前，必须按以下决策树确定每个测试目标的先侦察策略：

```text
收到测试目标（URL / API endpoint）
  │
  ├─ 是 Web 页面？
  │   ├─ 是 → 先截图 + 检查 DOM 结构 + 记录可交互元素清单
  │   │       → 根据实际 DOM 决定测试动作，不要假设元素存在
  │   └─ 否 ↓
  │
  ├─ 是 API 接口？
  │   ├─ 有文档 → 先读取文档中的请求/响应 schema，再构造测试请求
  │   ├─ 无文档 → 先发 OPTIONS/GET 探测可用方法和响应结构，再设计测试
  │   └─ 有 Swagger/OpenAPI → 优先解析 schema，避免猜测字段
  │
  └─ 不确定 → 先做最低成本探测（curl / screenshot），再决定后续策略
```

**关键规则**：
- 禁止在未侦察的情况下直接执行复杂操作（如提交表单、调用写入接口）
- 侦察结果必须记录到测试执行文件中，作为后续判定的依据
- 侦察发现与 SPEC.md / TEST-DESIGN.md 不一致时，以侦察结果为准并标注差异

## 执行原则

- 真实执行优先，禁止仅读页面或接口文档就下结论
- 页面测试需要记录关键交互、状态切换和实际页面结果
- 接口测试需要记录真实请求、响应、错误码和异常场景
- 登录、支付、用户中心、后台配置等高状态路径在文档不足时优先走 B 模式

## 参考文档

- `docs/references/reference-flow-web-api.md`：网页/接口测试细化模板
- `docs/references/reference-test-case-templates.md`：用例模板与反模式
- `docs/references/reference-report-format.md`：交付物格式
- `docs/references/reference-security-scan.md`：安全测试规则

