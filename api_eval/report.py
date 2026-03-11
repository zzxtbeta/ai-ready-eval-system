"""
api_eval/report.py — API 评估报告生成器

整合静态分析和动态探测结果，计算综合 API AI-Readiness Score。
"""

from __future__ import annotations

import datetime
from typing import Any


# 各维度权重（影响综合得分）
DIMENSION_WEIGHTS = {
    "semantic_description": 3.0,   # 高：最影响 agent 可用性
    "response_sizing": 2.5,         # 高：影响 context 管理
    "error_quality": 2.5,           # 高：影响自愈能力
    "discoverability": 2.0,         # 中：影响发现和导入
    "workflow_documentation": 1.5,  # 中
    "design_consistency": 2.0,      # 中
    "traffic_resilience": 2.0,      # 中
    "security_readiness": 2.5,      # 高
}


class APIReport:
    """整合评估结果并生成结构化报告。"""

    def __init__(self, eval_results: dict):
        """
        Args:
            eval_results: {
                "static": scanner.run() 的返回值,
                "dynamic": prober.run() 的返回值（可选）,
                "agent_trial": agent_trial 结果（可选）
            }
        """
        self.eval_results = eval_results

    def build(self) -> dict:
        """构建完整报告。"""
        static = self.eval_results.get("static", {})
        dynamic = self.eval_results.get("dynamic", {})
        agent_trial = self.eval_results.get("agent_trial", {})

        dimensions = static.get("dimensions", [])
        dimensions = _merge_dynamic_results(dimensions, dynamic)

        overall_score = _calculate_overall_score(dimensions)
        grade = _grade(overall_score)

        # 提取所有 issues 和 recommendations
        all_issues = []
        all_recommendations = []
        for dim in dimensions:
            all_issues.extend(dim.get("issues", []))
            all_recommendations.extend(dim.get("recommendations", []))

        return {
            "report_type": "api_eval",
            "generated_at": datetime.datetime.now().isoformat(),
            "spec_info": static.get("spec_info", {}),
            "overall_score": round(overall_score, 4),
            "grade": grade,
            "grade_label": _grade_label(grade),
            "dimensions": dimensions,
            "top_issues": all_issues[:10],
            "top_recommendations": _deduplicate(all_recommendations)[:8],
            "agent_trial": agent_trial,
            "has_dynamic_results": bool(dynamic),
        }


def _merge_dynamic_results(dimensions: list[dict], dynamic: dict) -> list[dict]:
    """将动态探测结果合并到对应维度，取加权平均。"""
    if not dynamic:
        return dimensions

    dim_map = {d["id"]: d for d in dimensions}

    # 合并响应体量（动态）
    rs_dynamic = dynamic.get("response_sizing", {})
    if rs_dynamic.get("endpoints"):
        from api_eval.dimensions.response_sizing import evaluate_dynamic
        dyn_result = evaluate_dynamic(rs_dynamic)
        static_result = dim_map.get("response_sizing", {})
        if static_result:
            static_result["score"] = round(
                static_result["score"] * 0.4 + dyn_result["score"] * 0.6, 4
            )
            static_result["checks"].extend(dyn_result.get("checks", []))
            static_result["issues"].extend(dyn_result.get("issues", []))

    # 合并错误质量（动态）
    eq_dynamic = dynamic.get("error_quality", {})
    if eq_dynamic.get("error_probes"):
        from api_eval.dimensions.error_quality import evaluate_dynamic
        dyn_result = evaluate_dynamic(eq_dynamic)
        static_result = dim_map.get("error_quality", {})
        if static_result:
            static_result["score"] = round(
                static_result["score"] * 0.4 + dyn_result["score"] * 0.6, 4
            )
            static_result["checks"].extend(dyn_result.get("checks", []))
            static_result["issues"].extend(dyn_result.get("issues", []))

    return dimensions


def _calculate_overall_score(dimensions: list[dict]) -> float:
    """加权计算综合得分。"""
    if not dimensions:
        return 0.0

    total_weight = 0.0
    total_score = 0.0

    for dim in dimensions:
        dim_id = dim.get("id", "")
        weight = DIMENSION_WEIGHTS.get(dim_id, 1.5)
        score = dim.get("score", 0.0)
        total_weight += weight
        total_score += score * weight

    return total_score / total_weight if total_weight > 0 else 0.0


def _grade(score: float) -> str:
    if score >= 0.85:
        return "A"
    elif score >= 0.70:
        return "B"
    elif score >= 0.50:
        return "C"
    else:
        return "D"


def _grade_label(grade: str) -> str:
    return {
        "A": "Agent-Ready",
        "B": "Agent-Usable",
        "C": "Agent-Fragile",
        "D": "Agent-Hostile",
    }.get(grade, "Unknown")


def _deduplicate(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
