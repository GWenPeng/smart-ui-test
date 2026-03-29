# NL Test Framework - 部署文档

## 1. 环境要求

### Docker 部署（推荐）

| 组件         | 最低版本        | 说明                       |
|-------------|----------------|---------------------------|
| Docker      | 24.0+          | 容器化部署                 |
| Docker Compose | 2.20+        | 编排服务                   |
| 内存         | 2GB+          | Playwright 浏览器较耗内存   |
| 磁盘         | 5GB+          | 含浏览器、截图、报告        |

### 本地开发

| 组件         | 版本            | 说明                          |
|-------------|----------------|-------------------------------|
| Python      | 3.11+          | 后端运行环境                   |
| MySQL       | 8.0+           | 可选，默认使用 SQLite           |
| Node.js     | 18+            | 可选，仅前端开发需要            |

---

## 2. 快速部署 (Docker Compose 推荐)

### 2.1 克隆项目

```bash
git clone https://github.com/GWenPeng/smart-ui-test.git
cd smart-ui-test
```

### 2.2 配置环境变量

```bash
cat > .env << 'EOF'
# LLM API 配置 (对话模式必填，独立测试脚本不需要)
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# 可选: 使用兼容 OpenAI 的其他服务
# OPENAI_BASE_URL=https://your-proxy.com/v1
# OPENAI_MODEL=deepseek-chat
EOF
```

### 2.3 启动服务

```bash
cd docker
docker compose up -d --build
```

启动后：
- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **MySQL**: localhost:3306

### 2.4 查看日志

```bash
# 查看所有服务日志
docker compose logs -f

# 仅看后端
docker compose logs -f backend
```

### 2.5 停止服务

```bash
docker compose down

# 清理数据卷（会删除所有数据）
docker compose down -v
```

---

## 3. 本地开发部署

### 3.1 安装依赖

```bash
# Python 依赖（如使用系统 Python 需 --break-system-packages）
pip install -r backend/requirements.txt --break-system-packages

# Playwright 浏览器
playwright install chromium
playwright install-deps chromium
```

### 3.2 数据库配置

**方式一: SQLite（默认，无需额外安装）**

默认配置已使用 SQLite，存储在 `/tmp/nl_test.db`。无需任何配置即可运行。

**方式二: MySQL（生产推荐）**

```bash
# Ubuntu/Debian
sudo apt install mysql-server
sudo systemctl start mysql

# 创建数据库
mysql -u root -p << 'SQL'
CREATE DATABASE nl_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'nltest'@'localhost' IDENTIFIED BY 'nltest123';
GRANT ALL ON nl_test.* TO 'nltest'@'localhost';
FLUSH PRIVILEGES;
SQL

# 导入表结构
mysql -u nltest -pnltest123 nl_test < docker/init.sql
```

配置 MySQL 连接：

```bash
cat > backend/.env << 'EOF'
DATABASE_URL=mysql+pymysql://nltest:nltest123@localhost:3306/nl_test
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
SCREENSHOT_DIR=./screenshots
EOF
```

### 3.3 启动后端

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3.4 打开前端

直接用浏览器打开 `frontend/index.html`，或用 HTTP 服务器：

```bash
cd frontend
python3 -m http.server 3000
# 访问 http://localhost:3000
```

> **注意**: 前端需要能访问后端 API。如果前端和后端不在同一端口，
> 需要修改 `index.html` 中的 `API` 变量。

---

## 4. 独立测试脚本（无需 LLM API）

项目支持不依赖 LLM API 的独立测试脚本，直接构造测试步骤执行。

### 4.1 运行示例测试

```bash
cd smart-ui-test
python3 test_baidu_mimo_click.py
```

该脚本会：
1. 初始化数据库（默认 SQLite）
2. 自动 seed 默认技能包
3. 创建百度搜索测试用例（9 步骤）
4. 用 TestExecutor 执行，自动加载技能包
5. 生成 HTML 测试报告

### 4.2 编写自己的测试脚本

```python
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.database import Base, engine, SessionLocal
from app.models.models import TestCase, TestStep, TestRun
from app.services.skill_manager import SkillManager
from app.services.test_executor import TestExecutor
from app.services.report_generator import ReportGenerator

def setup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    SkillManager(db).seed_default_skills()
    db.close()

async def run():
    db = SessionLocal()

    # 创建用例
    case = TestCase(
        name="我的测试",
        target_url="https://example.com",
        natural_input="打开页面，点击登录",
        status="ready",
    )
    db.add(case)
    db.flush()

    # 创建步骤
    for i, (action, target, strategy, locator, value) in enumerate([
        ("navigate", "https://example.com", None, None, None),
        ("wait", "3000", None, None, None),
        ("click", "登录按钮", "text", "登录", None),
        ("screenshot", "结果页", None, None, None),
    ], 1):
        db.add(TestStep(
            case_id=case.id, step_order=i,
            action=action, target=target,
            locator_strategy=strategy, locator_value=locator,
            value=value, raw_text=target, status="generated",
        ))

    db.commit()

    # 执行（自动加载技能包）
    run = TestRun(case_id=case.id, status="queued")
    db.add(run)
    db.flush()

    logs = []
    executor = TestExecutor(db)
    result = await executor.run_test(case.id, run.id, logs)

    # 生成报告
    report = ReportGenerator(db).save_report(run.id)
    print(f"结果: {result.status}, 报告: {report}")
    db.close()

if __name__ == "__main__":
    setup()
    asyncio.run(run())
```

### 4.3 技能包自动生效

TestExecutor 在执行时会自动：

1. **加载技能包** — 按目标 URL 匹配所有 enabled 的技能
2. **UA 伪装** — 从技能中读取自定义 User-Agent
3. **弹窗清理** — 导航后自动执行 JS 隐藏 + CSS 点击 + iframe 清理
4. **容错降级** — 元素不可见时自动从 normal → force → JS 降级

---

## 5. 使用指南（对话模式）

### 5.1 基本操作

1. 在顶部输入框填写目标 URL（默认 `https://www.baidu.com`）
2. 在聊天框输入自然语言指令，例如：
   - `打开百度搜索mimo点击百度一下`
   - `在搜索框输入 python 教程 然后点击搜索`
   - `打开 https://example.com 点击登录按钮`
3. 系统解析后展示步骤列表
4. 输入 `执行` 运行测试
5. 右侧面板查看实时日志

### 5.2 默认技能包

系统预置了 5 个技能包，启动时自动 seed：

| 技能包             | 类型     | 优先级 | 作用                         |
|-------------------|----------|--------|------------------------------|
| 百度弹窗处理       | page     | 20     | UA伪装 + JS隐藏弹窗 + force降级 |
| 百度搜索           | page     | 10     | 搜索框/按钮/结果页元素映射      |
| 不可见元素处理     | element  | 5      | normal → force → JS 三级降级   |
| 通用弹窗处理       | wait     | 1      | Cookie同意关键词 + CSS关闭     |
| 通用等待规则       | wait     | 1      | networkidle + 元素可见等待     |

点击左下角「技能包管理」查看已有技能。

### 5.3 添加自定义技能包

#### 通过 API

```bash
curl -X POST http://localhost:8000/api/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的登录页",
    "description": "登录页弹窗处理和元素定位",
    "category": "page",
    "url_pattern": "*myapp.com/login*",
    "rules": {
      "username": {"strategy": "label", "value": "用户名"},
      "password": {"strategy": "label", "value": "密码"},
      "submit": {"strategy": "text", "value": "登录"},
      "post_load_actions": [
        {
          "type": "js_dismiss",
          "selectors": ["[class*=\"promo\"]", ".ad-banner"],
          "description": "隐藏推广弹窗"
        }
      ],
      "dismiss_selectors": [".close-btn", "button:has-text(\"关闭\")"]
    },
    "priority": 10
  }'
```

#### 通过代码

在 `SkillManager.seed_default_skills()` 中添加新的技能 dict。

---

## 6. API 参考

启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

主要端点:

| 方法   | 路径                  | 说明           |
|--------|----------------------|----------------|
| POST   | `/api/chat`          | 对话式交互     |
| GET    | `/api/cases`         | 列出测试用例   |
| POST   | `/api/cases`         | 创建测试用例   |
| POST   | `/api/runs`          | 执行测试       |
| GET    | `/api/runs`          | 列出运行记录   |
| GET    | `/api/reports/{id}`  | 查看测试报告   |
| GET    | `/api/skills`        | 列出技能包     |
| POST   | `/api/skills`        | 创建技能包     |
| POST   | `/api/skills/seed`   | 重新 seed 默认技能包 |
| WS     | `/api/ws/logs`       | 实时日志推送   |

---

## 7. 常见问题

### Q: Playwright 浏览器启动失败
```bash
# 安装系统依赖
playwright install-deps chromium
# 或在 Docker 中确保使用完整镜像
```

### Q: 元素被弹窗遮挡，提示 not visible
系统会自动处理：
- 技能包中配置了弹窗清理规则，导航后自动执行
- 元素不可见时自动降级到 force click / JS click
- 如果仍失败，检查技能包是否匹配了目标 URL

### Q: 新网站弹窗无法自动关闭
添加自定义技能包，配置 `post_load_actions` 和 `dismiss_selectors`。
参考「百度弹窗处理」技能包的配置格式。

### Q: MySQL 连接失败
```bash
# 检查 MySQL 是否启动
systemctl status mysql
# 检查连接字符串
echo $DATABASE_URL
# 或使用默认 SQLite（无需配置）
```

### Q: LLM 解析不准确
- 检查技能包是否正确匹配 URL（技能包上下文会注入 LLM prompt）
- 尝试更明确的描述（指定元素类型：按钮、输入框、链接）
- 调整 `OPENAI_MODEL` 使用更强的模型

### Q: 截图未生成
- 检查 `SCREENSHOT_DIR` 目录权限
- 确保 Docker 挂载了截图卷
- 默认路径: `./screenshots/`

### Q: 独立脚本报 DetachedInstanceError
在访问 ORM 属性前确保 session 未关闭：
```python
status = result_run.status  # 先读属性
db.close()                  # 再关闭 session
```
