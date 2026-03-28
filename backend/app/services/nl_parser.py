"""LLM-based natural language parser with skill injection."""
import json
from openai import AsyncOpenAI
from app.core.config import settings
from app.schemas.schemas import LogEntry

SYSTEM_PROMPT = """你是一个自动化测试指令解析器。将用户的自然语言描述解析为结构化的测试步骤。

## 输出格式
输出严格的 JSON 数组，每个元素：
{
  "action": "click|fill|select|check|hover|navigate|wait|assert|scroll|screenshot",
  "target": "元素的自然语言描述",
  "value": "填充值（fill/select时必须）",
  "locator_strategy": "role|text|label|placeholder|test_id|css|xpath|title|alt_text",
  "locator_value": "定位表达式",
  "iframe_hint": "iframe描述（如果元素在iframe内）",
  "timeout_ms": 10000,
  "raw_text": "原始输入片段"
}

## 规则
1. navigate 动作不需要 locator，target 字段放 URL
2. wait 动作的 target 放等待条件描述
3. assert 动作的 target 放断言条件，value 放期望值
4. 如果用户提到 iframe/弹窗/嵌套页面，设置 iframe_hint
5. 优先使用 role、text、label 等语义化定位策略
6. 每一步尽量拆细，一个动作一个步骤
7. 只输出 JSON，不要任何解释"""


class NLParser:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

    async def parse(
        self,
        user_input: str,
        url: str = "",
        skills_context: str = "",
        logs: list = None,
    ) -> list[dict]:
        if logs is None:
            logs = []

        # Build context with skills
        user_message = f"目标页面: {url}\n\n用户指令:\n{user_input}"
        if skills_context:
            user_message += f"\n\n## 已加载的领域知识（技能包）\n{skills_context}"

        logs.append(LogEntry(
            timestamp=self._ts(),
            level="info",
            message="🧠 开始解析自然语言指令...",
            detail={"input": user_input, "url": url},
        ))

        if skills_context:
            logs.append(LogEntry(
                timestamp=self._ts(),
                level="debug",
                message="📦 已注入技能包上下文",
                detail={"skills": skills_context[:500]},
            ))

        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=4096,
            )

            content = response.choices[0].message.content.strip()
            # Extract JSON from possible markdown code block
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[: content.rfind("```")]

            steps = json.loads(content)

            logs.append(LogEntry(
                timestamp=self._ts(),
                level="info",
                message=f"✅ 解析完成，生成 {len(steps)} 个步骤",
                detail={"steps": steps},
            ))

            return steps

        except json.JSONDecodeError as e:
            logs.append(LogEntry(
                timestamp=self._ts(),
                level="error",
                message=f"❌ JSON解析失败: {e}",
                detail={"raw": content},
            ))
            return []
        except Exception as e:
            logs.append(LogEntry(
                timestamp=self._ts(),
                level="error",
                message=f"❌ LLM调用失败: {e}",
            ))
            return []

    @staticmethod
    def _ts():
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
