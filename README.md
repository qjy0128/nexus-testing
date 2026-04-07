# Nexus Testing Framework

基于 OpenClaw 的多类型 AI 测试编排框架。系统会识别用户的测试意图，并把任务分流到 Skill、网页+接口、安卓、MCP 四类流程，按阶段零到阶段七产出结构化测试文档和 Go/No-Go 结论。

> 主入口是 [SKILL.md](SKILL.md)。共享阶段、角色、输出文件、门禁和超时基线以 [DEFINITIONS.md](DEFINITIONS.md) 为准；具体 Flow/Reference 的场景化细化按文档优先级覆盖。

## 当前状态

| Flow | 状态 | 说明 |
|------|------|------|
| Flow A（Skill 测试） | ✅ 可用 | 完整主流程，含 `live` / `shim-live` / `trace` 三层执行支持，带严格断言门禁和独立 verifier 要求 |
| Flow B（网页+接口） | ⚠️ 流程骨架 | 有角色分工和模板，无专用沙箱脚本，落地依赖浏览器/设备环境 |
| Flow C（安卓） | ⚠️ 流程骨架 | 同上，需 adb 等 Android 工具链 |
| Flow D（MCP） | ⚠️ 流程骨架 | 同上，需 MCP Server 可连接 |

### 沙箱执行能力

`auto` / `live` / `shim-live` / `trace` 四级调用控制：

- **`live`**：依赖 OpenClaw CLI，`--strict-real` 下要求 CLI 原生回传 `nexus-live-telemetry/v1` telemetry protocol。
- **`shim-live`**：依赖 Skill 提供 `testing.json` 或 `scripts/test-entry.*`；`--strict-real` 下必须携带独立 `--verification-manifest`，否则直接返回断言失败。
- **`auto --strict-real`**：当存在独立 verifier 时自动选择 `shim-live`，避免旧版 CLI 缺少 live telemetry 把本可验证的用例误判为 blocker。
- **`trace`**：仅用于静态补充分析，不能直接当成功能通过。

`sandbox-exec.sh` 支持 `--backend host-logged|container` 双后端，其中 `container` 可通过 Docker/Podman 运行容器化命令，默认断网并挂载当前 session workspace。

### 当前限制

- Flow A 已有完整的流程 + 沙箱脚本 + 严格门禁支撑。
- Flow B 目前提供编排、角色与测试模板，真实落地仍依赖浏览器自动化环境或手动执行环境。
- Flow C 目前提供编排与角色模板，真实落地依赖 adb、设备或模拟器。
- Flow D 目前提供编排与角色模板，真实落地依赖可连接的 MCP Server。

## 支持的测试类型

| 测试类型 | Flow | 关键词 | 阶段五并行角色 |
|---------|------|--------|----------------|
| Skill 测试 | Flow A | `Skill` / `skill` | 2 个：`skill-tester` + `security-tester` |
| 网页+接口测试 | Flow B | `网页` / `页面` / `web` / `接口` / `API` | 5 个：`functional` + `compatibility` + `security` + `performance` + `accessibility` |
| 安卓测试 | Flow C | `APK` / `安卓` / `android` | 5 个：`functional` + `compatibility` + `security` + `performance` + `reality-checker` |
| MCP 测试 | Flow D | `MCP` / `mcp` | 4 个：`mcp-tester` + `security` + `performance` + `reality-checker` |

系统支持在识别到多种测试类型时让用户选择串行、并行或只测其中一种。

## 工作模式

- 生成模式：从需求解析开始，完整执行阶段零到阶段七。
- 评审模式：只审查已有测试报告或文档，不触发标准测试流程。

## 标准执行流程

```text
阶段零：环境就绪检查 -> 等待用户确认
阶段一：需求解析 -> SPEC.md
阶段二：质量评估 -> PRODUCT-QUALITY-REVIEW.md -> 等待用户批准
阶段三：测试设计 -> TEST-DESIGN.md
阶段四：用例评估 -> TEST-CASE-REVIEW.md -> 等待用户批准
阶段五：并行测试执行 -> TEST-EXECUTION/*.md
阶段五后：证据收集 -> DEFECTS/evidence-collection.md
阶段六：缺陷分析 -> DEFECTS/DEFECT-REPORT.md
阶段七：报告整合 -> FINAL-TEST-REPORT.md
```

Flow B 支持双模式：
- A 模式：文档完整时走标准 8 阶段。
- B 模式：文档不全或需要深度体验时，插入双边体验、交叉核对、争议复检三个扩展阶段，总计 11 个阶段（B-阶段零~十）。

## 快速开始

1. 把这个仓库作为 OpenClaw Skill 项目打开，入口文件为 [SKILL.md](SKILL.md)。
2. 按被测对象类型准备输入：
   - Skill：源码路径或 `SKILL.md`
   - Web/API：URL、接口文档、页面截图
   - Android：`.apk` 路径
   - MCP：Server 地址、连接方式、JSON-RPC 信息
3. 让主 agent 先执行阶段零环境就绪检查，确认输出目录、依赖环境和工具能力可用。
4. 按阶段门禁推进。阶段二和阶段四必须等待用户显式批准。

## 仓库自检

```bash
python scripts/validate-framework.py        # 结构 + 语法 + 行为级 smoke test 校验
python scripts/security-scanner.py <dir>     # 安全扫描
python scripts/test_sandbox_lifecycle.py     # E2E 生命周期测试
python scripts/test_sandbox_exec_container.py # sandbox-exec 容器后端 smoke test
```

`validate-framework.py` 当前会校验：
- 核心文件、Flow 文件、沙箱脚本和治理文件是否齐全
- 所有 Markdown 本地链接是否有效
- `SKILL.md` 和 `roles/*.md` 的 frontmatter 是否完整
- `README.md` 的当前版本是否与 `CHANGELOG.md` 最新版本一致
- `.gitignore` 是否覆盖运行期产物
- Flow 文件是否保留对 `DEFINITIONS.md` 的单一事实源声明
- Python 辅助脚本是否能通过 `py_compile`
- `reference-approval-mechanism.md` 与 `DEFINITIONS.md` 的关键工件定义是否一致
- 活跃角色文档中是否混入易漂移的内联版本号
- 本地存在可用 `bash` 时，对全部沙箱脚本执行 `bash -n` 语法检查；不可用时输出警告
- Flow A runtime smoke tests（strict verifier、live telemetry、integration）

CI 也会在 GitHub Actions 中自动执行上述校验和全部 smoke tests。

## 项目结构

```text
nexus-testing/
├── SKILL.md                    # 主入口
├── DEFINITIONS.md              # 单一事实源：阶段、角色、门禁、超时
├── CHANGELOG.md                # 变更记录
├── README.md                   # 本文件
├── flows/                      # 4 个 Flow 定义
│   ├── skill-testing.md        #   Flow A — Skill 测试
│   ├── web-api-testing.md      #   Flow B — 网页+接口测试
│   ├── android-testing.md      #   Flow C — 安卓测试
│   └── mcp-testing.md          #   Flow D — MCP 测试
├── roles/                      # 19 个活跃角色
├── scripts/
│   ├── sandbox-*.sh            # 沙箱执行脚本（invoke/exec/multi-turn/...）
│   ├── sandbox_skill_invoke/   # Python 沙箱包（源码快照+安全复制）
│   ├── security-scanner.py     # 安全扫描
│   ├── validate-framework.py   # 框架结构校验
│   ├── skill-structure-validator.py
│   ├── test_sandbox_lifecycle.py
│   ├── test_sandbox_exec_container.py
│   ├── test_flow_a_*.py        # Flow A 行为级回归测试
│   └── fixtures/               # 元测试固件（pass/defect/extreme）
├── reference-*.md              # 17 个参考文档
├── archive/                    # 已归档的历史模板和 changelog
├── .github/workflows/          # CI
└── memory/nexus-reports/       # 运行期产物（不入库）
```

角色目录包含 19 个活跃角色和 1 个已归档模板（`archive/roles/compatibility-tester-skill.md`）。

## 报告输出

所有测试报告输出到 `memory/nexus-reports/{date}-{test-type}-{flow}/`，其中核心交付物包括：

- `SPEC.md`
- `PRODUCT-QUALITY-REVIEW.md`
- `TEST-DESIGN.md`
- `TEST-CASE-REVIEW.md`
- `TEST-EXECUTION/*.md`
- `DEFECTS/DEFECT-REPORT.md`
- `FINAL-TEST-REPORT.md`

更完整的目录结构和文件职责见 [DEFINITIONS.md](DEFINITIONS.md) 第三节。

## 维护约定

- 统一定义只写在 [DEFINITIONS.md](DEFINITIONS.md)，`SKILL.md`、`flows/`、`roles/` 只做引用和场景化补充。
- 运行期文件写入 `memory/nexus-reports/`、`.nexus-sandbox/`、`.tmp-test-runs/`、`.tmp-validation/` 等目录，不要把这些产物提交回仓库。
- 任何修改入口、流程、角色或参考文档后，都应先跑一次 `python scripts/validate-framework.py`。
- Shell 脚本默认按 LF 换行维护，避免在 Git Bash / Linux 环境中出现执行异常。
- 新增脚本文件需要在 `validate-framework.py` 的 `REQUIRED_*` 列表中注册。

## 参考文档一览

| 文件 | 用途 |
|------|------|
| `DEFINITIONS.md` | 阶段、角色、门禁、超时单一事实源 |
| `reference-sandbox-spec.md` | 沙箱执行环境完整规格 |
| `reference-security-scan.md` | 安全扫描规则 |
| `reference-security-blacklist.md` | 安全黑名单 |
| `reference-approval-mechanism.md` | 批准/拒绝/无响应规则 |
| `reference-recovery.md` | 测试中断后的恢复/续跑机制 |
| `reference-report-format.md` | 报告输出格式规范 |
| `reference-production-readiness.md` | 生产就绪检查清单 |
| `reference-flow-skill.md` | Flow A 详细参考 |
| `reference-flow-web-api.md` | Flow B 详细参考 |
| `reference-flow-android.md` | Flow C 详细参考 |
| `reference-flow-mcp.md` | Flow D 详细参考 |
| `reference-expected-outputs.md` | 各阶段预期输出 |
| `reference-output-verification-examples.md` | 输出验证示例 |
| `reference-test-case-templates.md` | 用例模板 |
| `reference-external-case-sourcing.md` | 外部用例来源 |
| `reference-skill-tier-requirements.md` | Skill 分层要求 |
| `reference-skill-review-framework.md` | Skill 评审框架 |
| `reference-agent-evaluation-methodology.md` | Agent 评估方法论 |

## 支持渠道

Telegram、飞书、QQ、微信。微信和 QQ 使用”先文字后文件”的降级发送策略。

## 当前版本

v0.9.24 — 详见 [CHANGELOG.md](CHANGELOG.md)
