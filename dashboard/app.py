"""
dashboard/app.py — Flask 仪表盘应用

部署到 Vercel 时通过 api/index.py 引用此模块。
本地运行：python main.py dashboard
"""

from __future__ import annotations

import json
import os
import sys
import datetime

from flask import Flask, render_template, jsonify, request, redirect, url_for

# 确保项目根目录在 Python path 中
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

_template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(
    __name__,
    template_folder=_template_dir,
    static_folder=_static_dir,
    static_url_path="/static",
)
app.secret_key = os.environ.get("FLASK_SECRET", "ai-ready-eval-local-dev")

# Jinja2 额外全局函数
app.jinja_env.globals["enumerate"] = enumerate
app.jinja_env.globals["abs"] = abs

REPORTS_DIR = os.environ.get("REPORTS_DIR", os.path.join(_root, "reports"))
EXAMPLES_DIR = os.path.join(_root, "examples")


# ─────────────────────────────────────────────────── helpers ─────

def _load_report(report_type: str) -> dict | None:
    """尝试加载最新报告，失败时返回示例数据。"""
    latest_path = os.path.join(REPORTS_DIR, f"{report_type}_report_latest.json")
    if os.path.exists(latest_path):
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 回退到示例数据
    demo_path = os.path.join(EXAMPLES_DIR, "demo_results", f"{report_type}_report.json")
    if os.path.exists(demo_path):
        try:
            with open(demo_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_is_demo"] = True
                return data
        except Exception:
            pass

    return None


def _load_trend_data() -> list[dict]:
    """加载历史评估趋势数据。"""
    demo_path = os.path.join(EXAMPLES_DIR, "demo_results", "trend_data.json")
    if os.path.exists(demo_path):
        try:
            with open(demo_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _generate_mock_trend()


def _generate_mock_trend() -> list[dict]:
    """生成模拟趋势数据（演示用）。"""
    import random
    random.seed(42)
    trend = []
    base_api = 0.62
    base_skill = 0.58
    for i in range(8):
        date = (datetime.datetime.now() - datetime.timedelta(weeks=7 - i)).strftime("%Y-%m-%d")
        api_score = min(0.95, base_api + i * 0.04 + random.uniform(-0.02, 0.02))
        skill_score = min(0.92, base_skill + i * 0.04 + random.uniform(-0.02, 0.02))
        trend.append({
            "date": date,
            "api_score": round(api_score, 3),
            "skill_score": round(skill_score, 3),
        })
    return trend


def _grade_info(score: float) -> dict:
    if score >= 0.85:
        return {"grade": "A", "label": "Agent-Ready", "color": "#22c55e", "bg": "#f0fdf4"}
    elif score >= 0.70:
        return {"grade": "B", "label": "Agent-Usable", "color": "#eab308", "bg": "#fefce8"}
    elif score >= 0.50:
        return {"grade": "C", "label": "Agent-Fragile", "color": "#f97316", "bg": "#fff7ed"}
    else:
        return {"grade": "D", "label": "Agent-Hostile", "color": "#ef4444", "bg": "#fef2f2"}


def _skill_grade_info(score: float) -> dict:
    if score >= 0.85:
        return {"grade": "A", "label": "Production-Grade", "color": "#22c55e", "bg": "#f0fdf4"}
    elif score >= 0.70:
        return {"grade": "B", "label": "Usable", "color": "#eab308", "bg": "#fefce8"}
    elif score >= 0.50:
        return {"grade": "C", "label": "Fragile", "color": "#f97316", "bg": "#fff7ed"}
    else:
        return {"grade": "D", "label": "Prototype", "color": "#ef4444", "bg": "#fef2f2"}


# ─────────────────────────────────────────────────── routes ─────

@app.route("/")
def index():
    """概览页：展示 API + Skill 综合得分与关键指标。"""
    api_report = _load_report("api")
    skill_report = _load_report("skill")
    trend_data = _load_trend_data()

    api_score = api_report.get("overall_score", 0) if api_report else 0
    skill_score = skill_report.get("overall_score", 0) if skill_report else 0
    is_demo = (api_report or {}).get("_is_demo", False)

    return render_template(
        "index.html",
        api_report=api_report,
        skill_report=skill_report,
        api_score=api_score,
        skill_score=skill_score,
        api_grade=_grade_info(api_score),
        skill_grade=_skill_grade_info(skill_score),
        trend_data=json.dumps(trend_data),
        is_demo=is_demo,
        last_updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/api-eval")
def api_eval_detail():
    """API AI-Ready 测试页（前端静态分析 + 3层架构）。"""
    return render_template("api_detail.html")


@app.route("/skill-eval")
def skill_eval_detail():
    """Skill 评估页（多模式文件加载 + 3层分析）。"""
    return render_template("skill_detail.html")


@app.route("/trends")
def trends():
    """趋势页：历次评估对比，识别退化。"""
    trend_data = _load_trend_data()
    return render_template(
        "trend.html",
        trend_data=json.dumps(trend_data),
        trend_table=trend_data,
    )


@app.route("/run-eval", methods=["GET", "POST"])
def run_eval():
    """/run-eval 已合并到 /api-eval，此处重定向。"""
    return redirect(url_for("api_eval_detail"), code=301)


# ─────────────────────────────────────── JSON API endpoints ─────

@app.route("/api/scores")
def api_scores():
    """返回最新评分 JSON，供 CI/CD 消费。"""
    api_report = _load_report("api")
    skill_report = _load_report("skill")
    return jsonify({
        "api": {
            "score": api_report.get("overall_score", 0) if api_report else None,
            "grade": api_report.get("grade") if api_report else None,
        },
        "skill": {
            "score": skill_report.get("overall_score", 0) if skill_report else None,
            "grade": skill_report.get("grade") if skill_report else None,
        },
        "generated_at": datetime.datetime.now().isoformat(),
    })


@app.route("/api/report/api")
def api_report_json():
    report = _load_report("api")
    if not report:
        return jsonify({"error": "No API report found"}), 404
    return jsonify(report)


@app.route("/api/report/skill")
def skill_report_json():
    report = _load_report("skill")
    if not report:
        return jsonify({"error": "No Skill report found"}), 404
    return jsonify(report)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
