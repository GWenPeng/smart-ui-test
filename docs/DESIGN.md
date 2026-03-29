# NL Test Framework - 设计方案文档

## 1. 项目概述

NL Test Framework 是一个**自然语言驱动的智能自动化测试平台**。用户通过对话式界面输入自然语言描述的测试场景，系统自动解析为结构化测试步骤，并在真实浏览器中执行，支持复杂的 iframe 嵌套定位和弹窗自动处理。

### 核心特性

- 🗣️ **自然语言输入** — 用中文描述测试场景，AI 自动解析
- 📦 **iframe 智能切换** — 自动扫描、遍历嵌套 iframe，无需手动切换
- 🧩 **技能包系统** — 预定义领域知识（弹窗处理、元素定位、等待规则、UA 伪装）
- 🛡️ **弹窗自动处理** — Cookie 同意、登录弹窗、模态框等自动识别并关闭
- 💪 **元素容错降级** — normal → force → JS 三级点击/输入降级链
- 💬 **对话式交互** — 类 ChatGPT 界面，实时反馈
- 📋 **详细执行日志** — 每步操作的定位过程、iframe 路径、耗时等
- 📸 **失败截图** — 自动截取失败步骤的页面截图
- 📊 **可视化报告** — 精美的 HTML 测试报告

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 SPA)                       │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ 用例列表  │  │  对话式聊天界面   │  │  实时日志面板  │  │
│  └──────────┘  └──────────────────┘  └───────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API + WebSocket
┌───────────────────────┴─────────────────────────────────┐
│                 后端 (FastAPI)                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Chat API   │  │  NL Parser   │  │ Skill Manager  │  │
│  │  对话路由    │  │  自然语言解析  │  │  技能包管理     │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
│  ┌──────┴────────────────┴───────────────────┴────────┐  │
│  │            Test Executor (Playwright)               │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │Ifm Explorer  │  │Smart Locator │  │ Skill    │  │  │
│  │  │ iframe扫描器  │  │ 智能元素定位  │  │ Executor │  │  │
│  │  └──────────────┘  └──────────────┘  │ 技能执行  │  │  │
│  │  ┌──────────────┐  ┌──────────────┐  └──────────┘  │  │
│  │  │Popup Dismiss │  │Force Fallback│                │  │
│  │  │ 弹窗自动关闭  │  │ 容错降级链   │                │  │
│  │  └──────────────┘  └──────────────┘  ┌──────────┐  │  │
│  │                                      │ Reporter │  │  │
│  │                                      │ 报告生成  │  │  │
│  │                                      └──────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────┐
│               MySQL / SQLite 数据库                      │
│  test_cases │ test_steps │ test_runs │ step_results      │
│  skills │ iframe_cache                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 技术栈

| 层       | 技术                        | 说明                              |
|----------|-----------------------------|-----------------------------------|
| 前端     | Vue 3 + 原生 CSS            | 轻量 SPA，无需构建                |
| 后端     | FastAPI + Uvicorn           | 异步高性能 Web 框架               |
| 浏览器引擎 | Playwright (Python)        | 比 Selenium 更优雅的 iframe 处理  |
| AI 解析  | OpenAI API (兼容接口)       | 自然语言 → 结构化步骤             |
| 数据库   | MySQL 8.0 / SQLite          | 测试用例、步骤、运行记录持久化     |
| 容器化   | Docker Compose             | 一键部署                          |

---

## 4. 核心模块设计

### 4.1 自然语言解析器 (NL Parser)

```
用户输入: "打开百度搜索mimo点击百度一下"
    ↓
LLM Prompt (含技能包上下文)
    ↓
[
  {"action": "navigate", "target": "https://www.baidu.com"},
  {"action": "fill", "target": "搜索框", "value": "mimo", "locator_strategy": "id", "locator_value": "kw"},
  {"action": "click", "target": "百度一下按钮", "locator_strategy": "id", "locator_value": "su"}
]
```

**设计要点:**
- System Prompt 定义严格的 JSON 输出格式
- 温度设为 0.1 保证输出稳定性
- 注入匹配的技能包作为上下文，提高解析准确度

### 4.2 iframe 智能定位引擎

```
定位元素流程:
1. 在主页面尝试定位 → 找到？→ 返回
2. 扫描所有 iframe，构建层级树
3. 如有 iframe_hint → 仅在匹配的 iframe 中搜索
4. 否则遍历每个 frame，尝试定位 → 找到？→ 返回 iframe 路径
5. 深度遍历（递归子 frame）
6. 全部未找到 → 报错
```

**iframe 遍历算法:**
- 递归扫描 `frame.child_frames`
- 在每个 frame context 中调用 `build_locator(frame, strategy, value)`
- 记录从 main → 目标 frame 的完整路径
- 支持按 name、index、URL 多种方式定位 iframe

### 4.3 技能包系统 (Skills)

技能包是**领域知识的载体**，存储在数据库中，按 URL glob 模式匹配。执行器在运行时加载匹配的技能包，自动应用其中的规则。

#### 技能类型总览

| 类型       | 用途                         | 示例                                       |
|------------|------------------------------|--------------------------------------------|
| `page`     | 页面级元素映射 + 弹窗处理    | 百度搜索框/按钮定位、Cookie弹窗关闭规则      |
| `element`  | 元素级定位与容错规则         | 不可见元素的 force-click 降级策略           |
| `flow`     | 常见操作流程                 | 登录流程 = 输入账号 → 输入密码 → 点击登录   |
| `iframe`   | iframe 结构映射              | 某页面的支付模块在 iframe `payment-frame`   |
| `wait`     | 等待规则 + 通用弹窗处理      | networkidle 等待、Cookie 同意关键词匹配     |

#### 默认技能包列表

启动时自动 seed 以下技能包：

**1. 百度弹窗处理 (优先级 20, page)**
```yaml
URL模式: *baidu.com*
功能:
  - pre_navigate: 设置 Chrome UA 伪装，避免触发弹窗
  - post_load: JS 隐藏所有 pop/dialog/modal/mask/overlay/cookie/passport 元素
  - iframe_check: 逐 frame 清理弹窗
  - click_hints: 启用 force click 绕过遮挡
  - dismiss_selectors: 接受按钮、关闭按钮等候选选择器
```

**2. 百度搜索 (优先级 10, page)**
```yaml
URL模式: *baidu.com*
功能:
  - 搜索框: #kw
  - 搜索按钮: #su
  - 第一条结果: #content_left .result h3 a
  - 相关搜索: #rs a
  - 等待规则: 搜索后等待 #content_left 出现
```

**3. 不可见元素处理 (优先级 5, element)**
```yaml
URL模式: *
功能:
  - force_click: normal → JS click → force click 三级降级
  - force_fill: normal → JS set_value → force fill 三级降级
  - visibility_timeout: 5000ms 后自动切换 force 模式
```

**4. 通用弹窗处理 (优先级 1, wait)**
```yaml
URL模式: *
功能:
  - cookie_consent_keywords: 接受、同意、Accept、Agree、Got it 等
  - dismiss_strategies: 按优先级尝试 text_click → css_dismiss → js_force_dismiss
  - cross_iframe: 弹窗可能在 iframe 中，逐 frame 处理
```

**5. 通用等待规则 (优先级 1, wait)**
```yaml
URL模式: *
功能:
  - page_load: networkidle 等待，超时 15s
  - input_focus: 输入前等待元素可见，超时 5s
```

#### 技能包注入流程

```
1. 收到用户消息 + 目标URL
2. 查询所有 enabled 的技能，按 URL glob 匹配
3. 将匹配的技能规则格式化为 LLM 上下文
4. 注入到 NL Parser 的 prompt 中
5. LLM 解析时参考技能包，生成更准确的定位策略
6. TestExecutor 加载同一组技能，执行时自动应用
```

#### 技能包在执行器中的应用

```
TestExecutor.run_test()
  ├── 1. SkillManager.get_matching_skills(url) → 加载匹配的技能
  ├── 2. _get_custom_ua() → 从技能中读取 UA 伪装
  ├── 3. _should_use_force() → 检查是否启用 force 模式
  │
  ├── navigate 步骤执行后:
  │   └── _dismiss_popups(page)
  │       ├── 遍历技能中的 post_load_actions
  │       ├── 执行 JS 隐藏弹窗
  │       ├── 尝试 text_click 关闭
  │       ├── 尝试 css_dismiss 关闭
  │       └── 逐 iframe 清理
  │
  └── click/fill 步骤执行时:
      ├── 先尝试 normal click/fill
      ├── 超时或不可见 → force click/fill
      └── 仍失败 → JS dispatch_event / set_value
```

### 4.4 容错降级链 (Force Fallback)

当元素存在但不可见（被弹窗/遮罩遮挡）时，执行器自动降级：

```
┌─────────────────────────────────────────────┐
│              Click 降级链                     │
│                                             │
│  normal click (3s)                          │
│      ↓ 失败 / 不可见                        │
│  force click (跳过可见性检查)                │
│      ↓ 失败                                 │
│  JS dispatch_event("click")                 │
│      ↓ 仍失败                               │
│  ❌ 抛出异常                                │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│              Fill 降级链                      │
│                                             │
│  normal click + fill (3s)                   │
│      ↓ 失败 / 不可见                        │
│  force click + force fill                   │
│      ↓ 失败                                 │
│  JS el.value = ... + dispatchEvent          │
│      ↓ 仍失败                               │
│  ❌ 抛出异常                                │
└─────────────────────────────────────────────┘
```

### 4.5 数据库设计

```
test_cases (测试用例)
  ├── id, name, description, target_url, natural_input, status
  └── has_many → test_steps

test_steps (测试步骤)
  ├── id, case_id, step_order, action, target, value
  ├── locator_strategy, locator_value, iframe_hint
  └── has_many → step_results

test_runs (测试运行)
  ├── id, case_id, status, started_at, finished_at, duration_ms
  └── has_many → step_results

step_results (步骤结果)
  ├── id, run_id, step_id, status, duration_ms
  ├── error_message, screenshot_path, iframe_path (JSON)
  └── element_info (JSON)

skills (技能包)
  ├── id, name, category (page|element|flow|iframe|wait)
  ├── url_pattern, rules (JSON), priority, enabled
  └── 支持: 元素映射、弹窗规则、UA伪装、降级策略

iframe_cache (iframe结构缓存)
  └── url_pattern, iframe_tree (JSON)
```

---

## 5. 交互流程

```
用户: "打开 https://baidu.com 搜索 mimo 点击百度一下"
  ↓
Chat API 接收
  ↓
SkillManager 匹配 URL → 获取技能包 (百度弹窗处理 + 百度搜索 + 通用规则)
  ↓
NLParser 解析 (注入技能上下文) → 3个步骤
  ↓
创建 TestCase + TestSteps (写入数据库)
  ↓
返回步骤列表给前端
  ↓
用户: "执行"
  ↓
TestExecutor 执行 (技能增强):
  ├─ 加载技能包: UA伪装 + 弹窗规则 + force降级
  ├─ 步骤1: navigate → baidu.com
  │   └─ 自动执行: 🧹 弹窗清理 (JS隐藏 + iframe清理)
  ├─ 步骤2: fill "mimo" in #kw
  │   ├─ 日志: 🔎 定位元素: 搜索框 (visible=True)
  │   └─ 日志: ✏️ 输入: mimo
  ├─ 步骤3: click #su
  │   ├─ 如果 visible=False → 自动 force click
  │   └─ 日志: 👆 Force点击
  └─ 截图: final.png
  ↓
返回执行结果 + 日志 + 截图路径
  ↓
前端实时展示日志、结果
```

---

## 6. 自定义技能包

通过 API 或数据库添加自定义技能包：

### 示例: 登录页弹窗处理

```json
{
  "name": "我的登录页",
  "description": "登录页元素定位和弹窗处理",
  "category": "page",
  "url_pattern": "*myapp.com/login*",
  "rules": {
    "username": {"strategy": "label", "value": "用户名"},
    "password": {"strategy": "label", "value": "密码"},
    "submit": {"strategy": "text", "value": "登录"},
    "post_load_actions": [
      {
        "type": "js_dismiss",
        "selectors": ["[class*='promo']", ".ad-banner"],
        "description": "隐藏推广弹窗"
      }
    ],
    "dismiss_selectors": [".close-btn", "button:has-text('关闭')"],
    "iframe_check": true
  },
  "priority": 10
}
```

### 示例: iframe 密集型页面

```json
{
  "name": "iframe密集页面",
  "category": "iframe",
  "url_pattern": "*example.com/dashboard*",
  "rules": {
    "payment_form": {
      "iframe_name": "payment-frame",
      "iframe_src_contains": "payment",
      "description": "支付表单在 iframe 内"
    },
    "iframe_check": true
  },
  "priority": 10
}
```

---

## 7. 测试用例编写

### 独立测试脚本

不依赖 LLM API，直接构造步骤执行。参考 `test_baidu_mimo_click.py`：

```python
from app.services.test_executor import TestExecutor

# 1. 创建测试用例和步骤
case = TestCase(name="...", target_url="https://...")
steps = [
    TestStep(action="navigate", target="https://..."),
    TestStep(action="fill", target="搜索框", locator_strategy="id",
             locator_value="kw", value="关键词"),
    TestStep(action="click", target="搜索按钮", locator_strategy="id",
             locator_value="su"),
    TestStep(action="screenshot", target="结果页"),
]

# 2. 用 TestExecutor 执行（自动加载技能包）
executor = TestExecutor(db)
run = await executor.run_test(case_id, run_id, logs)
```

执行器会自动：
- 加载匹配目标 URL 的技能包
- 导航后执行弹窗清理
- 元素不可见时自动降级到 force 模式
- 失败时截图

---

## 8. 安全设计

- LLM API Key 通过环境变量注入，不存数据库
- 脚本执行在 Playwright 沙箱浏览器中，隔离于宿主
- 截图存储在受控目录，不对外暴露文件系统
- 前后端 CORS 受控，生产环境应限制 origin
- 数据库无敏感数据，仅存储测试元信息
