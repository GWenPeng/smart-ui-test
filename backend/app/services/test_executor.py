"""Test executor - runs parsed test steps with Playwright, with skill-based enhancements."""
import asyncio
import os
import time
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import TestCase, TestStep, TestRun, StepResult, Skill
from app.services.locator import smart_locate, build_locator, IframeExplorer
from app.services.skill_manager import SkillManager
from app.schemas.schemas import LogEntry


class TestExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.screenshot_dir = settings.SCREENSHOT_DIR
        self.skill_mgr = SkillManager(db)
        self._active_skills: list[Skill] = []
        os.makedirs(self.screenshot_dir, exist_ok=True)

    async def run_test(self, case_id: int, run_id: int, logs: list) -> TestRun:
        """Execute a test case and record results."""
        case = self.db.query(TestCase).get(case_id)
        run = self.db.query(TestRun).get(run_id)

        if not case or not run:
            logs.append(LogEntry(timestamp=_ts(), level="error", message="❌ 测试用例或运行记录不存在"))
            return run

        run.status = "running"
        run.started_at = datetime.utcnow()
        self.db.commit()

        # Load matching skills
        self._active_skills = self.skill_mgr.get_matching_skills(case.target_url, logs)
        use_force = self._should_use_force()
        ua = self._get_custom_ua()

        logs.append(LogEntry(
            timestamp=_ts(), level="info",
            message=f"🚀 开始执行测试: {case.name}",
            detail={"url": case.target_url, "steps": len(case.steps), "skills": len(self._active_skills)},
        ))

        pw = None
        browser = None
        page = None

        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)

            ctx_opts = {
                "viewport": {"width": 1280, "height": 900},
                "ignore_https_errors": True,
            }
            if ua:
                ctx_opts["user_agent"] = ua
                logs.append(LogEntry(timestamp=_ts(), level="info", message=f"🎭 使用自定义 UA"))

            context = await browser.new_context(**ctx_opts)
            page = await context.new_page()

            logs.append(LogEntry(timestamp=_ts(), level="info", message="🌐 浏览器已启动"))

            total_start = time.time()
            all_passed = True

            for step in sorted(case.steps, key=lambda s: s.step_order):
                step_result = StepResult(
                    run_id=run_id, step_id=step.id,
                    step_order=step.step_order, status="passed",
                )
                step_start = time.time()

                try:
                    await self._execute_step(page, step, logs, run_id, step.step_order, use_force)
                    step_result.status = "passed"
                    logs.append(LogEntry(
                        timestamp=_ts(), level="info",
                        message=f"  ✅ 步骤 {step.step_order}: {step.action} → {step.target}",
                        step_order=step.step_order,
                    ))
                except Exception as e:
                    step_result.status = "failed"
                    step_result.error_message = str(e)
                    all_passed = False

                    screenshot_name = f"run{run_id}_step{step.step_order}_fail.png"
                    screenshot_path = os.path.join(self.screenshot_dir, screenshot_name)
                    try:
                        await page.screenshot(path=screenshot_path, full_page=True)
                        step_result.screenshot_path = screenshot_name
                        logs.append(LogEntry(
                            timestamp=_ts(), level="error",
                            message=f"  ❌ 步骤 {step.step_order} 失败: {e}",
                            detail={"screenshot": screenshot_name},
                            step_order=step.step_order,
                        ))
                    except Exception:
                        logs.append(LogEntry(
                            timestamp=_ts(), level="error",
                            message=f"  ❌ 步骤 {step.step_order} 失败: {e}",
                            step_order=step.step_order,
                        ))
                    break

                step_result.duration_ms = int((time.time() - step_start) * 1000)
                self.db.add(step_result)

            if all_passed:
                final_name = f"run{run_id}_final.png"
                try:
                    await page.screenshot(path=os.path.join(self.screenshot_dir, final_name), full_page=True)
                    logs.append(LogEntry(timestamp=_ts(), level="info", message=f"📸 最终截图: {final_name}"))
                except Exception:
                    pass

            run.status = "passed" if all_passed else "failed"
            run.duration_ms = int((time.time() - total_start) * 1000)
            run.finished_at = datetime.utcnow()

            logs.append(LogEntry(
                timestamp=_ts(), level="info",
                message=f"{'🎉' if all_passed else '💥'} 测试{'通过' if all_passed else '失败'}，耗时 {run.duration_ms}ms",
            ))

        except Exception as e:
            run.status = "error"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            logs.append(LogEntry(timestamp=_ts(), level="error", message=f"💥 执行异常: {e}"))
        finally:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()

        self.db.commit()
        return run

    # ==================== Skill helpers ====================

    def _should_use_force(self) -> bool:
        """Check if any active skill recommends force-click."""
        for skill in self._active_skills:
            if skill.category == "element" and skill.rules:
                fc = skill.rules.get("force_click", {})
                if fc.get("enabled"):
                    return True
        return False

    def _get_custom_ua(self) -> str:
        """Get custom user agent from skills."""
        for skill in self._active_skills:
            if skill.rules:
                pre = skill.rules.get("pre_navigate_actions", [])
                for action in pre:
                    if action.get("type") == "set_user_agent":
                        return action.get("value", "")
        return ""

    def _get_popup_rules(self) -> list[dict]:
        """Get popup dismissal rules from all active skills."""
        rules = []
        for skill in self._active_skills:
            if not skill.rules:
                continue
            # post_load_actions
            for action in skill.rules.get("post_load_actions", []):
                rules.append(action)
            # dismiss_selectors
            if "dismiss_selectors" in skill.rules:
                rules.append({
                    "type": "css_dismiss",
                    "selectors": skill.rules["dismiss_selectors"],
                })
            # cookie_consent_keywords -> text click
            if "cookie_consent_keywords" in skill.rules:
                rules.append({
                    "type": "text_click",
                    "keywords": skill.rules["cookie_consent_keywords"],
                })
            # dismiss_strategies from generic skills
            for strat in skill.rules.get("dismiss_strategies", []):
                rules.append(strat)
        # Sort by priority
        rules.sort(key=lambda r: r.get("priority", 99))
        return rules

    async def _dismiss_popups(self, page: Page, logs: list):
        """Apply popup dismissal rules from skills after page load."""
        rules = self._get_popup_rules()
        if not rules:
            return

        logs.append(LogEntry(
            timestamp=_ts(), level="debug",
            message=f"🧹 执行弹窗清理 ({len(rules)} 条规则)",
        ))

        for rule in rules:
            rtype = rule.get("type")

            if rtype == "js_dismiss":
                selectors = rule.get("selectors", [])
                selector_str = ", ".join(selectors)
                js = f"""
                    document.querySelectorAll('{selector_str}').forEach(el => {{
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                        el.style.pointerEvents = 'none';
                    }});
                """
                try:
                    await page.evaluate(js)
                    logs.append(LogEntry(
                        timestamp=_ts(), level="debug",
                        message=f"  🔧 JS隐藏弹窗 ({len(selectors)} 类选择器)",
                    ))
                except Exception:
                    pass

            elif rtype == "js_restore_scroll":
                try:
                    await page.evaluate("""
                        document.body.style.overflow = 'auto';
                        document.documentElement.style.overflow = 'auto';
                    """)
                except Exception:
                    pass

            elif rtype == "css_dismiss":
                for sel in rule.get("selectors", []):
                    try:
                        loc = page.locator(sel)
                        count = await loc.count()
                        if count > 0 and await loc.first.is_visible():
                            await loc.first.click(timeout=2000)
                            logs.append(LogEntry(
                                timestamp=_ts(), level="debug",
                                message=f"  👆 点击关闭: {sel}",
                            ))
                    except Exception:
                        continue

            elif rtype == "text_click":
                for kw in rule.get("keywords", []):
                    try:
                        loc = page.get_by_text(kw, exact=False)
                        count = await loc.count()
                        if count > 0 and await loc.first.is_visible():
                            await loc.first.click(timeout=2000)
                            logs.append(LogEntry(
                                timestamp=_ts(), level="debug",
                                message=f"  👆 文字点击关闭: '{kw}'",
                            ))
                            return
                    except Exception:
                        continue

            elif rtype == "js_force_dismiss":
                js = rule.get("js_snippet", "")
                if js:
                    try:
                        await page.evaluate(js)
                        logs.append(LogEntry(
                            timestamp=_ts(), level="debug",
                            message="  🔧 JS强力隐藏弹窗",
                        ))
                    except Exception:
                        pass

        # Also check iframes
        check_iframes = any(
            skill.rules.get("iframe_check") or skill.rules.get("cross_iframe")
            for skill in self._active_skills if skill.rules
        )
        if check_iframes:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    await frame.evaluate("""
                        document.querySelectorAll('[class*="pop"], [class*="dialog"], [class*="modal"], [class*="mask"], [class*="overlay"]').forEach(el => {
                            el.style.display = 'none';
                        });
                    """)
                except Exception:
                    pass

    # ==================== Step execution ====================

    async def _execute_step(
        self, page: Page, step: TestStep, logs: list,
        run_id: int, step_order: int, use_force: bool = False,
    ):
        """Execute a single test step with skill-enhanced behavior."""
        action = step.action
        target = step.target
        value = step.value
        strategy = step.locator_strategy
        locator_val = step.locator_value
        iframe_hint = step.iframe_hint
        timeout = step.timeout_ms or settings.DEFAULT_TIMEOUT_MS

        logs.append(LogEntry(
            timestamp=_ts(), level="action",
            message=f"  ▶ 执行: {action} | 目标: {target}",
            detail={"strategy": strategy, "value": locator_val, "iframe": iframe_hint},
            step_order=step_order,
        ))

        # ---- navigate ----
        if action == "navigate":
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  🌐 导航到: {target}",
                step_order=step_order,
            ))
            await page.goto(target, wait_until="networkidle", timeout=timeout)
            await page.wait_for_load_state("networkidle")

            # Auto-dismiss popups after navigate
            await self._dismiss_popups(page, logs)
            return

        # ---- wait ----
        if action == "wait":
            if target.isdigit():
                ms = int(target)
                logs.append(LogEntry(
                    timestamp=_ts(), level="action",
                    message=f"  ⏳ 等待 {ms}ms",
                    step_order=step_order,
                ))
                await page.wait_for_timeout(ms)
            else:
                await page.wait_for_load_state("networkidle", timeout=timeout)
            return

        # ---- screenshot ----
        if action == "screenshot":
            name = f"run{run_id}_step{step_order}.png"
            await page.screenshot(path=os.path.join(self.screenshot_dir, name), full_page=True)
            logs.append(LogEntry(
                timestamp=_ts(), level="info",
                message=f"  📸 截图: {name}",
                step_order=step_order,
            ))
            return

        # ---- scroll ----
        if action == "scroll":
            loc, frame, path = await smart_locate(page, target, strategy, locator_val, iframe_hint, timeout, logs)
            if loc:
                await loc.scroll_into_view_if_needed()
            else:
                await page.evaluate("window.scrollBy(0, 500)")
            return

        # ---- Element-based actions (click, fill, etc.) ----
        loc, frame, iframe_path = await smart_locate(
            page, target, strategy, locator_val or value, iframe_hint, timeout, logs
        )

        if not loc:
            raise Exception(f"未找到元素: {target} (策略: {strategy})")

        # Record element info
        try:
            el = loc.first
            box = await el.bounding_box()
            text = await el.text_content() or ""
            tag = await el.evaluate("el => el.tagName")
            visible = await el.is_visible()
            logs.append(LogEntry(
                timestamp=_ts(), level="locator",
                message=f"  📍 元素: <{tag}> \"{text[:50]}\" visible={visible}",
                detail={"tag": tag, "text": text[:100], "box": box, "visible": visible, "iframe_path": iframe_path},
                step_order=step_order,
            ))
        except Exception:
            visible = True  # assume visible if check fails

        # Execute action with force fallback
        if action == "click":
            await self._click_with_fallback(loc, timeout, use_force and not visible, logs, step_order)
        elif action == "fill":
            await self._fill_with_fallback(loc, value or "", timeout, use_force and not visible, logs, step_order)
        elif action == "select":
            await loc.first.select_option(value or "", timeout=timeout)
        elif action == "check":
            await loc.first.check(timeout=timeout)
        elif action == "hover":
            await loc.first.hover(timeout=timeout)
        elif action == "assert":
            text = await loc.first.text_content() or ""
            if value and value not in text:
                raise Exception(f"断言失败: 期望包含 \"{value}\"，实际为 \"{text}\"")
            logs.append(LogEntry(
                timestamp=_ts(), level="info",
                message=f"  ✔ 断言通过: \"{text[:50]}\"",
                step_order=step_order,
            ))

    async def _click_with_fallback(self, loc, timeout: int, force: bool, logs: list, step_order: int):
        """Click with normal → force → JS fallback chain."""
        el = loc.first

        # Try normal click first (short timeout)
        if not force:
            try:
                await el.click(timeout=min(timeout, 3000))
                logs.append(LogEntry(
                    timestamp=_ts(), level="action",
                    message=f"  👆 点击",
                    step_order=step_order,
                ))
                return
            except Exception:
                pass

        # Force click
        try:
            await el.click(force=True, timeout=timeout)
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  👆 Force点击",
                step_order=step_order,
            ))
            return
        except Exception:
            pass

        # JS click fallback
        try:
            await el.dispatch_event("click")
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  👆 JS事件点击",
                step_order=step_order,
            ))
            return
        except Exception as e:
            raise Exception(f"点击失败 (尝试了normal/force/js): {e}")

    async def _fill_with_fallback(self, loc, value: str, timeout: int, force: bool, logs: list, step_order: int):
        """Fill with normal → force → JS fallback chain."""
        el = loc.first

        if not force:
            try:
                await el.click(timeout=min(timeout, 3000))
                await el.fill(value, timeout=min(timeout, 3000))
                logs.append(LogEntry(
                    timestamp=_ts(), level="action",
                    message=f"  ✏️ 输入: {value}",
                    step_order=step_order,
                ))
                return
            except Exception:
                pass

        # Force fill
        try:
            await el.click(force=True, timeout=timeout)
            await el.fill(value, force=True, timeout=timeout)
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  ✏️ Force输入: {value}",
                step_order=step_order,
            ))
            return
        except Exception:
            pass

        # JS value set
        try:
            await el.evaluate(f"el => {{ el.value = '{value}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}")
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  ✏️ JS设置值: {value}",
                step_order=step_order,
            ))
            return
        except Exception as e:
            raise Exception(f"输入失败 (尝试了normal/force/js): {e}")


def _ts():
    return datetime.utcnow().isoformat() + "Z"
