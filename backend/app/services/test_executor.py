"""Test executor - runs parsed test steps with Playwright."""
import asyncio
import os
import time
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import TestCase, TestStep, TestRun, StepResult
from app.services.locator import smart_locate, build_locator, IframeExplorer
from app.schemas.schemas import LogEntry


class TestExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.screenshot_dir = settings.SCREENSHOT_DIR
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

        logs.append(LogEntry(
            timestamp=_ts(), level="info",
            message=f"🚀 开始执行测试: {case.name}",
            detail={"url": case.target_url, "steps": len(case.steps)},
        ))

        pw = None
        browser = None
        page = None

        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
            )
            page = await context.new_page()

            logs.append(LogEntry(timestamp=_ts(), level="info", message="🌐 浏览器已启动"))

            total_start = time.time()
            all_passed = True

            for step in sorted(case.steps, key=lambda s: s.step_order):
                step_result = StepResult(
                    run_id=run_id,
                    step_id=step.id,
                    step_order=step.step_order,
                    status="passed",
                )
                step_start = time.time()

                try:
                    await self._execute_step(page, step, logs, run_id, step.step_order)
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

                    # Take screenshot on failure
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

                    # Continue or stop based on config
                    # For now, stop on failure
                    break

                step_result.duration_ms = int((time.time() - step_start) * 1000)
                self.db.add(step_result)

            # Final screenshot on success
            if all_passed:
                final_name = f"run{run_id}_final.png"
                try:
                    await page.screenshot(
                        path=os.path.join(self.screenshot_dir, final_name),
                        full_page=True,
                    )
                    logs.append(LogEntry(
                        timestamp=_ts(), level="info",
                        message=f"📸 最终截图: {final_name}",
                    ))
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
            logs.append(LogEntry(
                timestamp=_ts(), level="error",
                message=f"💥 执行异常: {e}",
            ))

        finally:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()

        self.db.commit()
        return run

    async def _execute_step(self, page: Page, step: TestStep, logs: list, run_id: int, step_order: int):
        """Execute a single test step."""
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

        if action == "navigate":
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  🌐 导航到: {target}",
                step_order=step_order,
            ))
            await page.goto(target, wait_until="networkidle", timeout=timeout)
            await page.wait_for_load_state("networkidle")
            return

        if action == "wait":
            wait_type = "time"
            if target.isdigit():
                await page.wait_for_timeout(int(target))
            else:
                await page.wait_for_load_state("networkidle", timeout=timeout)
            return

        if action == "screenshot":
            name = f"run{run_id}_step{step_order}_manual.png"
            await page.screenshot(path=os.path.join(self.screenshot_dir, name), full_page=True)
            return

        if action == "scroll":
            loc, frame, path = await smart_locate(page, target, strategy, locator_val, iframe_hint, timeout, logs)
            if loc:
                await loc.scroll_into_view_if_needed()
            else:
                # Scroll page
                await page.evaluate("window.scrollBy(0, 500)")
            return

        # For actions that need element location
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
            logs.append(LogEntry(
                timestamp=_ts(), level="locator",
                message=f"  📍 元素信息: <{tag}> \"{text[:50]}\"",
                detail={"tag": tag, "text": text[:100], "box": box, "iframe_path": iframe_path},
                step_order=step_order,
            ))
        except Exception:
            pass

        if action == "click":
            await loc.first.click(timeout=timeout)
        elif action == "fill":
            await loc.first.fill(value or "", timeout=timeout)
            logs.append(LogEntry(
                timestamp=_ts(), level="action",
                message=f"  ✏️ 输入: {value}",
                step_order=step_order,
            ))
        elif action == "select":
            await loc.first.select_option(value or "", timeout=timeout)
        elif action == "check":
            await loc.first.check(timeout=timeout)
        elif action == "hover":
            await loc.first.hover(timeout=timeout)
        elif action == "assert":
            # Simple assertion: check text content
            text = await loc.first.text_content() or ""
            if value and value not in text:
                raise Exception(f"断言失败: 期望包含 \"{value}\"，实际为 \"{text}\"")
            logs.append(LogEntry(
                timestamp=_ts(), level="info",
                message=f"  ✔ 断言通过: \"{text[:50]}\"",
                step_order=step_order,
            ))


def _ts():
    return datetime.utcnow().isoformat() + "Z"
