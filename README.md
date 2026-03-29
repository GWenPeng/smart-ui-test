# 🧪 NL Test Framework

**自然语言驱动的智能自动化测试平台** — 用中文描述测试场景，AI 自动解析并执行。

## 核心特性

- 🗣️ **自然语言输入** — `打开百度搜索mimo点击百度一下`，AI 自动解析为结构化步骤
- 🛡️ **弹窗自动处理** — Cookie 同意、登录弹窗、模态框自动识别并关闭
- 📦 **iframe 智能切换** — 自动扫描、遍历嵌套 iframe
- 💪 **容错降级** — 元素不可见时 normal → force → JS 三级降级
- 🧩 **技能包系统** — 预定义领域知识，按 URL 自动匹配
- 📊 **可视化报告** — 精美 HTML 报告 + 失败截图

## 快速开始

### Docker 部署（推荐）

```bash
# 配置环境变量
cat > .env << 'EOF'
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
EOF

# 启动
cd docker && docker compose up -d --build
```

- 前端: http://localhost:3000
- API: http://localhost:8000
- 文档: http://localhost:8000/docs

### 本地运行（独立测试，无需 LLM）

```bash
pip install -r backend/requirements.txt --break-system-packages
playwright install chromium && playwright install-deps chromium

# 运行百度搜索测试
python3 test_baidu_mimo_click.py
```

## 项目结构

```
smart-ui-test/
├── frontend/
│   └── index.html              # Vue 3 SPA（聊天界面）
├── backend/
│   └── app/
│       ├── main.py             # FastAPI 入口
│       ├── api/routes.py       # REST API + WebSocket
│       ├── core/               # 配置 + 数据库
│       ├── models/             # ORM 模型
│       ├── schemas/            # Pydantic 请求/响应
│       └── services/
│           ├── chat_service.py     # 对话路由（意图识别）
│           ├── nl_parser.py        # LLM 自然语言解析
│           ├── test_executor.py    # 测试执行器（技能增强）
│           ├── locator.py          # 智能元素定位 + iframe 遍历
│           ├── skill_manager.py    # 技能包管理
│           └── report_generator.py # HTML 报告生成
├── docker/                     # Docker Compose + MySQL
├── test_baidu_mimo_click.py    # 示例测试脚本
└── docs/                       # 设计文档 + 部署文档
```

## 技能包

系统预置 5 个默认技能包：

| 技能包 | 类型 | 作用 |
|--------|------|------|
| 百度弹窗处理 | page | UA伪装 + JS隐藏弹窗 + force降级 |
| 百度搜索 | page | 搜索框/按钮/结果页元素映射 |
| 不可见元素处理 | element | normal → force → JS 三级降级 |
| 通用弹窗处理 | wait | Cookie同意关键词 + CSS关闭 |
| 通用等待规则 | wait | networkidle + 元素可见等待 |

详见 [设计文档](docs/DESIGN.md)。

## 文档

- [设计方案](docs/DESIGN.md) — 架构、模块设计、技能包系统
- [部署文档](docs/DEPLOY.md) — 安装、配置、使用指南、常见问题

## License

MIT
