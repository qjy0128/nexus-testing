# Flow C（安卓测试）详细模板参考

> 本文件供安卓 APK 测试时查阅，补充 SKILL.md 和 android-testing.md 中的详细格式要求。

---

## 一、安卓功能测试用例模板

### 1.1 核心功能测试

| 用例 ID | 功能 | 测试步骤 | 预期结果 | 优先级 |
|---------|------|---------|---------|--------|
| TC-APP-01 | 应用启动 | 1. 点击图标 | 3秒内进入首页 | P0 |
| TC-APP-02 | 登录 | 1. 输入账号密码 2. 点击登录 | 跳转首页 | P0 |
| TC-APP-03 | 列表加载 | 1. 进入列表页 | 数据正确展示 | P0 |

### 1.2 异常场景测试

| 用例 ID | 场景 | 测试步骤 | 预期结果 | 优先级 |
|---------|------|---------|---------|--------|
| TC-EXC-01 | 无网络 | 1. 断网 2. 打开 App | 显示网络错误提示 | P0 |
| TC-EXC-02 | 弱网 | 1. 切换 2G | 显示加载超时 | P1 |
| TC-EXC-03 | Crash | 1. 特定操作 | App 不崩溃 | P0 |

---

## 二、兼容性测试设备矩阵

| 设备 | 系统版本 | 屏幕尺寸 | 分辨率 | 厂商 |
|------|----------|---------|--------|------|
| 三星 Galaxy S24 | Android 14 | 6.2" | 2340x1080 | Samsung |
| 小米 14 | Android 14 | 6.4" | 2670x1200 | Xiaomi |
| OPPO Find X7 | Android 13 | 6.7" | 2780x1264 | OPPO |
| vivo X100 | Android 14 | 6.8" | 2800x1260 | vivo |
| 华为 Mate 60 | HarmonyOS 4 | 6.7" | 2688x1216 | Huawei |

---

## 三、安全测试关注点

| 测试项 | 方法 | 通过标准 | 优先级 |
|--------|------|---------|--------|
| 反编译检测 | apktool 尝试反编译 | 代码混淆有效 | P0 |
| 权限申请 | 检查危险权限 | 权限最小化 | P1 |
| 敏感数据存储 | 检查 SharedPreferences | 无明文敏感数据 | P0 |
| 网络传输 | 抓包检测 | HTTPS + 证书校验 | P0 |

---

## 四、Flow C 阶段产出清单

| 阶段 | 文件名 | 必填字段 |
|------|--------|---------|
| 阶段一 | `SPEC.md` | APK 路径、包名、主要 Activity |
| 阶段二 | `PRODUCT-QUALITY-REVIEW.md` | 风险评估 |
| 阶段三 | `TEST-DESIGN.md` | 功能/兼容/安全/性能用例 |
| 阶段四 | `TEST-CASE-REVIEW.md` | 覆盖率 |
| 阶段五 | `TEST-EXECUTION/functional-results.md` | 功能测试结果 |
| 阶段五 | `TEST-EXECUTION/compatibility-results.md` | 设备兼容性结果 |
| 阶段五 | `TEST-EXECUTION/security-results.md` | 安全检测结果 |
| 阶段五 | `TEST-EXECUTION/performance-results.md` | 性能数据 |
| 阶段五 | `TEST-EXECUTION/reality-results.md` | 真机验证结果 |
| 阶段六 | `DEFECTS/DEFECT-REPORT.md` | 缺陷清单 |
| 阶段七 | `FINAL-TEST-REPORT.md` | Go/No-Go 判定 |
