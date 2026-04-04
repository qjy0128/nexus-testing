# 流程 B：网页 + 接口测试

> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**

## 触发条件
用户请求测试网页、页面、web、接口、API（包含对应关键词）

## 测试目标
验证前端页面功能、接口合规性、跨浏览器适配、安全性、性能

## 推荐测试工具

> Flow B 的测试工程师在阶段五/B-阶段八执行时，推荐使用以下浏览器自动化工具。**工具为可选项**——不可用时退化为手动测试或沙箱模拟执行。

### playwright-cli（首选）

**适用场景**：功能测试、兼容性测试、无障碍测试、证据收集

| 能力 | 命令 | 用途 |
|------|------|------|
| 多浏览器 | `--browser=chrome/firefox/webkit/msedge` | 跨浏览器测试（A 模式 Step 5.4 / B 模式 Step 8.4） |
| 截图 | `screenshot --filename=page.png` | 证据收集（每个测试步骤） |
| 无障碍树 | `snapshot` | 无障碍测试（A 模式 Step 5.5 / B 模式 Step 8.5） |
| 网络日志 | `network` | API 请求响应验证 |
| 网络模拟 | `route "**/*" --status=404` | 安全测试/错误场景模拟 |
| 视频录制 | `video-start/stop` | 缺陷复现视频 |
| 会话管理 | `-s=name`（命名会话） | 并行测试工程师各自独立会话 |
| 状态持久化 | `state-save/load` | 登录流程测试 |
| JS 执行 | `eval "document.title"` | 动态内容验证 |

**在 Flow B 中的使用方式**：
- functional-tester：用 `open` → `goto` → `click/fill/type` → `snapshot` 驱动页面交互
- compatibility-tester：用 `--browser=` 切换浏览器引擎
- accessibility-auditor：用 `snapshot` 获取无障碍树，检查 ARIA 标签
- evidence-collector：用 `screenshot` + `video` 捕获结构化证据

### chrome-cdp（辅助，SPA 专用）

**适用场景**：B 模式双边体验、SPA/动态内容扫描、连接真实浏览器

| 能力 | 命令 | 用途 |
|------|------|------|
| 连接真实浏览器 | 连接已打开的 Chrome（`--remote-debugging-port=9222`） | 复现用户看到的内容 |
| 动态元素扫描 | `scan <target> [settleMs]` | SPA 异步渲染内容检测 |
| 无限滚动 | `loadall <target>` | 长列表/Feed 页面测试 |
| 网络时序 | `net <target>` | 性能数据采集 |
| CDP 直通 | `evalraw` | 高级调试场景 |

**在 Flow B 中的使用方式**：
- B 模式 experience-tester-a/b：用 `scan` 确保不遗漏动态渲染的内容
- performance-tester：用 `net` 获取 Resource Timing 数据
- 任何需要「连接用户正在使用的浏览器」的场景

### 工具选择决策

```
需要浏览器自动化？
├─ 是 → 需要连接用户已有的浏览器？
│       ├─ 是 → chrome-cdp
│       └─ 否 → 需要多浏览器兼容性测试？
│               ├─ 是 → playwright-cli
│               └─ 否 → playwright-cli（默认）
└─ 否 → 沙箱执行（sandbox-exec）或手动测试
```

**⚠️ 阶段编号说明**：
Flow B 有两种模式。**A 模式严格遵循标准 8 阶段（阶段零~七）**。B 模式在标准阶段之间插入 3 个独有阶段（双边体验→交叉核对→争议复检），总计 11 个阶段（B-阶段零~十）。

> **B 模式完整阶段定义、门禁规则、输出文件统一引用** `DEFINITIONS.md` 第四节「Flow B 双模式阶段定义」。沟通时 B 模式使用「B-阶段X」前缀，避免与标准阶段编号混淆。

**A 模式阶段映射**（标准 8 阶段，阶段零~七）：

| A 模式 | 主框架 | 内容 |
|--------|--------|------|
| 阶段零 | 阶段零 | 环境就绪检查 |
| 阶段一 | 阶段一 | 需求解析 |
| 阶段二 | 阶段二 | 质量评估 |
| 阶段三 | 阶段三 | 测试设计 |
| 阶段四 | 阶段四 | 用例评估 |
| 阶段五 | 阶段五 | 并行测试执行 |
| 阶段六 | 阶段六 | 缺陷分析 |
| 阶段七 | 阶段七 | 报告整合 |

**B 模式阶段映射**（使用 B-阶段前缀，详见 DEFINITIONS.md）：

| B 模式 | 主框架 | 内容 |
|--------|--------|------|
| B-阶段零 | 阶段零 | 环境就绪检查 |
| B-阶段一 | 阶段一 | 需求解析 |
| B-阶段二 | 阶段二 | 质量评估 + 文档判定 |
| B-阶段三 | —（独有） | 双边深度体验 |
| B-阶段四 | —（独有） | 交叉核对 |
| B-阶段五 | —（独有） | 争议复检 |
| B-阶段六 | 阶段三 | 测试用例生成 |
| B-阶段七 | 阶段四 | 用例评估 |
| B-阶段八 | 阶段五 | 并行测试执行 |
| B-阶段九 | 阶段六 | 缺陷分析 |
| B-阶段十 | 阶段七 | 报告整合 |

---

## 执行流程（两种模式）

### 判断依据

**阶段一完成后**，质量评估师需判断：

| 产品文档状态 | 说明 | 走哪个模式 |
|-------------|------|-----------|
| **文档完整** | 有完整的产品规格说明、用户流程图、接口文档 | 走 **A模式**（原有流程） |
| **文档不全/无文档** | 只有 URL 或截图，无法获取完整产品说明 | 走 **B模式**（双边体验模式） |

**重要**：登录场景、用户中心、复杂交互页面**无论文档是否完整**，都必须走 B模式进行深度体验。

---

## A模式：文档完整测试流程

### 阶段零：环境就绪检查
**执行角色**：主 agent

输入：URL / API 文档
输出：环境就绪报告（内存中）
任务：
- 基础检查：URL 是否可访问、API 是否返回有效响应
- 通用检查：输出目录可写性、渠道配置

**需用户确认后才能进入阶段一**

### 阶段一：需求解析
**执行角色**：`roles/requirement-analyst.md`

输入：需求文档 / API 文档 / 页面截图 / URL
输出：`SPEC.md`
任务：提取页面功能点、接口清单、数据流、验收标准

### 阶段二：质量评估
**执行角色**：`roles/quality-assessor.md`

输入：`SPEC.md`
输出：产品质量评估报告
任务：评估需求完整性、功能可行性、非功能需求
**需批准后才能进入阶段三**

### 阶段三：测试设计
**执行角色**：`roles/test-designer.md`

输入：`SPEC.md`
输出：`TEST-DESIGN.md`
任务：设计测试用例

### 阶段四：用例评估
**执行角色**：`roles/test-case-evaluator.md`

输入：`TEST-DESIGN.md` + `SPEC.md`
输出：用例评估报告
**需批准后才能进入阶段五**

### 阶段五：并行测试执行

**重要**：每个角色必须独立执行并输出各自的交付物。

> **执行验证标准**：统一引用 `DEFINITIONS.md` 第十节「执行验证标准」。

**Flow B 并行角色（共 5 个）**：
- `roles/functional-tester.md`（功能测试）→ `TEST-EXECUTION/functional-results.md`
- `roles/compatibility-tester.md`（兼容性测试）→ `TEST-EXECUTION/compatibility-results.md`
- `roles/security-tester.md`（安全测试）→ `TEST-EXECUTION/security-results.md`
- `roles/performance-tester.md`（性能测试）→ `TEST-EXECUTION/performance-results.md`
- `roles/accessibility-auditor.md`（无障碍测试）→ `TEST-EXECUTION/accessibility-results.md`

#### 阶段五后：证据收集
**执行角色**：`roles/evidence-collector.md`

阶段五所有 subagent 完成后执行一次性验证（非实时监控）
输出：`DEFECTS/evidence-collection.md`

**文件发送要求**：每个角色的交付物必须单独发送，并附带内容摘要和下一步说明。

### 阶段六：缺陷分析
**执行角色**：`roles/defect-analyst.md`

输入：`TEST-EXECUTION/*.md` + `DEFECTS/evidence-collection.md`
输出：`DEFECTS/DEFECT-REPORT.md`
任务：汇总所有缺陷，去重、定级、误杀排查、漏检补充
**打回机制**：有问题 → 打回测试设计师/测试工程师重新测试 → 循环阶段五/六（最多 3 轮）

### 阶段七：报告整合
**执行角色**：`roles/report-integrator.md`

输入：所有测试结果 + `DEFECTS/DEFECT-REPORT.md`
输出：`FINAL-TEST-REPORT.md`
任务：缺陷定级、汇总所有问题、输出 Go/No-Go 建议

---

## B模式：双边体验测试流程（无文档/文档不全）

> B 模式阶段使用「B-阶段X」前缀，避免与标准阶段编号混淆。完整阶段定义见 `DEFINITIONS.md` 第四节。

### B-阶段零：环境就绪检查
**执行角色**：主 agent

输入：URL / 页面截图
输出：环境就绪报告（内存中）
任务：
- 基础检查：URL 是否可访问、API 是否返回有效响应
- 通用检查：输出目录可写性、渠道配置

**需用户确认后才能进入 B-阶段一**

### B-阶段一：需求解析
**执行角色**：`roles/requirement-analyst.md`

输入：URL / 页面截图
输出：`SPEC.md`（可能不完整，仅包含已知信息）
任务：记录已知的零散信息，不强求完整

### B-阶段二：质量评估 + 文档判定
**执行角色**：`roles/quality-assessor.md`

输入：`SPEC.md`
输出：产品质量评估报告
任务：
1. 评估 `SPEC.md` 完整度
2. 判断走 A模式 还是 B模式
3. **如果走 B模式**：明确列出"已知的已知"和"已知的未知"

**文档完整度判定标准**：
| 维度 | 完整 | 不完整 |
|------|------|--------|
| 用户流程 | 有完整流程图 | 只有 URL |
| 功能清单 | 有明确功能列表 | 无法枚举 |
| 接口文档 | 有 API 说明 | 只有 URL |
| 登录机制 | 有说明 | 需要自己探索 |

**需批准后才能进入 B-阶段三**

---

### B-阶段三：双边深度体验

**执行角色**：
- `roles/experience-tester-a.md`（体验工程师 A）
- `roles/experience-tester-b.md`（体验工程师 B）

**输入**：目标 URL + 已知的未知清单
**输出**：各自输出独立的体验报告

**核心原则**：
- **不跳过任何功能**——登录、用户中心、支付等全部要测
- **遇到不确定就标记**——记录下来，不主观猜测
- **截图是必须品**——每个功能点、每个异常都要有截图
- **遇到问题不自行判断严重性**——如实记录现象

**A 和 B 必须分别独立体验**，不允许提前讨论或分工。

**A 的输出**：`experience-report-a.md`
**B 的输出**：`experience-report-b.md`

---

### B-阶段四：交叉核对

**执行角色**：
- A 检查 B 的报告 → 输出 `cross-check-b-by-a.md`
- B 检查 A 的报告 → 输出 `cross-check-a-by-b.md`

**交叉核对内容**：
1. **你漏了哪些功能点？**（对方体验到了，我没体验到）
2. **你漏了哪些异常？**（对方发现了，我没发现）
3. **截图证据齐不齐全？**（有没有关键步骤缺失截图）
4. **有没有争议点？**（同一现象，结论不同）

**输出格式**：
```
## 核对结果

### A 漏了（由 B 发现）
| 功能/异常 | B 的描述 | B 的截图 | 严重性待定 |

### B 漏了（由 A 发现）
| 功能/异常 | A 的描述 | A 的截图 | 严重性待定 |

### 争议点
| 现象 | A 的解读 | B 的解读 | 需要复检 |

### 截图完整性
- ✅ A 的截图齐全
- ⚠️ B 缺少 xxx 的截图
```

---

### B-阶段五：争议复检 + 补充体验

**执行角色**：
- A 复检自己漏的内容 + 争议点
- B 复检自己漏的内容 + 争议点

**复检任务**：
1. 对交叉核对发现的遗漏进行**补充体验**
2. 对争议点进行**实地复测**
3. 更新自己的体验报告

**输出**：
- A 更新 `experience-report-a.md`
- B 更新 `experience-report-b.md`

---

### B-阶段六：测试用例生成

**执行角色**：`roles/test-designer.md`

输入：`experience-report-a.md` + `experience-report-b.md` + `cross-check` 结果
输出：`TEST-DESIGN.md`

**核心任务**：
1. 整合两人体验到的所有功能点
2. 整合两人发现的所有异常
3. 生成覆盖所有功能的测试用例
4. **不遗漏任何一个功能**

---

### B-阶段七：用例评估
**执行角色**：`roles/test-case-evaluator.md`

输入：`TEST-DESIGN.md` + `SPEC.md`
输出：`TEST-CASE-REVIEW.md`
任务：评估测试用例覆盖率、边界条件覆盖、测试数据充分性
**需批准后才能进入 B-阶段八**

---

### B-阶段八：并行测试执行

**重要**：每个角色必须独立执行并输出各自的交付物。

> **执行验证标准**：统一引用 `DEFINITIONS.md` 第十节「执行验证标准」。每个测试用例必须包含真实的 HTTP 请求和实际响应，禁止仅读 API 文档写验证结论。

#### Step 8.1：功能测试
**执行角色**：`roles/functional-tester.md`

输入：`TEST-DESIGN.md` + 目标 URL
输出：`TEST-EXECUTION/functional-results.md`
测试内容：
- 页面交互测试
- 状态流转测试
- 前端校验测试
- 接口功能测试

#### Step 8.2：安全测试
**执行角色**：`roles/security-tester.md`

输入：目标系统
输出：`TEST-EXECUTION/security-results.md`
测试内容：
- XSS / SQL 注入
- CSRF / 越权访问
- 敏感数据暴露

#### Step 8.3：性能测试
**执行角色**：`roles/performance-tester.md`

输入：目标 URL / API
输出：`TEST-EXECUTION/performance-results.md`
测试内容：
- 页面加载时间
- 接口响应时间（P50/P95/P99）
- Lighthouse 评分

#### Step 8.4：兼容性测试
**执行角色**：`roles/compatibility-tester.md`

输入：目标 URL
输出：`TEST-EXECUTION/compatibility-results.md`
测试内容：
- 跨浏览器测试
- 响应式布局验证
- 多系统版本适配

#### Step 8.5：无障碍测试
**执行角色**：`roles/accessibility-auditor.md`

输入：目标 URL
输出：`TEST-EXECUTION/accessibility-results.md`
测试内容：
- WCAG 合规检查
- 键盘导航验证
- 屏幕阅读器兼容

#### Step 8.6：证据收集
**执行角色**：`roles/evidence-collector.md`

B-阶段八所有 subagent 完成后执行一次性验证（非实时监控）
输出：`DEFECTS/evidence-collection.md`

---

### B-阶段九：缺陷分析
**执行角色**：`roles/defect-analyst.md`

输入：`TEST-EXECUTION/*.md` + `DEFECTS/evidence-collection.md`
输出：`DEFECTS/DEFECT-REPORT.md`
任务：汇总所有缺陷，去重、定级、误杀排查、漏检补充
**打回机制**：有问题 → 打回测试设计师/测试工程师 → 循环（最多 3 轮）

### B-阶段十：报告整合

**执行角色**：`roles/report-integrator.md`

输入：所有测试结果 + `DEFECTS/DEFECT-REPORT.md` + 双边体验报告
输出：`FINAL-TEST-REPORT.md`

**整合报告必须包含**：
- 双边体验的完整功能覆盖清单（证明没有遗漏）
- 争议点的最终裁定结果
- 截图证据索引

---

## 文件发送要求

每个角色的交付物必须**单独发送**，并附带摘要说明：
1. 发送了什么文件
2. 文件内容摘要
3. **下一步是什么**

---

## 流程对比

| A模式（标准 8 阶段） | B模式（B-阶段前缀，共 11 阶段） | 内容差异 |
|---------------------|-------------------------------|---------|
| 阶段零 | B-阶段零 | 环境就绪检查 |
| 阶段一 | B-阶段一 | 需求解析 |
| 阶段二 | B-阶段二 | 质量评估（B 模式含文档判定） |
| 阶段三 | B-阶段三（独有） | A: 测试设计 / B: **双边深度体验** |
| 阶段四 | B-阶段四（独有） | A: 用例评估 / B: **交叉核对** |
| — | B-阶段五（独有） | B: **争议复检 + 补充体验** |
| — | B-阶段六 | B: 测试用例生成（对应 A 模式阶段三） |
| — | B-阶段七 | B: 用例评估（对应 A 模式阶段四，需批准） |
| 阶段五 | B-阶段八 | 并行测试执行 + 证据收集 |
| 阶段六 | B-阶段九 | 缺陷分析 |
| 阶段七 | B-阶段十 | 报告整合 |

**关键区别**：B模式在测试设计前插入"双边体验→交叉核对→争议复检"三个独有阶段，总计 11 个阶段（B-阶段零~十），确保不遗漏任何功能。
