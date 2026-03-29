"""
百度搜索 mimo → 点击搜索 → 点击第一条结果
使用集成技能包的 TestExecutor 执行
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.database import Base, engine, SessionLocal
from app.models.models import TestCase, TestStep, TestRun
from app.services.skill_manager import SkillManager
from app.services.test_executor import TestExecutor
from app.services.report_generator import ReportGenerator


def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    mgr = SkillManager(db)
    mgr.seed_default_skills()
    db.close()
    print("✅ 数据库初始化完成")


def create_test_case():
    db = SessionLocal()
    case = TestCase(
        name="百度搜索mimo并点击第一条结果",
        description="打开百度，搜索mimo，点击搜索，点击第一条结果（由技能包自动处理弹窗）",
        target_url="https://www.baidu.com",
        natural_input="打开百度搜索mimo点击百度一下，然后点击第一条搜索结果",
        status="ready",
    )
    db.add(case)
    db.flush()

    steps = [
        (1,  "navigate",    "打开百度",         "https://www.baidu.com", None, None, None),
        (2,  "wait",        "等待页面加载",      "3000",                  None, None, None),
        (3,  "fill",        "搜索框输入mimo",    "搜索框",                "id", "kw", "mimo"),
        (4,  "click",       "点击百度一下",      "百度一下按钮",          "id", "su", None),
        (5,  "wait",        "等待搜索结果",      "5000",                  None, None, None),
        (6,  "screenshot",  "截图搜索结果页",    "搜索结果页",            None, None, None),
        (7,  "click",       "点击第一条结果",    "第一条搜索结果",        "css", "#content_left .result h3 a", None),
        (8,  "wait",        "等待目标页加载",    "5000",                  None, None, None),
        (9,  "screenshot",  "截图目标页面",      "目标页面",              None, None, None),
    ]

    for order, action, raw, target, strategy, locator, value in steps:
        db.add(TestStep(
            case_id=case.id, step_order=order,
            action=action, target=target, value=value,
            locator_strategy=strategy, locator_value=locator,
            raw_text=raw, status="generated",
        ))

    db.commit()
    case_id = case.id
    db.close()
    print(f"✅ 测试用例创建: case_id={case_id}，共 {len(steps)} 步")
    return case_id


async def run_test(case_id: int):
    db = SessionLocal()
    run = TestRun(case_id=case_id, status="queued")
    db.add(run)
    db.flush()
    run_id = run.id

    logs = []
    executor = TestExecutor(db)

    print("\n" + "=" * 60)
    print("🚀 开始执行 (技能包自动加载)")
    print("=" * 60 + "\n")

    result_run = await executor.run_test(case_id, run_id, logs)

    # 打印日志
    colors = {
        "info": "\033[36m", "error": "\033[31m", "warn": "\033[33m",
        "debug": "\033[90m", "iframe": "\033[35m", "locator": "\033[36m",
        "action": "\033[32m",
    }
    reset = "\033[0m"
    for log in logs:
        c = colors.get(log.level, "\033[0m")
        ts = log.timestamp[11:19] if len(log.timestamp) > 19 else log.timestamp
        print(f"  {c}[{ts}] {log.message}{reset}")
        if log.detail and log.level in ("error", "iframe", "locator", "debug"):
            print(f"           {c}↳ {str(log.detail)[:200]}{reset}")

    print("\n" + "=" * 60)
    icon = "🎉" if result_run.status == "passed" else "💥"
    print(f"{icon} 结果: {result_run.status.upper()} | 耗时: {result_run.duration_ms}ms")
    print("📋 步骤:")
    for sr in sorted(result_run.step_results, key=lambda x: x.step_order):
        si = "✅" if sr.status == "passed" else "❌"
        print(f"  {si} 步骤{sr.step_order}: {sr.status} ({sr.duration_ms}ms)")
        if sr.error_message:
            print(f"     错误: {sr.error_message}")

    gen = ReportGenerator(db)
    report_path = gen.save_report(run_id)
    print(f"\n📊 报告: {report_path}")

    passed = result_run.status == "passed"
    db.commit()
    db.close()
    return passed, run_id


async def main():
    print("🧪 百度搜索mimo → 点击搜索 → 点击第一条结果 (技能增强版)")
    print("=" * 60)
    setup_db()
    case_id = create_test_case()
    success, run_id = await run_test(case_id)
    print(f"\n{'🎉 全部通过!' if success else '💥 失败!'}")


if __name__ == "__main__":
    asyncio.run(main())
