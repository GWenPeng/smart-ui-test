"""Chat service - conversational test creation and execution."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.models import TestCase, TestStep, TestRun
from app.services.nl_parser import NLParser
from app.services.skill_manager import SkillManager
from app.services.test_executor import TestExecutor
from app.schemas.schemas import LogEntry


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.parser = NLParser()
        self.skill_mgr = SkillManager(db)

    async def handle_message(self, message: str, url: str = "", case_id: int = None) -> dict:
        """Handle a chat message and return response with logs."""
        logs = []
        reply_parts = []

        # Detect intent
        msg_lower = message.strip().lower()

        # ---- Create new test case ----
        if any(kw in msg_lower for kw in ["打开", "访问", "go to", "navigate", "open"]):
            if not url:
                # Try to extract URL from message
                import re
                url_match = re.search(r'(https?://\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}\S*)', message)
                if url_match:
                    url = url_match.group(0)
                    if not url.startswith("http"):
                        url = "https://" + url
                else:
                    return {
                        "reply": "请提供目标页面 URL，例如：`打开 https://baidu.com 搜索 mimo`",
                        "case_id": None,
                        "steps": None,
                        "log": [l.model_dump() for l in logs],
                    }

            # Parse steps
            skills = self.skill_mgr.get_matching_skills(url, logs)
            skills_ctx = self.skill_mgr.build_context(skills)
            steps = await self.parser.parse(message, url, skills_ctx, logs)

            if not steps:
                return {
                    "reply": "❌ 无法解析指令，请尝试更明确的描述，例如：\n- 打开百度搜索mimo\n- 点击登录按钮\n- 在用户名输入框输入 admin",
                    "case_id": None,
                    "steps": None,
                    "log": [l.model_dump() for l in logs],
                }

            # Create test case
            case = TestCase(
                name=f"聊天创建_{datetime.utcnow().strftime('%m%d_%H%M%S')}",
                description=message,
                target_url=url,
                natural_input=message,
                status="ready",
            )
            self.db.add(case)
            self.db.flush()

            # Create steps
            for i, step_data in enumerate(steps):
                step = TestStep(
                    case_id=case.id,
                    step_order=i + 1,
                    action=step_data.get("action", "click"),
                    target=step_data.get("target", ""),
                    value=step_data.get("value"),
                    locator_strategy=step_data.get("locator_strategy"),
                    locator_value=step_data.get("locator_value"),
                    iframe_hint=step_data.get("iframe_hint"),
                    timeout_ms=step_data.get("timeout_ms", 10000),
                    raw_text=step_data.get("raw_text", ""),
                    status="generated",
                )
                self.db.add(step)

            self.db.commit()

            # Build reply
            reply_parts.append(f"✅ 已创建测试用例 **#{case.id}**")
            reply_parts.append(f"📎 目标: `{url}`")
            reply_parts.append(f"\n📋 解析出 **{len(steps)}** 个步骤:\n")
            for i, s in enumerate(steps):
                icon = _action_icon(s.get("action", ""))
                iframe_tag = f" 📦iframe" if s.get("iframe_hint") else ""
                reply_parts.append(f"  {i+1}. {icon} **{s.get('action')}** → {s.get('target', '')}{iframe_tag}")
                if s.get("value"):
                    reply_parts.append(f"     值: `{s['value']}`")

            reply_parts.append(f"\n输入 `执行` 或 `运行` 来执行测试。")

            return {
                "reply": "\n".join(reply_parts),
                "case_id": case.id,
                "steps": steps,
                "log": [l.model_dump() for l in logs],
            }

        # ---- Execute test ----
        elif any(kw in msg_lower for kw in ["执行", "运行", "run", "execute", "测试"]):
            if not case_id:
                # Try to find latest case
                case = self.db.query(TestCase).order_by(TestCase.id.desc()).first()
                if not case:
                    return {
                        "reply": "❌ 没有找到测试用例，请先创建一个。例如：`打开 https://baidu.com 搜索 mimo`",
                        "case_id": None,
                        "steps": None,
                        "log": [l.model_dump() for l in logs],
                    }
                case_id = case.id
            else:
                case = self.db.query(TestCase).get(case_id)

            if not case:
                return {
                    "reply": f"❌ 测试用例 #{case_id} 不存在",
                    "case_id": None,
                    "steps": None,
                    "log": [l.model_dump() for l in logs],
                }

            # Create run record
            run = TestRun(case_id=case_id, status="queued")
            self.db.add(run)
            self.db.flush()

            # Execute
            executor = TestExecutor(self.db)
            result_run = await executor.run_test(case_id, run.id, logs)

            # Build result reply
            status_icon = {"passed": "🎉", "failed": "💥", "error": "⚠️"}.get(result_run.status, "❓")
            reply_parts.append(f"{status_icon} 测试 **{result_run.status.upper()}**")
            reply_parts.append(f"📊 耗时: {result_run.duration_ms}ms | 运行ID: #{run.id}")

            if result_run.step_results:
                reply_parts.append("\n📋 步骤详情:")
                for sr in sorted(result_run.step_results, key=lambda x: x.step_order):
                    icon = "✅" if sr.status == "passed" else "❌"
                    reply_parts.append(f"  {sr.step_order}. {icon} {sr.duration_ms}ms")
                    if sr.error_message:
                        reply_parts.append(f"     错误: {sr.error_message}")
                    if sr.screenshot_path:
                        reply_parts.append(f"     📸 截图: {sr.screenshot_path}")

            return {
                "reply": "\n".join(reply_parts),
                "case_id": case_id,
                "steps": None,
                "log": [l.model_dump() for l in logs],
                "run_id": run.id,
            }

        # ---- List cases ----
        elif any(kw in msg_lower for kw in ["列表", "list", "用例", "cases"]):
            cases = self.db.query(TestCase).order_by(TestCase.id.desc()).limit(10).all()
            if not cases:
                return {"reply": "📭 暂无测试用例", "case_id": None, "steps": None, "log": []}
            reply_parts.append("📋 **最近的测试用例:**\n")
            for c in cases:
                reply_parts.append(f"  #{c.id} | {c.name} | `{c.target_url}` | {c.status}")
            return {"reply": "\n".join(reply_parts), "case_id": None, "steps": None, "log": []}

        # ---- Help ----
        elif any(kw in msg_lower for kw in ["帮助", "help", "怎么用", "how"]):
            return {
                "reply": (
                    "🤖 **NL Test Framework 使用指南**\n\n"
                    "**创建测试:** 用自然语言描述你要测试的场景\n"
                    "  例: `打开 https://baidu.com 搜索 mimo 点击百度一下`\n\n"
                    "**执行测试:**\n"
                    "  输入 `执行` 运行最近创建的用例\n"
                    "  或 `执行 #123` 运行指定用例\n\n"
                    "**查看用例:**\n"
                    "  输入 `列表` 查看所有测试用例\n\n"
                    "**技能包:** 系统会自动加载匹配的技能包，提供领域知识辅助定位。"
                ),
                "case_id": None,
                "steps": None,
                "log": [],
            }

        # ---- Default: treat as test creation ----
        else:
            # Use URL from parameter or existing latest case
            if not url:
                latest = self.db.query(TestCase).order_by(TestCase.id.desc()).first()
                if latest:
                    url = latest.target_url

            if not url:
                return {
                    "reply": "请提供目标 URL，例如：`打开 https://baidu.com 搜索 mimo`",
                    "case_id": None, "steps": None, "log": [],
                }

            return await self.handle_message(f"打开 {url} {message}", url)


def _action_icon(action: str) -> str:
    icons = {
        "navigate": "🌐", "click": "👆", "fill": "✏️",
        "select": "📋", "check": "☑️", "hover": "🖱️",
        "wait": "⏳", "assert": "✔️", "scroll": "📜",
        "screenshot": "📸",
    }
    return icons.get(action, "▶")
