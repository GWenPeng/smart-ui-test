"""HTML test report generator with screenshots and detailed logs."""
import os
from datetime import datetime
from jinja2 import Template
from sqlalchemy.orm import Session
from app.models.models import TestCase, TestRun, StepResult


REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>测试报告 - {{ run.id }}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e1e4e8; line-height: 1.6; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
.header { background: linear-gradient(135deg, #1a1b26 0%, #24283b 100%); border-radius: 16px; padding: 32px; margin-bottom: 24px; border: 1px solid #30363d; }
.header h1 { font-size: 28px; margin-bottom: 8px; }
.header .meta { color: #8b949e; font-size: 14px; }
.status-badge { display: inline-block; padding: 4px 16px; border-radius: 20px; font-weight: 600; font-size: 14px; }
.status-passed { background: #1b4332; color: #52c41a; }
.status-failed { background: #3b1a1a; color: #ff4d4f; }
.status-error { background: #3b2e1a; color: #faad14; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
.stat-card .value { font-size: 32px; font-weight: 700; }
.stat-card .label { color: #8b949e; font-size: 13px; margin-top: 4px; }
.section { background: #161b22; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 24px; overflow: hidden; }
.section-title { padding: 16px 24px; font-size: 18px; font-weight: 600; border-bottom: 1px solid #30363d; background: #1c2128; }
.step { padding: 16px 24px; border-bottom: 1px solid #21262d; }
.step:last-child { border-bottom: none; }
.step-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.step-num { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; }
.step-passed .step-num { background: #1b4332; color: #52c41a; }
.step-failed .step-num { background: #3b1a1a; color: #ff4d4f; }
.step-action { font-weight: 600; }
.step-detail { color: #8b949e; font-size: 13px; margin-left: 40px; }
.step-error { background: #2d1b1b; border: 1px solid #5c2020; border-radius: 8px; padding: 12px; margin: 8px 0 8px 40px; color: #ff7875; font-size: 13px; }
.screenshot { margin: 12px 0 8px 40px; }
.screenshot img { max-width: 100%; border-radius: 8px; border: 1px solid #30363d; cursor: pointer; }
.screenshot img:hover { border-color: #58a6ff; }
.iframe-path { background: #1c2128; border-radius: 6px; padding: 8px 12px; margin: 8px 0 8px 40px; font-size: 12px; font-family: monospace; color: #79c0ff; }
.footer { text-align: center; color: #484f58; font-size: 13px; padding: 24px; }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; justify-content: center; align-items: center; }
.modal.active { display: flex; }
.modal img { max-width: 95%; max-height: 95%; border-radius: 8px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🧪 {{ case.name }}</h1>
    <div class="meta">
      <span class="status-badge status-{{ run.status }}">{{ run.status | upper }}</span>
      &nbsp; 运行 #{{ run.id }} | 目标: {{ case.target_url }} | {{ run.created_at.strftime('%Y-%m-%d %H:%M:%S') if run.created_at else '' }}
    </div>
    {% if case.description %}<div class="meta" style="margin-top:8px">{{ case.description }}</div>{% endif %}
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="value" style="color:#58a6ff">{{ total_steps }}</div>
      <div class="label">总步骤</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#52c41a">{{ passed_steps }}</div>
      <div class="label">通过</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#ff4d4f">{{ failed_steps }}</div>
      <div class="label">失败</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#f0883e">{{ run.duration_ms or 0 }}ms</div>
      <div class="label">总耗时</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📋 执行步骤</div>
    {% for sr in step_results %}
    <div class="step step-{{ sr.status }}">
      <div class="step-header">
        <div class="step-num">{{ sr.step_order }}</div>
        <div>
          <span class="step-action">{{ _action_icon(sr.step.action) }} {{ sr.step.action | upper }}</span>
          <span style="color:#8b949e;margin-left:8px">{{ sr.step.target }}</span>
        </div>
        <span style="margin-left:auto;color:#8b949e;font-size:12px">{{ sr.duration_ms }}ms</span>
      </div>
      {% if sr.step.value %}
      <div class="step-detail">值: {{ sr.step.value }}</div>
      {% endif %}
      {% if sr.step.locator_strategy %}
      <div class="step-detail">定位: {{ sr.step.locator_strategy }} = {{ sr.step.locator_value or sr.step.target }}</div>
      {% endif %}
      {% if sr.iframe_path %}
      <div class="iframe-path">📦 iframe 路径: {{ sr.iframe_path | join(' → ') }}</div>
      {% endif %}
      {% if sr.error_message %}
      <div class="step-error">❌ {{ sr.error_message }}</div>
      {% endif %}
      {% if sr.screenshot_path %}
      <div class="screenshot">
        <img src="/screenshots/{{ sr.screenshot_path }}" onclick="this.parentElement.classList.toggle('expanded')" loading="lazy">
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>

  {% if run.error_message %}
  <div class="section">
    <div class="section-title">⚠️ 错误信息</div>
    <div style="padding:24px;color:#ff7875">{{ run.error_message }}</div>
  </div>
  {% endif %}

  <div class="footer">
    NL Test Framework · 生成于 {{ now }}
  </div>
</div>

<div class="modal" id="modal" onclick="this.classList.remove('active')">
  <img id="modal-img" src="">
</div>
<script>
document.querySelectorAll('.screenshot img').forEach(img => {
  img.addEventListener('click', () => {
    document.getElementById('modal-img').src = img.src;
    document.getElementById('modal').classList.add('active');
  });
});
</script>
</body>
</html>"""


def _action_icon(action):
    icons = {
        "navigate": "🌐", "click": "👆", "fill": "✏️",
        "select": "📋", "check": "☑️", "hover": "🖱️",
        "wait": "⏳", "assert": "✔️", "scroll": "📜",
        "screenshot": "📸",
    }
    return icons.get(action, "▶")


class ReportGenerator:
    def __init__(self, db: Session, screenshot_dir: str = "./screenshots"):
        self.db = db
        self.screenshot_dir = screenshot_dir

    def generate(self, run_id: int) -> str:
        """Generate an HTML report for a test run."""
        run = self.db.query(TestRun).get(run_id)
        if not run:
            return "<html><body>Run not found</body></html>"

        case = run.case
        step_results = sorted(run.step_results, key=lambda x: x.step_order)

        # Enrich step results with step info
        enriched = []
        for sr in step_results:
            step = self.db.query(
                TestCase.__table__.columns.get("id"),  # dummy
            ).first()
            enriched.append({
                "step_order": sr.step_order,
                "status": sr.status,
                "duration_ms": sr.duration_ms,
                "error_message": sr.error_message,
                "screenshot_path": sr.screenshot_path,
                "iframe_path": sr.iframe_path,
                "step": sr.step,
            })

        passed = sum(1 for s in step_results if s.status == "passed")
        failed = sum(1 for s in step_results if s.status == "failed")

        template = Template(REPORT_TEMPLATE)
        template.globals["_action_icon"] = _action_icon

        html = template.render(
            run=run,
            case=case,
            step_results=step_results,
            total_steps=len(step_results),
            passed_steps=passed,
            failed_steps=failed,
            now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        return html

    def save_report(self, run_id: int) -> str:
        """Generate and save report to file, return path."""
        html = self.generate(run_id)
        report_dir = os.path.join(self.screenshot_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        path = os.path.join(report_dir, f"report_{run_id}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path
