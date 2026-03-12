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
    """加载历史评估趋势数据（仅从真实报告文件读取，无 mock）。"""
    trend_path = os.path.join(REPORTS_DIR, "trend_data.json")
    if os.path.exists(trend_path):
        try:
            with open(trend_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


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
    """产品首页——两个评估入口 + 三层架构说明。"""
    return render_template("index.html")


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


@app.route("/settings")
def settings_page():
    """LLM 提供商配置页面（Key 保存在浏览器 localStorage，后端无感知）。"""
    return render_template("settings.html")


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


# ─────────────────────────────── LLM & Spec 代理接口 ───────────────

@app.route("/api/llm-call", methods=["POST"])
def llm_call():
    """LLM 代理接口 —— 避免浏览器直接调用 LLM 的 CORS 限制。

    请求体 JSON:
        { provider: { baseUrl, apiKey, model, extraHeaders? }, messages: [...] }

    API Key 仅做请求转发，服务端不存储。
    """
    import urllib.request as _ureq  # noqa: PLC0415
    import urllib.error   as _uerr  # noqa: PLC0415
    import ssl            as _ssl   # noqa: PLC0415

    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "请求格式错误，需要 JSON 请求体"}), 400

    provider   = data.get("provider") or {}
    messages   = data.get("messages") or []
    base_url   = str(provider.get("baseUrl")  or "").strip().rstrip("/")
    api_key    = str(provider.get("apiKey")   or "").strip()
    model      = str(provider.get("model")    or "").strip()
    extra_hdrs = provider.get("extraHeaders") or {}

    if not base_url or not api_key or not model:
        return jsonify({"error": "缺少 provider 配置（baseUrl / apiKey / model）"}), 400

    # 安全校验：仅允许 HTTPS，防止 SSRF 访问内网
    if not base_url.startswith("https://"):
        return jsonify({"error": "baseUrl 必须使用 HTTPS 协议"}), 400

    endpoint = base_url + "/chat/completions"
    payload  = json.dumps({
        "model":       model,
        "messages":    messages,
        "max_tokens":  4096,
        "temperature": 0.2,
    }).encode("utf-8")

    headers = {
        "Content-Type":  "application/json",
        "Authorization": "Bearer " + api_key,
    }
    for k, v in extra_hdrs.items():
        headers[str(k)[:100]] = str(v)[:500]

    try:
        req = _ureq.Request(endpoint, data=payload, headers=headers, method="POST")
        ctx = _ssl.create_default_context()
        with _ureq.urlopen(req, timeout=90, context=ctx) as resp:
            return app.response_class(resp.read(), status=200, mimetype="application/json")
    except _uerr.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        return jsonify({"error": f"LLM 接口返回 HTTP {exc.code}", "detail": body}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)[:300]}), 502


@app.route("/api/fetch-spec")
def fetch_spec():
    """从远程 URL 获取 OpenAPI Spec 文件（代理，解决浏览器 CORS 限制）。

    Query param: ?url=<spec URL>
    返回: { content, content_type, url }
    """
    import urllib.request as _ureq  # noqa: PLC0415
    import urllib.error   as _uerr  # noqa: PLC0415
    import ssl            as _ssl   # noqa: PLC0415

    raw_url = request.args.get("url", "").strip()
    if not raw_url:
        return jsonify({"error": "缺少 url 参数"}), 400
    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        return jsonify({"error": "仅支持 http/https 协议"}), 400

    try:
        req = _ureq.Request(
            raw_url,
            headers={
                "User-Agent": "AI-Ready-Eval/1.0",
                "Accept":     "application/json, application/yaml, text/yaml, */*",
            },
        )
        ctx = _ssl.create_default_context()
        with _ureq.urlopen(req, timeout=20, context=ctx) as resp:
            content_type = resp.headers.get("Content-Type", "text/plain")
            content      = resp.read().decode("utf-8", errors="replace")
            return jsonify({"content": content, "content_type": content_type, "url": raw_url})
    except _uerr.HTTPError as exc:
        return jsonify({"error": f"远端返回 HTTP {exc.code}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)[:300]}), 502


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
