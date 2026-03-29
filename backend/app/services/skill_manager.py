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
        """Seed default skills for common scenarios."""
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
                    },
                    "first_result": {
                        "strategy": "css",
                        "value": "#content_left .result h3 a",
                        "description": "第一条搜索结果链接"
                    },
                    "result_links": {
                        "strategy": "css",
                        "value": "#content_left .result h3 a",
                        "description": "所有搜索结果链接"
                    },
                    "related_searches": {
                        "strategy": "css",
                        "value": "#rs a",
                        "description": "相关搜索关键词"
                    },
                },
                "priority": 10,
            },
            {
                "name": "百度弹窗处理",
                "description": "百度首页Cookie同意弹窗和登录弹窗的处理规则",
                "category": "page",
                "url_pattern": "*baidu.com*",
                "rules": {
                    "pre_navigate_actions": [
                        {
                            "type": "set_user_agent",
                            "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "description": "伪装UA避免弹窗触发"
                        }
                    ],
                    "post_load_actions": [
                        {
                            "type": "js_dismiss",
                            "selectors": [
                                "[class*='pop']",
                                "[class*='dialog']",
                                "[class*='modal']",
                                "[class*='mask']",
                                "[class*='overlay']",
                                "[class*='cookie']",
                                "[class*='passport']",
                                "[class*='login_pop']"
                            ],
                            "description": "JS隐藏所有弹窗和遮罩层"
                        },
                        {
                            "type": "js_restore_scroll",
                            "description": "恢复页面滚动能力"
                        }
                    ],
                    "click_hints": {
                        "use_force": True,
                        "reason": "弹窗遮挡时需要force click绕过可见性检查"
                    },
                    "dismiss_selectors": [
                        "button:has-text('接受')",
                        "a:has-text('接受')",
                        "[class*='close']",
                        ".pass_login_close",
                        "a.close"
                    ],
                    "iframe_check": True,
                    "description": "百度弹窗可能在iframe中，需逐frame处理"
                },
                "priority": 20,
            },
            {
                "name": "通用弹窗处理",
                "description": "网站通用弹窗/模态框/Cookie同意的处理策略",
                "category": "wait",
                "url_pattern": "*",
                "rules": {
                    "cookie_consent_keywords": [
                        "接受", "同意", "Accept", "Agree", "Got it",
                        "我知道了", "同意并继续", "允许", "确认"
                    ],
                    "dismiss_strategies": [
                        {
                            "type": "text_click",
                            "priority": 1,
                            "description": "优先通过按钮文字点击关闭"
                        },
                        {
                            "type": "css_dismiss",
                            "selectors": [
                                "[class*='close']",
                                "[class*='dismiss']",
                                "[aria-label='Close']",
                                "button[class*='cookie'] + button",
                                ".modal .close",
                                ".dialog-close"
                            ],
                            "priority": 2,
                            "description": "通过CSS选择器定位关闭按钮"
                        },
                        {
                            "type": "js_force_dismiss",
                            "priority": 3,
                            "js_snippet": """
                                document.querySelectorAll(
                                    '[class*="pop"], [class*="dialog"], [class*="modal"], [class*="mask"], [class*="overlay"], [class*="cookie"], [class*="consent"]'
                                ).forEach(el => {
                                    el.style.display = 'none';
                                    el.style.visibility = 'hidden';
                                    el.style.pointerEvents = 'none';
                                });
                                document.body.style.overflow = 'auto';
                                document.documentElement.style.overflow = 'auto';
                            """,
                            "description": "终极方案：JS暴力隐藏所有弹窗元素"
                        }
                    ],
                    "cross_iframe": True,
                    "description": "弹窗可能在iframe中，需要检查所有frame"
                },
                "priority": 1,
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
            {
                "name": "不可见元素处理",
                "description": "当元素存在但不可见时的降级策略",
                "category": "element",
                "url_pattern": "*",
                "rules": {
                    "force_click": {
                        "enabled": True,
                        "description": "元素被遮挡时使用force=True强制点击",
                        "fallback_order": [
                            "normal_click",
                            "js_click",
                            "force_click",
                            "dispatch_event"
                        ]
                    },
                    "force_fill": {
                        "enabled": True,
                        "description": "输入框不可见时使用force=True强制输入",
                        "fallback_order": [
                            "normal_fill",
                            "js_set_value",
                            "force_fill"
                        ]
                    },
                    "visibility_timeout_ms": 5000,
                    "description": "元素可见性等待超时后自动降级到force模式"
                },
                "priority": 5,
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
