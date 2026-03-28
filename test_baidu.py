"""
独立测试脚本 - 百度搜索 mimo 测试用例
不需要 LLM API，直接构造测试步骤执行
"""
import asyncio
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.database import Base, engine, SessionLocal
from app.models.models import TestCase, TestStep, TestRun, StepResult, Skill
from app.services.test_executor import TestExecutor
from app.services.skill_manager import SkillManager
from app.services.report_generator import ReportGenerator
from app.schemas.schemas import LogEntry


def setup_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    # Seed default skills
    mgr = SkillManager(db)
    mgr.seed_default_skills()
    db.close()
    print("✅ 数据库初始化完成")


def create_test_case():
    """创建百度搜索测试用例"""
    db = SessionLocal()

    case = TestCase(
        name="百度搜索mimo测试",
        description="打开百度，搜索mimo，点击百度一下",
        target_url="https://www.baidu.com",
        natural_input="打开百度搜索mimo点击百度一下",
        status="ready",
    )
    db.add(case)
    db.flush()

    steps = [
        TestStep(
            case_id=case.id, step_order=1,
            action="navigate", target="https://www.baidu.com",
            locator_strategy=None, locator_value=None,
            raw_text="打开百度",
            status="generated",
        ),
        TestStep(
            case_id=case.id, step_order=2,
            action="wait", target="3000",
            locator_strategy=None, locator_value=None,
            raw_text="等待页面加载",
            status="generated",
        ),
        TestStep(
            case_id=case.id, step_order=3,
            action="fill", target="搜索框", value="mimo",
            locator_strategy="id", locator_value="kw",
            raw_text="在搜索框输入mimo",
            status="generated",
        ),
        TestStep(
            case_id=case.id, step_order=4,
            action="click", target="百度一下按钮",
            locator_strategy="id", locator_value="su",
            raw_text="点击百度一下",
            status="generated",
        ),
        TestStep(
            case_id=case.id, step_order=5,
            action="wait", target="5000",
            locator_strategy=None, locator_value=None,
            raw_text="等待搜索结果",
            status="generated",
        ),
        TestStep(
            case_id=case.id, step_order=6,
            action="screenshot", target="搜索结果页",
            locator_strategy=None, locator_value=None,
            raw_text="截图",
            status="generated",
        ),
    ]

    for s in steps:
        db.add(s)

    db.commit()
    case_id = case.id
    db.close()
    print(f"✅ 测试用例创建成功: case_id={case_id}")
    return case_id


async def run_test(case_id: int):
    """执行测试"""
    db = SessionLocal()

    run = TestRun(case_id=case_id, status="queued")
    db.add(run)
    db.flush()
    run_id = run.id

    logs = []
    executor = TestExecutor(db)

    print("\n" + "=" * 60)
    print("🚀 开始执行测试")
    print("=" * 60 + "\n")

    result_run = await executor.run_test(case_id, run_id, logs)

    # Print all logs
    for log in logs:
        level_colors = {
            "info": "\033[36m", "error": "\033[31m", "warn": "\033[33m",
            "debug": "\033[90m", "iframe": "\033[35m", "locator": "\033[36m",
            "action": "\033[32m",
        }
        reset = "\033[0m"
        color = level_colors.get(log.level, "\033[0m")
        ts = log.timestamp[11:19] if len(log.timestamp) > 19 else log.timestamp
        print(f"  {color}[{ts}] {log.message}{reset}")
        if log.detail and log.level in ("error", "iframe", "locator"):
            detail_str = str(log.detail)[:200]
            print(f"           {color}↳ {detail_str}{reset}")

    print("\n" + "=" * 60)
    status_icon = {"passed": "🎉", "failed": "💥", "error": "⚠️"}.get(result_run.status, "❓")
    print(f"{status_icon} 测试结果: {result_run.status.upper()}")
    print(f"⏱️  耗时: {result_run.duration_ms}ms")
    print(f"📋 步骤结果:")

    for sr in sorted(result_run.step_results, key=lambda x: x.step_order):
        icon = "✅" if sr.status == "passed" else "❌"
        print(f"  {icon} 步骤 {sr.step_order}: {sr.status} ({sr.duration_ms}ms)")
        if sr.error_message:
            print(f"     错误: {sr.error_message}")
        if sr.screenshot_path:
            print(f"     📸 截图: {sr.screenshot_path}")
        if sr.iframe_path:
            print(f"     📦 iframe路径: {sr.iframe_path}")

    # Generate report
    gen = ReportGenerator(db)
    report_path = gen.save_report(run_id)
    print(f"\n📊 测试报告: {report_path}")

    db.close()
    return result_run.status == "passed"


async def main():
    print("🧪 NL Test Framework - 百度搜索测试")
    print("=" * 60)

    setup_db()
    case_id = create_test_case()
    success = await run_test(case_id)

    if success:
        print("\n🎉 所有测试通过!")
    else:
        print("\n💥 测试失败!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
