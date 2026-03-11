"""
维度 5：工作流文档化（Workflow Documentation）

检查 API 是否提供多步调用链文档、端点间依赖说明、HATEOAS 风格。
依据：The New Stack — Arazzo 规范讨论；OpenAI Agent 白皮书
"""

from __future__ import annotations


def evaluate(spec: dict) -> dict:
    checks = []
    issues = []
    recommendations = []

    # ── 检查 1：多步工作流文档 ──
    workflow_score = _check_workflow_docs(spec)
    checks.append({
        "id": "workflow_docs",
        "name": "多步工作流文档",
        "weight": "medium",
        "score": workflow_score,
        "detail": "检查 spec 中是否有工作流/序列说明（x-workflow、x-flow、externalDocs）",
    })
    if workflow_score < 0.5:
        issues.append("缺少多步工作流文档，agent 必须自己推断调用顺序")
        recommendations.append("添加 x-workflows 扩展或 externalDocs 链接描述常见调用链")

    # ── 检查 2：端点间依赖说明 ──
    dependency_score = _check_dependency_hints(spec)
    checks.append({
        "id": "endpoint_dependencies",
        "name": "端点依赖说明",
        "weight": "medium",
        "score": dependency_score,
        "detail": "检查端点描述中是否注明前置依赖（requires/depends/must first）",
    })
    if dependency_score < 0.5:
        recommendations.append("在端点描述中注明前置调用（如"调用此端点前需先调用 POST /auth/token"）")

    # ── 检查 3：HATEOAS 风格链接 ──
    hateoas_score = _check_hateoas(spec)
    checks.append({
        "id": "hateoas_links",
        "name": "HATEOAS 下一步提示",
        "weight": "low",
        "score": hateoas_score,
        "detail": "检查响应 schema 是否含 _links/next/href 等导航字段",
    })

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "工作流文档化",
        "id": "workflow_documentation",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def _check_workflow_docs(spec: dict) -> float:
    spec_str = str(spec).lower()
    workflow_keywords = ["x-workflow", "x-flow", "x-sequence", "arazzo", "workflow", "step"]
    hits = sum(1 for kw in workflow_keywords if kw in spec_str)
    if hits == 0:
        return 0.0
    elif hits <= 2:
        return 0.5
    else:
        return 1.0


def _check_dependency_hints(spec: dict) -> float:
    dependency_keywords = ["requires", "depends", "must first", "before calling", "prerequisite", "prior to"]
    found = 0
    total_ops = 0

    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"} and isinstance(op, dict):
                total_ops += 1
                desc = (op.get("description") or "").lower()
                if any(kw in desc for kw in dependency_keywords):
                    found += 1

    if total_ops == 0:
        return 0.5
    return min(found / max(total_ops * 0.3, 1), 1.0)  # 30% 端点有依赖说明即满分


def _check_hateoas(spec: dict) -> float:
    hateoas_keywords = ["_links", "next_url", "next_href", "x-next", "links", "hypermedia"]
    spec_str = str(spec).lower()
    return 1.0 if any(kw in spec_str for kw in hateoas_keywords) else 0.0
