# NL Test Framework - 部署文档

## 1. 环境要求

| 组件         | 最低版本        | 说明                       |
|-------------|----------------|---------------------------|
| Docker      | 24.0+          | 容器化部署                 |
| Docker Compose | 2.20+        | 编排服务                   |
| 内存         | 2GB+          | Playwright 浏览器较耗内存   |
| 磁盘         | 5GB+          | 含浏览器、截图、报告        |

或本地开发：
| 组件         | 版本            |
|-------------|----------------|
| Python      | 3.11+          |
| MySQL       | 8.0+           |
| Node.js     | 18+ (可选，前端开发) |

---

## 2. 快速部署 (Docker Compose 推荐)

### 2.1 克隆项目

```bash
cd nl-test-framework
```

### 2.2 配置环境变量

```bash
cat > .env << 'EOF'
# LLM API 配置 (必填)
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

# 仅看 MySQL
docker compose logs -f mysql
```

### 2.5 停止服务

```bash
docker compose down

# 清理数据卷（会删除所有数据）
docker compose down -v
```

---

## 3. 本地开发部署

### 3.1 安装 MySQL

```bash
# Ubuntu/Debian
sudo apt install mysql-server
sudo systemctl start mysql

# macOS
brew install mysql
brew services start mysql

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

### 3.2 安装后端依赖

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
playwright install-deps chromium
```

### 3.3 配置环境变量

```bash
cat > .env << 'EOF'
DATABASE_URL=mysql+pymysql://nltest:nltest123@localhost:3306/nl_test
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
SCREENSHOT_DIR=./screenshots
EOF
```

### 3.4 启动后端

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3.5 打开前端

直接用浏览器打开 `frontend/index.html`，或用 HTTP 服务器：

```bash
cd frontend
python3 -m http.server 3000
# 访问 http://localhost:3000
```

> **注意**: 前端需要能访问后端 API。如果前端和后端不在同一端口，
> 需要修改 `index.html` 中的 `API` 变量。

---

## 4. 使用指南

### 4.1 基本操作

1. 在顶部输入框填写目标 URL（默认 `https://www.baidu.com`）
2. 在聊天框输入自然语言指令，例如：
   - `打开百度搜索mimo点击百度一下`
   - `在搜索框输入 python 教程 然后点击搜索`
   - `打开 https://example.com 点击登录按钮`
3. 系统解析后展示步骤列表
4. 输入 `执行` 运行测试
5. 右侧面板查看实时日志

### 4.2 技能包使用

技能包自动匹配 URL，无需手动加载。系统预置了：
- **百度搜索**: 百度首页的搜索框/按钮定位
- **通用等待规则**: 页面加载等待策略

点击左下角「技能包管理」查看已有技能。

### 4.3 添加自定义技能包

通过 API 或数据库直接添加：

```bash
curl -X POST http://localhost:8000/api/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的登录页",
    "description": "登录页元素定位规则",
    "category": "page",
    "url_pattern": "*myapp.com/login*",
    "rules": {
      "username": {"strategy": "label", "value": "用户名"},
      "password": {"strategy": "label", "value": "密码"},
      "submit": {"strategy": "text", "value": "登录"},
      "iframe_login": {"name": "login-frame", "description": "登录表单在iframe内"}
    },
    "priority": 10
  }'
```

### 4.4 iframe 测试示例

当页面元素在 iframe 内时，系统会自动遍历。也可以通过技能包提示：

```json
{
  "name": "iframe 测试页",
  "category": "iframe",
  "url_pattern": "*example.com/embed*",
  "rules": {
    "payment_form": {
      "iframe_name": "payment-frame",
      "iframe_src_contains": "payment",
      "description": "支付表单在名为 payment-frame 的 iframe 内"
    }
  }
}
```

---

## 5. API 参考

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
| WS     | `/api/ws/logs`       | 实时日志推送   |

---

## 6. 常见问题

### Q: Playwright 浏览器启动失败
```bash
# 安装系统依赖
playwright install-deps chromium
# 或在 Docker 中确保使用完整镜像
```

### Q: MySQL 连接失败
```bash
# 检查 MySQL 是否启动
systemctl status mysql
# 检查连接字符串
echo $DATABASE_URL
```

### Q: LLM 解析不准确
- 检查技能包是否正确匹配 URL
- 尝试更明确的描述（指定元素类型：按钮、输入框、链接）
- 调整 `OPENAI_MODEL` 使用更强的模型

### Q: 截图未生成
- 检查 `SCREENSHOT_DIR` 目录权限
- 确保 Docker 挂载了截图卷
