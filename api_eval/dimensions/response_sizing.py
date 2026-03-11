"""
维度 2：响应体量控制（Response Sizing）— 动态探测

检查 API 默认响应体积、分页支持、字段筛选能力。
依据：The New Stack / OpenAI Agent 白皮书 — 最小化每步信息量
"""

from __future__ import annotations
from typing import Any


def evaluate_static(spec: dict) -> dict:
    """
    静态分析响应体量控制能力（无需实际调用 API）。
    """
    checks = []
    issues = []
    recommendations = []

    paths = spec.get("paths", {})
    get_endpoints = []

    for path, path_item in paths.items():
        op = path_item.get("get")
        if not isinstance(op, dict):
            continue
        params = [p.get("name", "").lower() for p in op.get("parameters", [])]
        get_endpoints.append({"path": path, "params": params, "operation": op})

    # ── 检查 1：分页支持 ──
    pagination_names = {"page", "limit", "per_page", "offset", "cursor", "page_size", "pagesize", "pagenumber"}
    endpoints_with_pagination = sum(
        1 for ep in get_endpoints
        if any(p in pagination_names for p in ep["params"])
    )
    pagination_score = _safe_ratio(endpoints_with_pagination, len(get_endpoints)) if get_endpoints else 1.0

    checks.append({
        "id": "pagination_support",
        "name": "分页支持",
        "weight": "high",
        "score": pagination_score,
        "detail": f"{endpoints_with_pagination}/{len(get_endpoints)} 个 GET 端点支持分页",
        "source": "static",
    })
    if pagination_score < 0.8:
        issues.append(f"{len(get_endpoints) - endpoints_with_pagination} 个 GET 端点缺少分页支持")
        recommendations.append("为所有返回列表的端点添加 page/limit 或 cursor 分页参数")

    # ── 检查 2：字段筛选 ──
    filter_names = {"fields", "select", "include", "exclude", "projection"}
    endpoints_with_filter = sum(
        1 for ep in get_endpoints
        if any(p in filter_names for p in ep["params"])
    )
    filter_score = _safe_ratio(endpoints_with_filter, len(get_endpoints)) if get_endpoints else 0.0

    checks.append({
        "id": "field_filtering",
        "name": "字段筛选",
        "weight": "medium",
        "score": filter_score,
        "detail": f"{endpoints_with_filter}/{len(get_endpoints)} 个 GET 端点支持字段筛选",
        "source": "static",
    })
    if filter_score < 0.5:
        recommendations.append("添加 fields/select 参数，允许 agent 只获取所需字段")

    # ── 检查 3：schema 中的 maxItems 约束 ──
    max_items_score = _check_max_items_constraint(spec)
    checks.append({
        "id": "max_items_constraint",
        "name": "响应集合大小约束",
        "weight": "high",
        "score": max_items_score,
        "detail": "检查列表响应 schema 是否有 maxItems 或默认限制",
        "source": "static",
    })
    if max_items_score < 0.5:
        issues.append("列表响应 schema 未定义 maxItems，agent 可能接收超大响应")
        recommendations.append("在响应 schema 中为数组字段添加 maxItems 约束，或在文档中说明默认上限")

    # ── 检查 4：批量端点 ──
    batch_score = _check_batch_endpoints(spec)
    checks.append({
        "id": "batch_endpoints",
        "name": "批量端点支持",
        "weight": "low",
        "score": batch_score,
        "detail": "检查是否有批量操作端点",
        "source": "static",
    })

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "响应体量控制",
        "id": "response_sizing",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def evaluate_dynamic(probe_results: dict) -> dict:
    """
    融合动态探测结果更新评分。

    Args:
        probe_results: prober.py 返回的 response_sizing 结果

    Returns:
        更新后的评估 dict
    """
    checks = []
    issues = []
    recommendations = []
    scores = []

    for ep_result in probe_results.get("endpoints", []):
        path = ep_result.get("path", "")
        default_size_bytes = ep_result.get("default_response_bytes", 0)
        # 4KB ≈ 1K token 阈值
        size_score = 1.0 if default_size_bytes < 4096 else (0.5 if default_size_bytes < 16384 else 0.0)
        scores.append(size_score)

        if size_score < 1.0:
            issues.append(
                f"{path}: 默认响应 {default_size_bytes // 1024}KB，"
                f"超过 4KB agent-safe 阈值"
            )

        checks.append({
            "id": f"default_size_{path.replace('/', '_')}",
            "name": f"{path} 默认响应体积",
            "weight": "high",
            "score": size_score,
            "detail": f"{default_size_bytes} bytes (~{default_size_bytes//4} tokens)",
            "source": "dynamic",
        })

    overall = sum(scores) / len(scores) if scores else 0.5
    if overall < 0.7:
        recommendations.append("设置合理的默认 limit（如 20），避免默认返回全量数据")

    return {
        "name": "响应体量控制（动态）",
        "id": "response_sizing_dynamic",
        "score": round(overall, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def _check_max_items_constraint(spec: dict) -> float:
    """检查响应 schema 中的 array 类型是否有 maxItems 约束。"""
    array_schemas = 0
    constrained = 0

    def _scan(schema: dict, depth: int = 0):
        nonlocal array_schemas, constrained
        if depth > 4 or not isinstance(schema, dict):
            return
        if schema.get("type") == "array":
            array_schemas += 1
            if "maxItems" in schema or "pagination" in str(schema).lower():
                constrained += 1
        for v in schema.get("properties", {}).values():
            _scan(v, depth + 1)
        if "items" in schema:
            _scan(schema["items"], depth + 1)

    for schema in spec.get("components", {}).get("schemas", {}).values():
        _scan(schema)

    for _, path_item in spec.get("paths", {}).items():
        for op in path_item.values():
            if isinstance(op, dict):
                for _, resp in op.get("responses", {}).items():
                    for _, media in resp.get("content", {}).items():
                        _scan(media.get("schema", {}))

    if array_schemas == 0:
        return 0.5
    return min(constrained / array_schemas, 1.0)


def _check_batch_endpoints(spec: dict) -> float:
    """检查是否有批量操作端点（路径含 batch/bulk）。"""
    for path in spec.get("paths", {}).keys():
        if "batch" in path.lower() or "bulk" in path.lower():
            return 1.0
    return 0.0


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return min(numerator / denominator, 1.0)
