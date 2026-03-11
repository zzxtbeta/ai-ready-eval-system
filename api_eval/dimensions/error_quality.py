"""
维度 3：错误语义质量（Error Quality）— 动态探测

检查错误响应的结构化程度、语义区分、具体性和修复建议。
依据：IETF RFC 7807 Problem Details、Microsoft API 工程实践
"""

from __future__ import annotations


def evaluate_static(spec: dict) -> dict:
    """
    静态分析错误响应定义质量。
    """
    checks = []
    issues = []
    recommendations = []

    paths = spec.get("paths", {})
    http_methods = {"get", "post", "put", "patch", "delete"}

    error_responses: list[dict] = []

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in http_methods or not isinstance(operation, dict):
                continue
            for status_code, response in operation.get("responses", {}).items():
                try:
                    code = int(status_code)
                except (ValueError, TypeError):
                    continue
                if code >= 400:
                    error_responses.append({
                        "path": path,
                        "method": method.upper(),
                        "status": code,
                        "response": response,
                    })

    if not error_responses:
        return {
            "name": "错误语义质量",
            "id": "error_quality",
            "score": 0.3,
            "checks": [],
            "issues": ["spec 中未定义任何错误响应（4xx/5xx）"],
            "recommendations": ["为主要端点定义 400/401/403/404/422/429/500 错误响应"],
        }

    # ── 检查 1：错误响应有 schema 定义 ──
    with_schema = sum(1 for er in error_responses if _has_json_schema(er["response"]))
    schema_score = _safe_ratio(with_schema, len(error_responses))
    checks.append({
        "id": "error_has_schema",
        "name": "错误响应结构化",
        "weight": "high",
        "score": schema_score,
        "detail": f"{with_schema}/{len(error_responses)} 个错误响应有 JSON schema 定义",
        "source": "static",
    })
    if schema_score < 0.8:
        recommendations.append("为所有错误响应定义 JSON schema（含 error_code/message/details 字段）")

    # ── 检查 2：错误码语义区分 ──
    status_codes = set(er["status"] for er in error_responses)
    diversity_score = min(len(status_codes) / 5, 1.0)  # 覆盖 5 种以上状态码得满分
    checks.append({
        "id": "error_code_diversity",
        "name": "错误码语义区分",
        "weight": "high",
        "score": diversity_score,
        "detail": f"定义了 {len(status_codes)} 种错误状态码: {sorted(status_codes)}",
        "source": "static",
    })
    if diversity_score < 0.6:
        issues.append(f"错误码种类不足（仅 {len(status_codes)} 种）")
        recommendations.append("区分 400（参数错误）/ 401（未认证）/ 403（无权限）/ 404（不存在）/ 422（语义错误）/ 429（限流）")

    # ── 检查 3：错误消息具体性（检查 schema 字段设计）──
    specificity_score = _check_error_schema_specificity(spec)
    checks.append({
        "id": "error_message_specificity",
        "name": "错误消息具体性",
        "weight": "high",
        "score": specificity_score,
        "detail": "检查错误 schema 是否含 field/details/code 等具体定位字段",
        "source": "static",
    })
    if specificity_score < 0.7:
        recommendations.append("错误响应应包含 field（哪个参数错了）、code（机器可读错误码）、details 字段")

    # ── 检查 4：修复建议字段 ──
    fix_hint_score = _check_fix_hint(spec)
    checks.append({
        "id": "error_fix_hint",
        "name": "修复建议字段",
        "weight": "medium",
        "score": fix_hint_score,
        "detail": "检查错误 schema 是否含 suggested_fix/hint/next_action 等字段",
        "source": "static",
    })

    # ── 检查 5：RFC 7807 兼容 ──
    rfc7807_score = _check_rfc7807(spec)
    checks.append({
        "id": "rfc7807_compat",
        "name": "RFC 7807 兼容",
        "weight": "low",
        "score": rfc7807_score,
        "detail": "检查是否使用 application/problem+json",
        "source": "static",
    })

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "错误语义质量",
        "id": "error_quality",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def evaluate_dynamic(probe_results: dict) -> dict:
    """融合动态探测错误响应结果。"""
    checks = []
    issues = []
    endpoint_results = probe_results.get("error_probes", [])

    if not endpoint_results:
        return {
            "name": "错误语义质量（动态）",
            "id": "error_quality_dynamic",
            "score": 0.5,
            "checks": [],
            "issues": ["未执行动态错误探测"],
            "recommendations": [],
        }

    is_json_scores = []
    is_structured_scores = []
    has_field_info_scores = []

    for result in endpoint_results:
        error_resp = result.get("error_response", {})
        is_json = result.get("is_json", False)
        is_json_scores.append(1.0 if is_json else 0.0)
        if not is_json:
            issues.append(f"{result.get('path', '?')}: 错误响应不是 JSON")

        is_structured = bool(
            is_json
            and isinstance(error_resp, dict)
            and any(k in error_resp for k in ("error", "message", "code", "type", "title"))
        )
        is_structured_scores.append(1.0 if is_structured else 0.0)

        has_field = bool(
            is_structured
            and any(k in str(error_resp) for k in ("field", "param", "detail", "path"))
        )
        has_field_info_scores.append(1.0 if has_field else 0.0)

    checks = [
        {
            "id": "error_is_json",
            "name": "错误响应 JSON 格式",
            "weight": "high",
            "score": _avg(is_json_scores),
            "detail": f"{sum(1 for s in is_json_scores if s == 1)}/{len(is_json_scores)} 个错误响应为 JSON",
            "source": "dynamic",
        },
        {
            "id": "error_is_structured",
            "name": "错误响应有固定结构",
            "weight": "high",
            "score": _avg(is_structured_scores),
            "detail": "",
            "source": "dynamic",
        },
        {
            "id": "error_has_field_info",
            "name": "错误指向具体字段",
            "weight": "high",
            "score": _avg(has_field_info_scores),
            "detail": "",
            "source": "dynamic",
        },
    ]

    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "错误语义质量（动态）",
        "id": "error_quality_dynamic",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": [],
    }


def _has_json_schema(response: dict) -> bool:
    content = response.get("content", {})
    return any(
        "json" in media_type.lower() and "schema" in content_obj
        for media_type, content_obj in content.items()
    )


def _check_error_schema_specificity(spec: dict) -> float:
    """检查错误相关 schema 是否含有具体定位字段。"""
    specificity_fields = {"field", "fields", "code", "error_code", "details", "path", "pointer"}
    schemas = spec.get("components", {}).get("schemas", {})

    error_schemas = {
        k: v for k, v in schemas.items()
        if any(kw in k.lower() for kw in ("error", "problem", "fault", "exception"))
    }

    if not error_schemas:
        return 0.3

    specific_count = 0
    for schema in error_schemas.values():
        props = set(schema.get("properties", {}).keys())
        if props & specificity_fields:
            specific_count += 1

    return specific_count / len(error_schemas)


def _check_fix_hint(spec: dict) -> float:
    fix_keywords = {"suggested_fix", "fix", "hint", "next_action", "resolution", "suggestion"}
    spec_str = str(spec).lower()
    return 1.0 if any(kw in spec_str for kw in fix_keywords) else 0.0


def _check_rfc7807(spec: dict) -> float:
    spec_str = str(spec)
    return 1.0 if "problem+json" in spec_str else 0.0


def _safe_ratio(n: int, d: int) -> float:
    return n / d if d > 0 else 1.0


def _avg(values: list) -> float:
    return sum(values) / len(values) if values else 0.0
