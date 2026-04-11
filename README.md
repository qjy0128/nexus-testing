# Nexus Testing Framework

基于 OpenClaw 的多类型 AI 测试编排框架。系统会识别用户的测试意图，并把任务分流到 Skill、网页+接口、安卓、MCP 四类流程，按阶段零到阶段七产出结构化测试文档和 Go/No-Go 结论。

> 主要目标平台是 OpenClaw。Claude CLI runtime 适配仅作为宿主执行桥的可选后备方案，不改变本 Skill 面向 OpenClaw 的定位。

> 主入口是 [SKILL.md](SKILL.md)。共享阶段、角色、输出文件、门禁和超时基线以 [DEFINITIONS.md](DEFINITIONS.md) 为准；具体 Flow/Reference 的场景化细化按文档优先级覆盖。

## 当前状态

| Flow | 状态 | 说明 |
|------|------|------|
| Flow A（Skill 测试） | ✅ 可用 | 完整主流程，含 `live` / `shim-live` / `trace` 三层执行支持，带严格断言门禁、产品事实指纹和独立 verifier 要求 |
| Flow B（网页+接口） | ⚠️ 流程骨架 | 有角色分工和模板，无专用沙箱脚本，落地依赖浏览器/设备环境 |
| Flow C（安卓） | ⚠️ 流程骨架 | 同上，需 adb 等 Android 工具链 |
| Flow D（MCP） | ⚠️ 流程骨架 | 同上，需 MCP Server 可连接 |

## 相比常规 Skill 测试，多做了什么

常规的 Skill 测试，很多时候停留在“读一遍 `SKILL.md`、挑几个 prompt 试一下、人工写结论”的层面。Nexus Testing 在 Flow A 里额外做了这些事：

- **先建产品事实，再做测试设计**：不是直接凭感觉出用例，而是先生成 `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`SPEC-CONSISTENCY-REVIEW.md`，把测试对象的真实表面、能力、依赖和事实边界固定下来。
- **把 Skill 拆成真实表面来测**：不是把整个 Skill 当成一个黑盒 prompt，而是拆成 `skill`、`bin`、`package`、`plugin-manifest`、`openclaw-extension`、`mcp` 等 surface 分别设计和执行。
- **阶段三到阶段五是结构化联动的**：不仅输出 `TEST-DESIGN.md`，还会生成 `SURFACE-EXECUTION-PLAN.json`、`CASE-EXECUTION-PLAN.json`、`SKILL-SURFACE-WORKLIST.md`、`SURFACE-COVERAGE.json`，让阶段五执行和阶段七结论都能回溯到具体 case。
- **真实执行和静态分析被严格区分**：`live` / `shim-live` / `trace` 三层执行有硬门禁，没有真实执行证据时不能写成功能通过。
- **subagent 跑不动时有正式 takeover 机制**：不是简单报 blocked 就结束。Flow A 现在会优先尝试 fallback runtime，再由 host takeover executor 自动接管剩余 blocked/pending 的通用真实调用 case。
- **结果质量有二次校验**：阶段五结束后会用 `validate_flow_a_skill_results.py` 校验 `skill-results.md` 和 `SURFACE-COVERAGE.json`，防止“有文件但没真正覆盖 case”的空壳结果。
- **阶段输入路径被强约束**：阶段二及后续关键角色现在会收到 `requiredArtifactPaths` 的完整绝对路径清单，必须先按这些路径核验输入，不允许在工作区里自行猜路径或拿同名文件替代。
- **审批前有轻量自动校验**：阶段二、四等审批门在进入 `await-approval` 前，会先检查关键交付物是否存在、非空且满足最小结构，避免用户只看摘要就放行空壳文件。
- **审批前会拦截“有标题但没内容”的空心报告**：关键 markdown 交付物现在不只校验 heading 存在，还会校验每个必需 section 是否有实质内容，`TODO`/`mock`/占位句不会再混进审批门。
- **静默降级会被拉回接管**：runtime bridge 现在会把 “工具不可用后改走 fallback/web_fetch” 这种静默替代识别为 `blocked-policy`，不再允许表面 PASS 混入真实执行率。
- **Flow A 执行器有 provenance**：`scripts/run_flow_a_skill_execution.py` 和 `scripts/run_flow_a_takeover_execution.py` 现在都会输出 `skill-results.meta.json`，并由 `validate_flow_a_skill_results.py` 强制校验来源与路径一致性。
- **长时间无产出会被判 stalled**：runtime bridge 现在会监控 stdout/stderr 和报告目录产物变化；运行中长期无新增输出时，不再只能等总超时，而是提前标记为 `stalled` 并按 takeover 规则处理。
- **失败状态会保留细分类**：`RUNS/<stage>/<role>.state.json` 现在会额外记录 `runtimeStatus`，区分 `blocked-env`、`blocked-policy`、`stalled` 等真实失败类型，而不是全部压扁成 `failed`。

## 现阶段明确不做什么

- **不把纯静态阅读伪装成真实功能通过**。
- **不承诺所有 Skill 都能零适配深度自动化**。复杂私有运行时、强账号依赖、强人工判断链路仍可能需要专用 harness 或人工复核。
- **不把 Flow B/C/D 包装成和 Flow A 同等成熟**。当前真正有完整执行闭环的还是 Flow A。
- **不要求每个纯指令型 Skill 预先手写 `testing.json` 才能开始测试**；但当通用 takeover 仍不足以表达私有行为时，仓库私有 harness 仍是兜底方案。

### 沙箱执行能力

`auto` / `live` / `shim-live` / `trace` 四级调用控制：

- **`live`**：依赖 OpenClaw CLI，`--strict-real` 下要求 CLI 原生回传 `nexus-live-telemetry/v1` telemetry protocol。
- **`shim-live`**：依赖 Skill 提供 `testing.json` 或 `scripts/test-entry.*`；`--strict-real` 下必须携带独立 `--verification-manifest`，否则直接返回断言失败。
- **`auto --strict-real`**：当存在独立 verifier 时自动选择 `shim-live`，避免旧版 CLI 缺少 live telemetry 把本可验证的用例误判为 blocker。
- **`trace`**：仅用于静态补充分析，不能直接当成功能通过。
- **静态分析结论限制**：没有真实执行证据时，不得给出 `PASS` / `PARTIAL PASS`，只能给 `blocked` 或 `incomplete`。
- **输出语言**：所有交付物的描述性内容必须使用用户发起测试请求的语言；Flow A 生成器和 runner 支持显式传 `--language <request-language>`。
- **交付物发送路径**：报告先写入 `memory/nexus-reports/...`，对外发送前使用 `python scripts/prepare_report_delivery.py --report-file <memory-report-file>` 镜像到 `files/...`。
- **交付物发送闭环**：需要真实发送和用户确认时，使用 `python scripts/nexus_delivery.py send|confirm|status ...` 记录 receipt、evidence 和确认状态，而不再只停留在文件中转。
- **内部测试默认策略**：Flow A runner 新增 `--execution-profile internal-fast|balanced|strict`，默认 `internal-fast`，优先 host 执行并降低不必要的强门禁。

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

## 执行模型

- 主 agent 只负责测试类型路由、阶段推进、交付物发送、审批和打回
- 阶段零到阶段七都应由对应阶段角色 subagent 执行
- 串行阶段一次只启动当前阶段角色
- 阶段五和 Flow B 体验阶段按 Flow 模板并行启动多个 subagent
- `evidence-collector` 只在所有执行角色完成后独立启动
- subagent 因宿主环境不足无法继续时，runtime bridge 应先尝试该角色的 fallback runtime；仍无法完成时生成 `takeover-required` 工单，由主 agent 在当前 host session 接管
- approval request 不应只依赖 subagent 自述摘要；编排层会把 `artifactValidation.fileSummaries` 一并返回给主 agent，用于发送审批时附上真实交付物概览

## 标准执行流程

```text
阶段零：环境就绪检查 -> 等待用户确认
阶段一：需求解析 + 事实校验 -> PRODUCT-FINGERPRINT.json / SPEC.md / SPEC-CONSISTENCY-REVIEW.md
阶段二：质量评估 -> PRODUCT-QUALITY-REVIEW.md -> 等待用户批准
阶段三：测试设计 -> TEST-DESIGN.md / SURFACE-EXECUTION-PLAN.json
阶段四：用例评估 -> TEST-CASE-REVIEW.md -> 等待用户批准
阶段五：并行测试执行 -> TEST-EXECUTION/*.md / SKILL-SURFACE-WORKLIST.md / SURFACE-COVERAGE.json
阶段五完成后（后置角色）：证据收集 -> DEFECTS/evidence-collection.md
阶段六：缺陷分析 -> DEFECTS/DEFECT-REPORT.md
阶段七：报告整合 -> FINAL-TEST-REPORT.md
```

Flow B 支持双模式：
- A 模式：文档完整时走标准 8 阶段。
- B 模式：文档不全或需要深度体验时，插入双边体验、交叉核对、争议复检三个扩展阶段，总计 11 个阶段（B-阶段零~十）。

辅助角色：
- `tool-evaluator`：仅在用户主动请求工具评估时触发，不属于标准阶段。
- `workflow-optimizer`：仅在需要流程瓶颈分析或仲裁时触发，不属于标准阶段。

简化调度示意：

```text
主 agent
  -> 阶段零 environment-checker
  -> 阶段一 requirement-analyst -> spec-consistency-validator
  -> 阶段二 quality-assessor
  -> 阶段三 test-designer
  -> 阶段四 test-case-evaluator
  -> 阶段五 并行测试角色
  -> 阶段五后 evidence-collector
  -> 阶段六 defect-analyst
  -> 阶段七 report-integrator
```

阶段零建议先生成 `STAGE-SUBAGENT-PLAN.json`，作为后续阶段调度的唯一机器可读计划。

## 快速开始

1. 把这个仓库作为 OpenClaw Skill 项目打开，入口文件为 [SKILL.md](SKILL.md)。
2. 按被测对象类型准备输入：
   - Skill：源码路径或 `SKILL.md`
   - Web/API：URL、接口文档、页面截图
   - Android：`.apk` 路径
   - MCP：Server 地址、连接方式、JSON-RPC 信息
3. 先生成 `STAGE-SUBAGENT-PLAN.json`，明确本次测试每阶段要启动的 subagent。
4. 让主 agent 启动 `environment-checker` 执行阶段零环境就绪检查，确认输出目录、依赖环境和工具能力可用。
5. 从阶段一开始，按阶段为对应角色启动独立 subagent；主 agent 只负责调度、发文件、审批和打回。
6. 按阶段门禁推进。阶段二和阶段四必须等待用户显式批准。

## 仓库自检

```bash
python scripts/validate-framework.py        # 结构 + 语法 + 行为级 smoke test 校验
python scripts/generate_stage_subagent_plan.py --flow <skill|web-api|android|mcp> --mode <standard|b> --output-file <report-dir>/STAGE-SUBAGENT-PLAN.json # 生成机器可读的阶段角色调度计划
python scripts/nexus_stage_executor.py init --report-dir <report-dir> --flow <skill|web-api|android|mcp> --mode <standard|b> # 初始化阶段执行状态并生成调度计划
python scripts/nexus_stage_executor.py next --report-dir <report-dir> # 读取调度计划、交付物和审批状态，给出下一步该启动的阶段角色
python scripts/nexus_stage_executor.py dispatch --report-dir <report-dir> # 输出当前阶段每个 subagent 的 dispatch payload（角色文件、输入、输出、启动提示）
python scripts/nexus_stage_executor.py bundle-dispatch --report-dir <report-dir> # 将当前阶段 dispatch payload 落成 DISPATCH/ 目录下的 manifest、payload.json 和 prompt.md 文件
python tests/test_role_metadata.py   # 校验 role frontmatter / 章节兼容解析是否正确
python tests/test_dispatch_payload_schema.py # 校验 dispatch payload / bundle manifest schema 是否正确并能拦截坏配置
python tests/test_runtime_config_schema.py # 校验 runtime-config schema 是否正确并能拦截坏配置
python scripts/nexus_dispatch_runner.py prepare --report-dir <report-dir> # 将当前 DISPATCH bundle 转成 RUNS/ 目录下的运行清单
python scripts/nexus_dispatch_runner.py start-role --report-dir <report-dir> --stage-id <stage-id> --role-id <role-id> # 标记某个角色已开始执行
python scripts/nexus_dispatch_runner.py complete-role --report-dir <report-dir> --stage-id <stage-id> --role-id <role-id> --result-file <artifact> # 标记角色完成并记录结果文件
python scripts/nexus_dispatch_runner.py fail-role --report-dir <report-dir> --stage-id <stage-id> --role-id <role-id> --note <reason> # 标记某个角色执行失败，供恢复/重试使用
python scripts/nexus_dispatch_runner.py takeover-role --report-dir <report-dir> --stage-id <stage-id> --role-id <role-id> --note <reason> --takeover-file <handoff.json> # 标记该角色需要主 agent 接管
python scripts/nexus_dispatch_runner.py advance --report-dir <report-dir> # 当当前 RUNS 里的角色都完成后，自动补写 stage-complete 并推进到下一步调度动作
python scripts/generate_runtime_bridge_config.py --preset mock --output-file <runtime.json> # 生成 mock runtime-config
python scripts/generate_runtime_bridge_config.py --preset openclaw --output-file <runtime.json> --openclaw-command openclaw --channel telegram --skill-path <repo-root> # 生成 OpenClaw CLI 运行配置
python scripts/generate_runtime_bridge_config.py --preset claude --output-file <runtime.json> --claude-command claude --permission-mode bypassPermissions --allowed-tools Read Write Edit Bash # 生成 Claude CLI 运行配置
python scripts/nexus_openclaw_role_runtime.py --payload-file <payload.json> --prompt-file <prompt.md> --openclaw-command openclaw --dry-run # 预览 OpenClaw 子角色运行命令和最终 prompt
python scripts/run_openclaw_stage_demo.py start --report-dir <report-dir> --runtime-config runtime-config.openclaw.json # 初始化并运行到首个审批门
python scripts/run_openclaw_stage_demo.py approve --report-dir <report-dir> --stage-id <stage-id> --runtime-config runtime-config.openclaw.json --continue-run # 记录批准并继续推进到下一个审批门
python scripts/nexus_claude_role_runtime.py --payload-file <payload.json> --prompt-file <prompt.md> --claude-command claude --dry-run # 预览 Claude 子角色运行命令和最终 prompt
python scripts/nexus_runtime_bridge.py run-once --report-dir <report-dir> --runtime-config <runtime.json> # 读取当前 DISPATCH/RUNS，并按 runtime-config 调起外部执行命令跑完当前阶段
python scripts/nexus_runtime_bridge.py run-until-gate --report-dir <report-dir> --runtime-config <runtime.json> # 持续执行多个阶段，直到遇到审批门、No-Go、执行失败或流程完成
python scripts/diagnose_bash_runtime.py     # 诊断为什么当前环境没有可运行 bash
python scripts/generate_flow_a_stage1.py --target <repo-or-skill> --output-dir <report-dir> # 生成 Flow A 阶段一三件套
python scripts/generate_flow_a_test_design.py --fingerprint <PRODUCT-FINGERPRINT.json> --spec <SPEC.md> --consistency-review <SPEC-CONSISTENCY-REVIEW.md> --output-dir <report-dir> --language <request-language> # 生成多表面 TEST-DESIGN + SURFACE-EXECUTION-PLAN + CASE-EXECUTION-PLAN
python scripts/generate_flow_a_skill_execution.py --surface-plan <SURFACE-EXECUTION-PLAN.json> --output-dir <report-dir> --language <request-language> # 生成阶段五 surface 工单与初始 SURFACE-COVERAGE
python scripts/run_flow_a_skill_execution.py --surface-plan <SURFACE-EXECUTION-PLAN.json> --case-plan <CASE-EXECUTION-PLAN.json> --skill-path <repo-or-skill> --session-id <id> --sandbox-root <sandbox-root> --output-dir <report-dir> --execution-profile <internal-fast|balanced|strict> --language <request-language> # 优先按 case plan 执行 skill-tester；若 testing.json 提供 caseExecutionHarness / caseExecutionHarnesses，则逐 case 真实执行并回填 case coverage；否则对 skill surface 启用框架内置 generic case executor，自动逐 case 调用 skill，并对缺少强断言的 case 保守记为 incomplete；非 skill surface 默认按 surface 级能力生成单条 structural case，避免设计/执行错配
python scripts/prepare_report_delivery.py --report-file memory/nexus-reports/<date>-<type>-<flow>/<artifact>.md # 镜像阶段交付物到 files/... 供平台发送
python scripts/nexus_delivery.py send --report-file memory/nexus-reports/<date>-<type>-<flow>/<artifact>.md --backend relay-only # 记录发送动作；若接入外部 sender，可改用 --backend command --command ...
python scripts/security-scanner.py <dir>     # 安全扫描
python tests/test_sandbox_lifecycle.py       # E2E 生命周期测试
python tests/test_sandbox_exec_container.py  # sandbox-exec 容器后端 smoke test
python tests/test_nexus_delivery.py          # delivery 闭环与执行策略 smoke test
```

`validate-framework.py` 当前会校验：
- 核心文件、Flow 文件、沙箱脚本和治理文件是否齐全
- 所有 Markdown 本地链接是否有效
- `SKILL.md` 和 `roles/*.md` 的 frontmatter 是否完整
- `README.md` 的当前版本是否与 `CHANGELOG.md` 最新版本一致
- `.gitignore` 是否覆盖运行期产物
- 仓库内自带 JS helper 的 `package-lock.json` 是否存在且未被 `.gitignore` 错误忽略
- Flow 文件是否保留对 `DEFINITIONS.md` 的单一事实源声明
- Python 辅助脚本是否能通过 `py_compile`
- `docs/references/reference-approval-mechanism.md` 与 `DEFINITIONS.md` 的关键工件定义是否一致
- 阶段调度、dispatch runner 和 runtime bridge 是否都接入文档与脚本契约
- runtime bridge 是否能在角色失败时区分 `role-failed` 与 `takeover-required`，并为主 agent 留下可执行的接管工单
- Flow A 的 `skill-tester` 在纯指令型 Skill 被真实执行环境卡住时，是否能优先触发 host takeover executor，自动接管剩余 blocked/pending case，而不是只能人工补跑或要求仓库预置 `testing.json`
- runtime bridge 是否会按 role frontmatter 里的 `output_validation` / `minimum_output` / `minimum_output_aliases` 规则，对阶段二/三/七等关键 markdown 交付物执行结构校验，拦截只有占位标题或缺章的懒惰输出
- runtime bridge 是否会按 role frontmatter 里的 `takeover_enabled` / `takeover_statuses` / `takeover_patterns` / `takeover_on_process_failure` 自动触发 `takeover-required`，而不是在 bridge 代码里硬编码某几个角色
- Flow A 的产品事实指纹与阶段一生成链是否存在，并可通过 smoke test 生成 `PRODUCT-FINGERPRINT.json`、`SPEC.md`、`SPEC-CONSISTENCY-REVIEW.md`
- Flow A 的阶段三是否会把复杂目标拆成多表面 `TEST-DESIGN.md` 与 `SURFACE-EXECUTION-PLAN.json`
- Flow A 的规则/决策/检查项 inventory 是否能从 `SKILL.md`、伴随规则文件、以及相关源码中被抽取并数据驱动展开，而不是每个 capability 只有 1 条泛化用例
- Flow A 的阶段三是否会生成 `CASE-EXECUTION-PLAN.json`，把每条测试用例变成阶段五可执行输入，而不是只停留在文档枚举
- Flow A 的阶段五是否会把所有 surface 落到 `SKILL-SURFACE-WORKLIST.md`，并能用 `validate_flow_a_skill_results.py` 校验 `skill-results.md` 与 `SURFACE-COVERAGE.json` 的 case 覆盖完整性
- Flow A 是否在没有 custom harness 的情况下，仍能通过框架内置 generic case executor 把 skill surface 的所有 case 自动执行一遍，而不是直接跳过
- Flow A 的 surface runner 是否能真实执行 `skill/bin`，对 `package/plugin-manifest` 给出结构化校验结果，并通过 `openclawExtensionRuntimeHarness` / `openclawExtensionHarness` / live probe 处理 `openclaw-extension`，对 `mcp` 验证协议交互
- Flow A 的 case harness 是否能通过 `testing.json.caseExecutionHarness` / `caseExecutionHarnesses` 把复杂 skill 的规则、决策路径、检查项逐条执行，而不是只做 smoke test
- 交付物发送契约是否要求 `files/...` 中转、同轮发送和请求语言一致性
- 活跃角色文档中是否混入易漂移的内联版本号
- 本地存在可用 `bash` 时，对全部沙箱脚本执行 `bash -n` 语法检查；不可用时输出警告
- 若 `bash` 不可运行，可先执行 `python scripts/diagnose_bash_runtime.py` 查看候选路径、失败原因和修复建议
- Flow A runtime smoke tests（strict verifier、live telemetry、integration）

CI 也会在 GitHub Actions 中自动执行上述校验和全部 smoke tests。

`nexus_runtime_bridge.py` 的 `runtime-config` 为 JSON，至少包含：

```json
{
  "name": "my-runtime",
  "default": {
    "command": ["python", "my_runner.py", "--payload-file", "{payload_file}", "--prompt-file", "{prompt_file}"],
    "cwd": "{workspace_root}",
    "timeoutSeconds": 900,
    "mainAgentTakeoverPatterns": ["gateway", "blocked-no-real-exec"]
  },
  "roles": {
    "security-tester": {
      "command": ["python", "security_runner.py", "--payload-file", "{payload_file}"],
      "cwd": "{workspace_root}",
      "timeoutSeconds": 900
    },
    "skill-tester": {
      "command": ["python", "subagent_runner.py", "--payload-file", "{payload_file}", "--prompt-file", "{prompt_file}"],
      "cwd": "{workspace_root}",
      "timeoutSeconds": 900,
      "fallback": {
        "name": "host-takeover-probe",
        "command": ["python", "host_runner.py", "--payload-file", "{payload_file}", "--prompt-file", "{prompt_file}"],
        "cwd": "{workspace_root}",
        "timeoutSeconds": 900
      }
    }
  }
}
```

可用模板变量包括：`{workspace_root}`、`{report_dir}`、`{bundle_dir}`、`{run_dir}`、`{manifest_file}`、`{payload_file}`、`{prompt_file}`、`{stage_id}`、`{stage_name}`、`{stage_label}`、`{role_id}`、`{role_type}`、`{role_file}`。外部命令若 stdout 输出 `{"resultFile":"...", "note":"..."}`，bridge 会自动回写到 `RUNS/<stage>/<role>.state.json`。

可选输出字段：
- `status`: 例如 `completed` / `blocked`
- `needsMainAgentTakeover`: `true` 时 bridge 直接转成 `takeover-required`
- `blockers`: 简短 blocker 列表

当 runtime bridge 命中 takeover 规则时，会写出 `RUNS/<stage>/<role>.takeover.json`，并以 `takeover-required` 终止当前轮，让主 agent 拿着完整的 payload、prompt、日志和缺失交付物清单接管执行。默认只有需要真实环境的执行角色会启用这套内建策略；像 `environment-checker` 这类基础阶段角色，如果 runtime 只返回 `status=blocked`，会保持普通失败而不是误触发主 agent 接管。

如果宿主 runtime 是 Claude Code CLI，可直接这样起步：

```bash
python scripts/generate_runtime_bridge_config.py --preset claude --output-file runtime-config.claude.json --claude-command claude --permission-mode bypassPermissions --allowed-tools Read Write Edit Bash
python scripts/nexus_runtime_bridge.py run-until-gate --report-dir <report-dir> --runtime-config runtime-config.claude.json
```

`nexus_claude_role_runtime.py` 会读取 `payload.json` 和 `prompt.md`，拼出当前阶段角色的完整执行 prompt，然后用 `claude --print --output-format json --json-schema ...` 非交互执行，并把 Claude 返回的 `resultFile/note` 交回 runtime bridge。prompt 会显式携带角色职责、执行规则、证据要求和反模式，减少 subagent 只交空壳文件的概率。

现在 role metadata 统一优先从 frontmatter 读取。对 markdown 结构校验，使用 `output_validation`、`minimum_output`、`minimum_output_aliases`；对主 agent 接管，使用 `takeover_enabled`、`takeover_statuses`、`takeover_patterns`、`takeover_on_process_failure`。`src/nexus_testing/role_metadata.py` 负责解析这些字段并兼容旧章节写法；`nexus_stage_executor.py` 只负责把解析结果写进 dispatch payload。若旧角色还保留 `输出结构校验` / `输出结构校验别名` / `主Agent接管策略` 章节，parser 仍兼容，但新角色应优先使用 frontmatter schema。`role_metadata.py` 还会在解析阶段校验 frontmatter key/type/组合是否合法，提前拦截无效 alias、无效 takeover 配置和不受支持的 validation rule。

dispatch payload 现在也有独立 schema。`src/nexus_testing/dispatch_payload_schema.py` 会校验 `nexus_stage_executor.py` 产出的 payload 和 `DISPATCH/.../manifest.json` 的字段、类型、角色顺序、别名映射与 takeover policy 结构；`nexus_dispatch_runner.py` / `nexus_runtime_bridge.py` 在消费前会再次校验，避免损坏的 dispatch bundle 混入运行阶段。

`runtime-config` 现在也有独立 schema。`src/nexus_testing/runtime_config_schema.py` 会校验 root/default/roles/fallback 的字段、命令数组、超时、环境变量和 takeover 配置；`generate_runtime_bridge_config.py` 生成后会先自校验，`nexus_runtime_bridge.py` 读取时也会再次校验，避免坏 config 直到真正起外部命令时才失败。

如果宿主 runtime 是 OpenClaw CLI，更符合这个 Skill 的主目标定位，可直接这样起步：

```bash
python scripts/generate_runtime_bridge_config.py --preset openclaw --output-file runtime-config.openclaw.json --openclaw-command openclaw --channel telegram --skill-path .
python scripts/nexus_runtime_bridge.py run-until-gate --report-dir <report-dir> --runtime-config runtime-config.openclaw.json
```

`nexus_openclaw_role_runtime.py` 会调用 `openclaw invoke --skill <repo> --message <prompt> --channel <channel> --output <...> --result <...>`。如果 OpenClaw 结果 JSON 里没有直接给出 `resultFile`，适配器会回到报告目录里按当前阶段缺失交付物去探测新产物并回写给 runtime bridge。若结果里声明 `needsMainAgentTakeover=true`，bridge 会自动生成 takeover 工单。

如果要直接按 OpenClaw 主路径做端到端演练，可使用：

```bash
python scripts/run_openclaw_stage_demo.py start --report-dir <report-dir> --runtime-config runtime-config.openclaw.json
python scripts/run_openclaw_stage_demo.py approve --report-dir <report-dir> --stage-id stage-0 --runtime-config runtime-config.openclaw.json --continue-run
```

`run_openclaw_stage_demo.py` 会把初始化、运行到审批门、记录批准和继续推进串起来，适合验证 OpenClaw 宿主调度链路。

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
├── roles/                      # 21 个活跃角色
├── src/nexus_testing/            # 主实现代码
│   ├── delivery/                 # 交付物 relay/send/confirm/store
│   ├── runtime/                  # 执行策略与运行时政策
│   └── sandbox_skill_invoke/     # Python 沙箱包主实现
├── tests/                        # 主测试目录
│   ├── test_nexus_delivery.py    # delivery 闭环 smoke test
│   ├── test_sandbox_lifecycle.py # E2E 生命周期测试
│   └── test_flow_a_*.py          # Flow A 回归测试
├── scripts/
│   ├── sandbox-*.sh            # 沙箱执行脚本（invoke/exec/multi-turn/...）
│   ├── nexus_delivery.py       # delivery CLI 兼容入口
│   ├── extract_product_fingerprint.py # Flow A 产品事实指纹提取兼容入口
│   ├── generate_flow_a_stage1.py # Flow A 阶段一产物生成
│   ├── generate_flow_a_test_design.py # Flow A 阶段三多表面测试设计生成
│   ├── generate_flow_a_skill_execution.py # Flow A 阶段五 surface 工单生成
│   ├── run_flow_a_skill_execution.py # Flow A 阶段五 case/surface 执行 runner
│   ├── security-scanner.py     # 安全扫描
│   ├── validate-framework.py   # 框架结构校验
│   ├── skill-structure-validator.py
│   ├── validate_flow_a_skill_results.py # 校验 skill-results 是否覆盖全部 surface
│   └── fixtures/               # 元测试固件（pass/defect/extreme）
├── docs/
│   ├── references/             # 18 个参考文档
│   └── *.md                    # 计划、评估和执行文档
├── archive/                    # 已归档的历史模板和 changelog
├── .github/workflows/          # CI
├── memory/nexus-reports/       # 运行期产物（不入库）
└── files/                      # 对外发送前的工作区中转附件（不入库）
```

角色目录包含 21 个活跃角色和 1 个已归档模板（`archive/roles/compatibility-tester-skill.md`）。

## 报告输出

所有测试报告输出到 `memory/nexus-reports/{date}-{test-type}-{flow}/`，其中核心交付物包括：

- `PRODUCT-FINGERPRINT.json`
- `STAGE-SUBAGENT-PLAN.json`
- `SPEC.md`
- `SPEC-CONSISTENCY-REVIEW.md`
- `PRODUCT-QUALITY-REVIEW.md`
- `TEST-DESIGN.md`
- `SURFACE-EXECUTION-PLAN.json`
- `TEST-CASE-REVIEW.md`
- `TEST-EXECUTION/*.md`
- `TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md`
- `TEST-EXECUTION/SURFACE-COVERAGE.json`
- `DEFECTS/DEFECT-REPORT.md`
- `FINAL-TEST-REPORT.md`

更完整的目录结构和文件职责见 [DEFINITIONS.md](DEFINITIONS.md) 第三节。

## 维护约定

- 统一定义只写在 [DEFINITIONS.md](DEFINITIONS.md)，`SKILL.md`、`flows/`、`roles/` 只做引用和场景化补充。
- 运行期文件写入 `memory/nexus-reports/`、`.nexus-sandbox/`、`.tmp-test-runs/`、`.tmp-validation/` 等目录，不要把这些产物提交回仓库。
- 任何修改入口、流程、角色或参考文档后，都应先跑一次 `python scripts/validate-framework.py`。
- 任何修改入口、流程、角色、参考文档、校验器或执行语义时，必须同步更新 `README.md` 和 `CHANGELOG.md`。
- 主实现优先放在 `src/nexus_testing/`，`scripts/` 默认只保留 CLI 和兼容入口。
- 主测试统一放在 `tests/`，直接执行 `python tests/test_*.py` 或 `pytest` 即可。
- 仓库内维护的 JS helper 需要提交对应 `package-lock.json`，保证 Playwright 等依赖可复现安装。
- Shell 脚本默认按 LF 换行维护，避免在 Git Bash / Linux 环境中出现执行异常。
- 新增核心脚本、源码模块或测试支持文件需要在 `validation-manifest.json` 注册，新增 smoke test 会由 `tests/test_*.py` 自动发现。

## 参考文档一览

| 文件 | 用途 |
|------|------|
| `DEFINITIONS.md` | 阶段、角色、门禁、超时单一事实源 |
| `docs/references/reference-sandbox-spec.md` | 沙箱执行环境完整规格 |
| `docs/references/reference-security-scan.md` | 安全扫描规则 |
| `docs/references/reference-security-blacklist.md` | 安全黑名单 |
| `docs/references/reference-approval-mechanism.md` | 批准/拒绝/无响应规则 |
| `docs/references/reference-recovery.md` | 测试中断后的恢复/续跑机制 |
| `docs/references/reference-report-format.md` | 报告输出格式规范 |
| `docs/references/reference-production-readiness.md` | 生产就绪检查清单 |
| `docs/references/reference-flow-skill.md` | Flow A 详细参考 |
| `docs/references/reference-flow-web-api.md` | Flow B 详细参考 |
| `docs/references/reference-flow-android.md` | Flow C 详细参考 |
| `docs/references/reference-flow-mcp.md` | Flow D 详细参考 |
| `docs/references/reference-expected-outputs.md` | 各阶段预期输出 |
| `docs/references/reference-output-verification-examples.md` | 输出验证示例 |
| `docs/references/reference-test-case-templates.md` | 用例模板 |
| `docs/references/reference-external-case-sourcing.md` | 外部用例来源 |
| `docs/references/reference-skill-tier-requirements.md` | Skill 分层要求 |
| `docs/references/reference-skill-review-framework.md` | Skill 评审框架 |
| `docs/references/reference-agent-evaluation-methodology.md` | Agent 评估方法论 |

## 支持渠道

Telegram、飞书、QQ、微信。微信和 QQ 使用”先文字后文件”的降级发送策略。

## 当前版本

v0.9.46 — 详见 [CHANGELOG.md](CHANGELOG.md)

