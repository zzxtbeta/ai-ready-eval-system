"""
维度 1：语义描述完整性（Semantic Description）

检查 OpenAPI spec 中端点、参数、响应字段的描述覆盖率与质量。
依据：The New Stack "How To Prepare Your API for AI Agents" (2025-06)
"""

from __future__ import annotations
import re
from typing import Any


MIN_ENDPOINT_DESC_WORDS = 15
MIN_PARAM_DESC_WORDS = 5
QUALITY_PENALTY_PATTERNS = [
    r"^(todo|tbd|n/a|placeholder|description|string|integer|boolean)\.?$",
    r"^the \w+ (field|parameter|value)\.?$",  # e.g. "The id field."
]


def evaluate(spec: dict) -> dict:
    """
    评估语义描述完整性。

    Returns:
        dict: {
            "score": float (0-1),
            "checks": list[dict],
            "issues": list[str],
            "recommendations": list[str]
        }
    """
    checks = []
    issues = []
    recommendations = []

    paths = spec.get("paths", {})
    total_endpoints = 0
    described_endpoints = 0
    total_params = 0
    described_params = 0
    params_with_examples = 0
    total_response_fields = 0
    described_response_fields = 0
    description_quality_scores = []

    http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in http_methods:
                continue
            if not isinstance(operation, dict):
                continue

            total_endpoints += 1
            desc = (operation.get("description") or operation.get("summary") or "").strip()
            word_count = len(desc.split())
            if word_count >= MIN_ENDPOINT_DESC_WORDS:
                described_endpoints += 1
            else:
                issues.append(
                    f"{method.upper()} {path}: 描述不足（{word_count} 词，需 ≥ {MIN_ENDPOINT_DESC_WORDS}）"
                )

            # 描述质量评分（规则式）
            quality = _score_description_quality(desc)
            description_quality_scores.append(quality)

            # 参数检查
            for param in operation.get("parameters", []):
                total_params += 1
                p_desc = (param.get("description") or "").strip()
                p_words = len(p_desc.split())
                if p_words >= MIN_PARAM_DESC_WORDS:
                    described_params += 1
                else:
                    issues.append(
                        f"  参数 '{param.get('name', '?')}' 描述不足（{p_words} 词）"
                    )

                # 示例检查
                schema = param.get("schema", {})
                has_example = (
                    "example" in param
                    or "example" in schema
                    or "enum" in schema
                    or "default" in schema
                )
                if has_example:
                    params_with_examples += 1

            # requestBody 参数检查
            req_body = operation.get("requestBody", {})
            for media_content in req_body.get("content", {}).values():
                schema = media_content.get("schema", {})
                fields_total, fields_described = _count_schema_fields(schema)
                total_response_fields += fields_total
                described_response_fields += fields_described

            # 响应字段描述检查
            for status_code, response in operation.get("responses", {}).items():
                for media_content in response.get("content", {}).values():
                    schema = media_content.get("schema", {})
                    fields_total, fields_described = _count_schema_fields(schema)
                    total_response_fields += fields_total
                    described_response_fields += fields_described

    # ── 计算各项得分 ──
    endpoint_coverage = _safe_ratio(described_endpoints, total_endpoints)
    param_coverage = _safe_ratio(described_params, total_params)
    example_coverage = _safe_ratio(params_with_examples, total_params)
    response_field_coverage = _safe_ratio(described_response_fields, total_response_fields)
    avg_quality = (
        sum(description_quality_scores) / len(description_quality_scores)
        if description_quality_scores
        else 0.5
    )

    checks = [
        {
            "id": "endpoint_desc_coverage",
            "name": "端点描述覆盖率",
            "weight": "high",
            "score": endpoint_coverage,
            "detail": f"{described_endpoints}/{total_endpoints} 个端点有充分描述",
        },
        {
            "id": "param_desc_coverage",
            "name": "参数描述覆盖率",
            "weight": "high",
            "score": param_coverage,
            "detail": f"{described_params}/{total_params} 个参数有充分描述",
        },
        {
            "id": "param_example_coverage",
            "name": "参数示例覆盖率",
            "weight": "medium",
            "score": example_coverage,
            "detail": f"{params_with_examples}/{total_params} 个参数有示例/枚举",
        },
        {
            "id": "response_field_desc",
            "name": "响应字段描述率",
            "weight": "medium",
            "score": response_field_coverage,
            "detail": f"{described_response_fields}/{total_response_fields} 个响应字段有描述",
        },
        {
            "id": "description_quality",
            "name": "描述质量评分",
            "weight": "high",
            "score": avg_quality,
            "detail": f"平均描述质量 {avg_quality:.2f}（规则式评分）",
        },
    ]

    # ── 综合得分（加权）──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    # ── 建议 ──
    if endpoint_coverage < 0.8:
        recommendations.append("为所有端点添加 ≥ 15 词的语义描述（不只是名称重复）")
    if param_coverage < 0.8:
        recommendations.append("为每个参数添加说明用途、取值范围、副作用的描述")
    if example_coverage < 0.6:
        recommendations.append("为参数添加 example 或 enum 枚举值，帮助 agent 理解合法输入")
    if response_field_coverage < 0.7:
        recommendations.append("为响应 schema 的每个字段添加 description")

    return {
        "name": "语义描述完整性",
        "id": "semantic_description",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],  # 最多返回 10 条 issue
        "recommendations": recommendations,
    }


def _count_schema_fields(schema: dict, depth: int = 0) -> tuple[int, int]:
    """递归统计 schema 字段总数和有描述的字段数。"""
    if depth > 4 or not isinstance(schema, dict):
        return 0, 0

    total = 0
    described = 0

    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        for field_name, field_schema in schema.get("properties", {}).items():
            total += 1
            if (field_schema.get("description") or "").strip():
                described += 1
            sub_total, sub_described = _count_schema_fields(field_schema, depth + 1)
            total += sub_total
            described += sub_described
    elif kind == "array":
        sub_total, sub_described = _count_schema_fields(schema.get("items", {}), depth + 1)
        total += sub_total
        described += sub_described

    return total, described


def _score_description_quality(desc: str) -> float:
    """
    规则式描述质量评分（0-1）。
    检查描述是否有实质内容（不是占位符、不是类型声明重复）。
    """
    if not desc:
        return 0.0

    lower = desc.lower().strip()

    for pattern in QUALITY_PENALTY_PATTERNS:
        if re.match(pattern, lower):
            return 0.1

    # 词数越多、有动词、有业务语义 → 质量越高
    words = lower.split()
    word_count = len(words)
    if word_count < 5:
        return 0.3
    elif word_count < 10:
        return 0.6
    elif word_count < 20:
        return 0.8
    else:
        return 1.0


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0  # 没有需要检查的项目时视为通过
    return min(numerator / denominator, 1.0)
