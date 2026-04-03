# Flow B（网页+接口测试）详细模板参考

> 本文件供网页和接口测试时查阅，补充 SKILL.md 和 web-api-testing.md 中的详细格式要求。

---

## 一、接口测试用例模板

### 1.1 HTTP 方法测试

| 用例 ID | 接口 | 方法 | 参数 | 预期结果 | 优先级 |
|---------|------|------|------|---------|--------|
| TC-API-01 | `/api/login` | POST | `{email, password}` | 200 + token | P0 |
| TC-API-02 | `/api/login` | GET | - | 405 Method Not Allowed | P0 |
| TC-API-03 | `/api/user/:id` | GET | 有效 ID | 200 + user object | P0 |

### 1.2 边界值测试

| 用例 ID | 字段 | 输入值 | 预期结果 | 优先级 |
|---------|------|-------|---------|--------|
| TC-BOUND-01 | email | 空字符串 | 400 + 错误提示 | P0 |
| TC-BOUND-02 | email | 无 @ 邮箱 | 400 + 格式错误 | P0 |
| TC-BOUND-03 | password | 1 个字符 | 400 + 长度不足 | P1 |

### 1.3 认证与授权测试

| 用例 ID | 场景 | 预期结果 | 优先级 |
|---------|------|---------|--------|
| TC-AUTH-01 | 无 token 请求 | 401 Unauthorized | P0 |
| TC-AUTH-02 | 过期 token | 401 Token Expired | P0 |
| TC-AUTH-03 | 他人资源访问 | 403 Forbidden | P0 |

---

## 二、网页测试用例模板

### 2.1 页面渲染测试

| 用例 ID | 页面 | 验证点 | 优先级 |
|---------|------|--------|--------|
| TC-UI-01 | 首页 | 核心元素可见、无白屏 | P0 |
| TC-UI-02 | 列表页 | 数据正确渲染 | P0 |
| TC-UI-03 | 表单页 | 输入框/按钮可见 | P0 |

### 2.2 用户交互测试

| 用例 ID | 操作 | 步骤 | 预期结果 | 优先级 |
|---------|------|------|---------|--------|
| TC-INTER-01 | 登录成功 | 输入正确凭据 | 跳转首页 + 显示用户名 | P0 |
| TC-INTER-02 | 登录失败 | 输入错误密码 | 提示错误信息 | P0 |
| TC-INTER-03 | 表单提交 | 填写完整表单 | 提交成功提示 | P1 |

---

## 三、性能测试参考值

| 指标 | 目标值 | 告警阈值 |
|------|--------|---------|
| 首次内容绘制（FCP） | < 1.8s | > 3.0s |
| 页面加载时间 | < 3.0s | > 5.0s |
| API 响应时间（p95） | < 500ms | > 1000ms |
| 并发用户数 | 支持 100 并发 | - |

---

## 四、Flow B 阶段产出清单

| 阶段 | 文件名 | 必填字段 |
|------|--------|---------|
| 阶段一 | `SPEC.md` | URL、API 端点列表、接口文档 |
| 阶段二 | `PRODUCT-QUALITY-REVIEW.md` | 完整性、风险点 |
| 阶段三 | `TEST-DESIGN.md` | 用例清单 |
| 阶段四 | `TEST-CASE-REVIEW.md` | 覆盖率 |
| 阶段五 | `TEST-EXECUTION/functional-results.md` | 功能测试结果 |
| 阶段五 | `TEST-EXECUTION/compatibility-results.md` | 浏览器兼容性结果 |
| 阶段五 | `TEST-EXECUTION/security-results.md` | 安全检测结果 |
| 阶段五 | `TEST-EXECUTION/performance-results.md` | 性能测试结果 |
| 阶段五 | `TEST-EXECUTION/accessibility-results.md` | 无障碍测试结果 |
| 阶段六 | `DEFECTS/DEFECT-REPORT.md` | 缺陷清单 |
| 阶段七 | `FINAL-TEST-REPORT.md` | Go/No-Go 判定 |
