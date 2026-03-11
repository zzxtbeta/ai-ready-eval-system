"""
维度 6：设计一致性（Design Consistency）

分析 OpenAPI spec 中命名风格、分页参数、日期格式、认证方式的统一性。
依据：The New Stack 引用 Tyk CEO — "LLM 是模式追随者"
"""

from __future__ import annotations
import re
from collections import Counter
from typing import Any


def evaluate(spec: dict) -> dict:
    """评估 API 设计一致性。"""
    checks = []
    issues = []
    recommendations = []

    paths = spec.get("paths", {})
    http_methods = {"get", "post", "put", "patch", "delete"}

    all_field_names: list[str] = []
    all_param_names: list[str] = []
    list_endpoint_pagination: list[dict] = []
    date_field_formats: list[str] = []
    auth_schemes: set[str] = set()

    # 收集 components.securitySchemes
    for scheme_name, scheme_def in spec.get("components", {}).get("securitySchemes", {}).items():
        auth_schemes.add(scheme_def.get("type", "unknown"))

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in http_methods or not isinstance(operation, dict):
                continue

            # 收集参数名
            for param in operation.get("parameters", []):
                pname = param.get("name", "")
                if pname:
                    all_param_names.append(pname)

            # 收集响应字段名
            for _, response in operation.get("responses", {}).items():
                for _, media in response.get("content", {}).items():
                    schema = media.get("schema", {})
                    _collect_field_names(schema, all_field_names)

            # 收集日期字段格式
            _collect_date_formats(operation, date_field_formats)

            # 检测列表端点分页参数
            if method.lower() == "get":
                params = [p.get("name", "").lower() for p in operation.get("parameters", [])]
                list_endpoint_pagination.append({
                    "path": path,
                    "params": params,
                })

            # 收集操作级认证
            if "security" in operation:
                for sec in operation.get("security", []):
                    for key in sec.keys():
                        auth_schemes.add(key)

    # ── 检查 1：命名风格一致性 ──
    naming_score, naming_issues = _check_naming_consistency(all_field_names + all_param_names)
    checks.append({
        "id": "naming_consistency",
        "name": "命名一致性",
        "weight": "medium",
        "score": naming_score,
        "detail": f"分析 {len(all_field_names) + len(all_param_names)} 个字段/参数名",
    })
    issues.extend(naming_issues)

    # ── 检查 2：分页风格统一 ──
    pagination_score, pagination_issues = _check_pagination_consistency(list_endpoint_pagination)
    checks.append({
        "id": "pagination_consistency",
        "name": "分页风格统一",
        "weight": "medium",
        "score": pagination_score,
        "detail": f"分析 {len(list_endpoint_pagination)} 个 GET 端点的分页参数",
    })
    issues.extend(pagination_issues)
    if pagination_score < 0.8:
        recommendations.append("统一所有列表端点的分页参数名（如统一用 page+per_page 或 cursor+limit）")

    # ── 检查 3：日期格式统一 ──
    date_score, date_issues = _check_date_format_consistency(date_field_formats)
    checks.append({
        "id": "date_format_consistency",
        "name": "日期格式统一",
        "weight": "medium",
        "score": date_score,
        "detail": f"发现 {len(set(date_field_formats))} 种日期格式",
    })
    issues.extend(date_issues)
    if date_score < 1.0:
        recommendations.append("统一所有日期字段使用 ISO 8601 格式（format: date-time）")

    # ── 检查 4：认证方式统一 ──
    auth_score = _check_auth_consistency(auth_schemes)
    checks.append({
        "id": "auth_consistency",
        "name": "认证方式统一",
        "weight": "high",
        "score": auth_score,
        "detail": f"发现 {len(auth_schemes)} 种认证方式: {', '.join(auth_schemes) or '未定义'}",
    })
    if auth_score < 1.0:
        issues.append(f"存在多种认证方式: {', '.join(auth_schemes)}，增加 agent 集成复杂度")
        recommendations.append("统一使用单一认证方式（推荐 OAuth2 或 API Key）")

    # ── 检查 5：可选字段行为 ──
    # 静态检查：nullable 字段是否有 description 说明缺失时的行为
    nullable_score, nullable_issues = _check_nullable_consistency(spec)
    checks.append({
        "id": "nullable_consistency",
        "name": "可选字段行为统一",
        "weight": "medium",
        "score": nullable_score,
        "detail": "检查 nullable/optional 字段的行为说明",
    })
    issues.extend(nullable_issues)

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "设计一致性",
        "id": "design_consistency",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def _check_naming_consistency(names: list[str]) -> tuple[float, list[str]]:
    """判断命名风格是否统一（snake_case vs camelCase）。"""
    if not names:
        return 1.0, []

    snake = sum(1 for n in names if "_" in n and not _is_camel(n))
    camel = sum(1 for n in names if _is_camel(n))
    total = len(names)
    dominant = max(snake, camel)
    minority = min(snake, camel)

    if total == 0:
        return 1.0, []

    inconsistency_ratio = minority / total
    score = max(0.0, 1.0 - inconsistency_ratio * 2)
    issues = []
    if inconsistency_ratio > 0.1:
        style_a = "camelCase" if camel >= snake else "snake_case"
        style_b = "snake_case" if camel >= snake else "camelCase"
        issues.append(f"命名风格混用：{dominant} 个 {style_a} vs {minority} 个 {style_b}")
    return score, issues


def _is_camel(name: str) -> bool:
    """判断是否符合 camelCase 规则（含大写字母且无下划线）。"""
    return bool(re.search(r"[A-Z]", name)) and "_" not in name


def _check_pagination_consistency(endpoints: list[dict]) -> tuple[float, list[str]]:
    """检查列表端点的分页参数是否统一。"""
    pagination_styles = []
    has_pagination_count = 0

    for ep in endpoints:
        params = set(ep["params"])
        if "page" in params or "per_page" in params or "limit" in params or "offset" in params or "cursor" in params:
            has_pagination_count += 1
            if "cursor" in params:
                pagination_styles.append("cursor")
            elif "page" in params:
                pagination_styles.append("page")
            elif "offset" in params:
                pagination_styles.append("offset")

    if not pagination_styles:
        return 0.5, []  # 无列表端点，无法判断

    style_counts = Counter(pagination_styles)
    dominant_count = style_counts.most_common(1)[0][1]
    inconsistent = len(pagination_styles) - dominant_count
    score = max(0.0, 1.0 - inconsistent / len(pagination_styles))

    issues = []
    if len(style_counts) > 1:
        issues.append(f"分页风格不统一：{dict(style_counts)}")

    return score, issues


def _check_date_format_consistency(formats: list[str]) -> tuple[float, list[str]]:
    """检查日期格式是否统一为 ISO 8601。"""
    if not formats:
        return 1.0, []

    non_iso = [f for f in formats if f not in ("date-time", "date")]
    score = 1.0 - len(non_iso) / len(formats)
    issues = []
    if non_iso:
        issues.append(f"非标准日期格式: {list(set(non_iso))}")
    return score, issues


def _check_auth_consistency(schemes: set) -> float:
    """认证方式越少越好（1 种=满分，2 种=0.5，3 种+=0）。"""
    count = len(schemes)
    if count == 0:
        return 0.5  # 未定义认证，部分得分
    elif count == 1:
        return 1.0
    elif count == 2:
        return 0.6
    else:
        return 0.2


def _check_nullable_consistency(spec: dict) -> tuple[float, list[str]]:
    """简单检查 nullable 字段是否有描述缺失行为的说明。"""
    issues = []
    nullable_without_desc = 0
    nullable_total = 0

    def _scan(schema: dict, depth: int = 0):
        nonlocal nullable_without_desc, nullable_total
        if depth > 4 or not isinstance(schema, dict):
            return
        if schema.get("nullable") or schema.get("type") == "null":
            nullable_total += 1
            desc = schema.get("description", "")
            if not desc or "null" not in desc.lower() and "optional" not in desc.lower() and "omit" not in desc.lower():
                nullable_without_desc += 1
        for v in schema.get("properties", {}).values():
            _scan(v, depth + 1)
        if "items" in schema:
            _scan(schema["items"], depth + 1)

    for schema in spec.get("components", {}).get("schemas", {}).values():
        _scan(schema)

    if nullable_total == 0:
        return 1.0, []

    score = 1.0 - nullable_without_desc / nullable_total
    if nullable_without_desc > 0:
        issues.append(f"{nullable_without_desc} 个 nullable 字段未说明缺失时的行为")

    return score, issues


def _collect_field_names(schema: dict, names: list, depth: int = 0):
    """递归收集 schema 中所有字段名。"""
    if depth > 4 or not isinstance(schema, dict):
        return
    for name, sub_schema in schema.get("properties", {}).items():
        names.append(name)
        _collect_field_names(sub_schema, names, depth + 1)
    if "items" in schema:
        _collect_field_names(schema["items"], names, depth + 1)


def _collect_date_formats(operation: dict, formats: list):
    """从 operation 的 schema 中收集带 format: date* 的字段。"""
    def _scan(schema: dict, depth: int = 0):
        if depth > 4 or not isinstance(schema, dict):
            return
        fmt = schema.get("format", "")
        if fmt.startswith("date"):
            formats.append(fmt)
        for v in schema.get("properties", {}).values():
            _scan(v, depth + 1)
        if "items" in schema:
            _scan(schema["items"], depth + 1)

    for _, response in operation.get("responses", {}).items():
        for _, media in response.get("content", {}).items():
            _scan(media.get("schema", {}))
