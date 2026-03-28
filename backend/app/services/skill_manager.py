"""Skill manager - loads and applies domain knowledge skills."""
from sqlalchemy.orm import Session
from app.models.models import Skill
from app.schemas.schemas import LogEntry


class SkillManager:
    def __init__(self, db: Session):
        self.db = db

    def get_matching_skills(self, url: str, logs: list = None) -> list[Skill]:
        """Get all enabled skills that match the given URL."""
        if logs is None:
            logs = []

        skills = (
            self.db.query(Skill)
            .filter(Skill.enabled == 1)
            .order_by(Skill.priority.desc())
            .all()
        )

        matched = []
        for skill in skills:
            if not skill.url_pattern or self._match_url(url, skill.url_pattern):
                matched.append(skill)

        if matched:
            logs.append(LogEntry(
                timestamp=_ts(),
                level="info",
                message=f"📦 匹配到 {len(matched)} 个技能包",
                detail={"skills": [s.name for s in matched]},
            ))

        return matched

    def build_context(self, skills: list[Skill]) -> str:
        """Build LLM context string from matched skills."""
        if not skills:
            return ""

        lines = []
        for skill in skills:
            lines.append(f"### 技能: {skill.name} ({skill.category})")
            if skill.description:
                lines.append(f"描述: {skill.description}")
            lines.append(f"规则: {_json_dumps(skill.rules)}")
            lines.append("")

        return "\n".join(lines)

    def get_iframe_hints(self, url: str) -> dict:
        """Get iframe mapping rules for a URL."""
        skills = self.get_matching_skills(url)
        hints = {}
        for skill in skills:
            if skill.category == "iframe" and skill.rules:
                hints.update(skill.rules)
        return hints

    def get_wait_rules(self, url: str) -> dict:
        """Get wait rules for a URL."""
        skills = self.get_matching_skills(url)
        rules = {}
        for skill in skills:
            if skill.category == "wait" and skill.rules:
                rules.update(skill.rules)
        return rules

    @staticmethod
    def _match_url(url: str, pattern: str) -> bool:
        """Simple glob-style URL matching."""
        import fnmatch
        return fnmatch.fnmatch(url, pattern)

    def seed_default_skills(self):
        """Seed some default skills for common scenarios."""
        defaults = [
            {
                "name": "百度搜索",
                "description": "百度首页搜索相关操作",
                "category": "page",
                "url_pattern": "*baidu.com*",
                "rules": {
                    "search_input": {
                        "strategy": "id",
                        "value": "kw",
                        "description": "搜索输入框"
                    },
                    "search_button": {
                        "strategy": "id",
                        "value": "su",
                        "description": "百度一下按钮"
                    },
                    "wait_after_search": {
                        "type": "selector",
                        "value": "#content_left",
                        "timeout_ms": 5000,
                        "description": "等待搜索结果加载"
                    }
                },
                "priority": 10,
            },
            {
                "name": "通用等待规则",
                "description": "页面加载等待策略",
                "category": "wait",
                "url_pattern": "*",
                "rules": {
                    "page_load": {
                        "type": "networkidle",
                        "timeout_ms": 15000,
                        "description": "等待网络空闲"
                    },
                    "input_focus": {
                        "type": "element_visible",
                        "timeout_ms": 5000,
                        "description": "输入前等待元素可见"
                    }
                },
                "priority": 1,
            },
        ]

        for data in defaults:
            exists = self.db.query(Skill).filter(Skill.name == data["name"]).first()
            if not exists:
                skill = Skill(**data)
                self.db.add(skill)
        self.db.commit()


def _ts():
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"


def _json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
