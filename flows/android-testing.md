# 流程 C：安卓应用测试

## 触发条件
用户请求测试 APK、安卓应用（包含 "APK"、"安卓"、"android" 关键词）

## 测试目标
验证安卓应用的安装、功能、权限、数据持久化、设备适配、安全、性能

## 执行步骤

### 阶段一：需求解析
**执行角色**：`roles/requirement-analyst.md`

输入：APK 文件路径 / 需求文档 / 截图
输出：`SPEC.md`
任务：提取功能清单、页面流、数据依赖、权限要求

### 阶段二：质量评估（评估产品本身）
**执行角色**：`roles/quality-assessor.md`

输入：`SPEC.md`
输出：产品质量评估报告
任务：评估需求完整性、功能可行性、非功能需求
**需批准后才能进入阶段三**

### 阶段三：测试设计
**执行角色**：`roles/test-designer.md`

输入：`SPEC.md`
输出：`TEST-DESIGN.md`
任务：设计测试用例——安装/卸载测试、功能测试用例、权限验证矩阵、设备适配矩阵

### 阶段四：用例评估（评估测试用例本身）
**执行角色**：`roles/test-case-evaluator.md`

输入：`TEST-DESIGN.md` + `SPEC.md`
输出：用例评估报告
任务：评估测试用例覆盖率、边界条件覆盖、测试数据充分性
**需批准后才能进入阶段五**

### 阶段五：并行测试执行

> **执行验证标准**：统一引用 `DEFINITIONS.md` 第十节「执行验证标准」。每个测试用例必须包含真实的执行动作和实际输出，禁止仅读文档写验证结论。

**重要**：每个角色必须独立执行并输出各自的交付物，禁止合并。发送文件时优先使用 caption；平台不支持时，必须随文件附带摘要说明。

#### Step 5.1：功能测试
**执行角色**：`roles/functional-tester.md`

输入：`TEST-DESIGN.md` + APK
输出：`TEST-EXECUTION/functional-results.md`
测试内容：
- 应用安装/卸载/升级
- Activity/Fragment 流转
- 数据一致性验证

#### Step 5.2：安全测试
**执行角色**：`roles/security-tester.md`

输入：APK 文件
输出：`TEST-EXECUTION/security-results.md`
测试内容：
- APK 反编译风险
- 权限滥用检测
- 数据存储安全（SharedPreferences/SQLite 加密）
- Intent/IPC 安全（导出组件权限检查）
- ContentProvider SQL 注入
- WebView 安全（JS 启用/file 协议）
- 日志泄露（Logcat 敏感信息）
- 通信加密（HTTPS 强制/证书校验）
- 详见 `roles/security-tester.md` APK 安全测试节

#### Step 5.3：性能测试
**执行角色**：`roles/performance-tester.md`

输入：APK
输出：`TEST-EXECUTION/performance-results.md`
测试内容：
- 冷启动时间
- 内存/CPU 占用
- 电池消耗

#### Step 5.4：兼容性测试
**执行角色**：`roles/compatibility-tester.md`

输入：APK
输出：`TEST-EXECUTION/compatibility-results.md`
测试内容：
- 多设备测试
- 系统版本兼容
- 屏幕尺寸/分辨率适配

#### Step 5.5：现实场景测试
**执行角色**：`roles/reality-checker.md`

输入：`TEST-DESIGN.md`
输出：`TEST-EXECUTION/reality-results.md`
测试内容：
- 弱网环境测试
- 中断恢复测试
- 电量/内存压力测试

#### Step 5.6：证据收集
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
