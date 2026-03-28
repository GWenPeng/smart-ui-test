# NL Test Framework - 设计方案文档

## 1. 项目概述

NL Test Framework 是一个**自然语言驱动的智能自动化测试平台**。用户通过对话式界面输入自然语言描述的测试场景，系统自动解析为结构化测试步骤，并在真实浏览器中执行，支持复杂的 iframe 嵌套定位。

### 核心特性

- 🗣️ **自然语言输入** — 用中文描述测试场景，AI 自动解析
- 📦 **iframe 智能切换** — 自动扫描、遍历嵌套 iframe，无需手动切换
- 🧩 **技能包系统** — 预定义领域知识（等待规则、iframe映射、元素定位）
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
│  │              Test Executor (Playwright)             │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │ IframeExplorer│  │Smart Locator │  │ Reporter │  │  │
│  │  │  iframe扫描器  │  │ 智能元素定位  │  │ 报告生成  │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────┐
│                   MySQL 数据库                            │
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
| 数据库   | MySQL 8.0                  | 测试用例、步骤、运行记录持久化     |
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

技能包是**领域知识的载体**，存储在 MySQL 中，按 URL 模式匹配。

**五种技能类型:**

| 类型     | 用途                         | 示例                                     |
|----------|------------------------------|------------------------------------------|
| `page`   | 页面级元素映射               | 百度搜索框 = `#kw`, 搜索按钮 = `#su`     |
| `element`| 特定元素的定位规则           | 某登录页的用户名框使用 label 定位         |
| `flow`   | 常见操作流程                 | 登录流程 = 输入账号 → 输入密码 → 点击登录 |
| `iframe` | iframe 结构映射              | 某页面的支付模块在 iframe `payment-frame` |
| `wait`   | 等待规则                     | 搜索后等待 `#content_left` 出现           |

**技能包注入流程:**
```
1. 收到用户消息 + 目标URL
2. 查询所有 enabled 的技能，按 URL glob 匹配
3. 将匹配的技能规则格式化为 LLM 上下文
4. 注入到 NL Parser 的 prompt 中
5. LLM 解析时参考技能包，生成更准确的定位策略
```

### 4.4 数据库设计

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
  ├── id, name, category, url_pattern
  └── rules (JSON)

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
SkillManager 匹配 URL → 获取"百度搜索"技能包
  ↓
NLParser 解析 (注入技能上下文) → 3个步骤
  ↓
创建 TestCase + TestSteps (写入MySQL)
  ↓
返回步骤列表给前端
  ↓
用户: "执行"
  ↓
TestExecutor 执行:
  ├─ 步骤1: navigate → baidu.com
  │   └─ 日志: 🌐 导航到 https://baidu.com
  ├─ 步骤2: fill "mimo" in #kw
  │   ├─ 日志: 🔎 定位元素: 搜索框
  │   ├─ 日志: ✅ 在主页面找到元素 (strategy=id, value=kw)
  │   └─ 日志: ✏️ 输入: mimo
  ├─ 步骤3: click #su
  │   ├─ 日志: 🔎 定位元素: 百度一下按钮
  │   └─ 日志: 👆 点击
  └─ 截图: final.png
  ↓
返回执行结果 + 日志 + 截图路径
  ↓
前端实时展示日志、结果
```

---

## 6. 安全设计

- LLM API Key 通过环境变量注入，不存数据库
- 脚本执行在 Playwright 沙箱浏览器中，隔离于宿主
- 截图存储在受控目录，不对外暴露文件系统
- 前后端 CORS 受控，生产环境应限制 origin
- 数据库无敏感数据，仅存储测试元信息
