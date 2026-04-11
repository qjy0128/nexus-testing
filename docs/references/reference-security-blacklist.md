# Caption XSS 注入字符黑名单

> 主入口和各角色在发送文件前，对 caption 内容执行以下安全检测。检测到任一项即拒绝发送。

---

## 一、事件处理器（完整）

`onerror=`、`onload=`、`onclick=`、`onmouseover=`、`onfocus=`、`onblur=`、`onchange=`、`onsubmit=`、`onreset=`、`onkeydown=`、`onkeyup=`、`onkeypress=`、`ondblclick=`、`oncontextmenu=` 等所有 `on*=` 属性。

**无等号变体**：`<img onerror alert(1)>`、`<svg onload=alert(1)>` 等（`on*` 与值之间无等号，用空白或直接拼接）也属于危险模式。

---

## 二、危险标签（HTML）

`<script>`、`<svg>`、`<img>`、`<iframe>`、`<object>`、`<embed>`、`<applet>`、`<link>`、`<style>`、`<base>`、`<meta>`、`<math>`、`<body>`、`<frameset>`、`<frame>`、`<noscript>`、`<noframes>`、`<template>`、`<xml>`、`<blink>`、`<marquee>`

---

## 三、SVG/MathML 特殊向量

- `<svg onload=>`、`<svg><script>`、`<svg use>`
- `<math>`、`<maction>`、`<annotation-xml>`（MathML 内的 HTML 标签）
- `<svg><foreignObject><body onload=alert(1)>`（foreignObject 绕过）

---

## 四、危险协议

- `javascript:`、`vbscript:`、`livescript:`、`x-vrml:`
- `data:text/html`、`data:image/svg+xml`、`data:application/x-shockwave-flash`
- 协议后紧跟可执行内容：`href="javascript:`、`src="javascript:`、`data="javascript:` 后跟 `alert(`、`prompt(`、`confirm(`、`eval(`、`document.write(` 等

---

## 五、表达式注入

- `${}`、`<%= %>`、`<%- %>`、`{{}}`、`{``}`
- `expression(`、`-webkit-appearance:`（CSS 注入事件处理器）

---

## 六、属性注入

**危险属性**：`href`、`src`、`action`、`formaction`、`data`、`value`、`title`、`alt`、`name`、`id`（当这些属性可被用户输入控制时）

**危险值**：
- `style="behavior:`、`style="binding:`、`style="-moz-binding:`、`style="expression(`（IE 旧版本）

---

## 七、特殊向量

| 向量 | 说明 |
|------|------|
| `<base href=` + 外部域名 | base 标签劫持 |
| `srcdoc=`、`sandbox=` | iframe 变体 |
| `http-equiv="refresh"`、`content="0;url=` | meta 刷新重定向 |
| `opacity:0` + `z-index` | 点击劫持透明可点击元素 |
| `name=` 覆盖 `window.name` | DOM clobbering |

---

## 八、编码绕过

| 类型 | 模式 |
|------|------|
| HTML 实体编码 | `&#x` 十六进制、`&#` 十进制、`&#0;`（null byte 截断）、`&lt;` 等 |
| URL 编码 | `%3Cscript%3E` 等 |
| CSS 注释截断 | `/* */` |
| CSS 表达式 | `expression(this.style.cssText)`、`behavior:` 路径注入 |

---

## 九、动态导入/执行

`<script src=`、`new Function(`、`setTimeout(` 第一个参数为字符串、`eval(`、`Function(`、`uneval(`、`atob(`/`btoa(` 配合 `document.write(atob(...))`