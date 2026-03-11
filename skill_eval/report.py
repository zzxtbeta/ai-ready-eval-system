"""
skill_eval/report.py — Skill 质量评估报告生成器
"""

from __future__ import annotations

import datetime
from typing import Any


DIMENSION_WEIGHTS = {
    "structure": 2.0,
    "instruction_quality": 2.5,
    "trigger_accuracy": 3.0,   # 最关键：触发准确率直接影响 agent 选择
    "functional_reliability": 3.0,
    "integration": 2.0,
}


class SkillReport:
    """整合 Skill 各维度评估结果，生成结构化报告。"""

    def __init__(self, skill_results: list[dict]):
        """
        Args:
            skill_results: [
                {
                    "path": str,
                    "structure": dict,
                    "content": dict,
                    "trigger": dict,       # optional
                    "functional": dict,    # optional
                    "integration": dict,   # optional
                }
            ]
        """
        self.skill_results = skill_results

    def build(self) -> dict:
        all_skill_reports = []

        for skill_result in self.skill_results:
            skill_report = self._build_single_skill_report(skill_result)
            all_skill_reports.append(skill_report)

        # 多 Skill 时取平均分
        if all_skill_reports:
            overall = sum(s["overall_score"] for s in all_skill_reports) / len(all_skill_reports)
        else:
            overall = 0.0

        grade = _grade(overall)

        return {
            "report_type": "skill_eval",
            "generated_at": datetime.datetime.now().isoformat(),
            "overall_score": round(overall, 4),
            "grade": grade,
            "grade_label": _grade_label(grade),
            "skill_count": len(all_skill_reports),
            "skills": all_skill_reports,
            # 兼容单 skill 场景：展示第一个 skill 的维度
            "dimensions": all_skill_reports[0]["dimensions"] if all_skill_reports else [],
            "top_issues": _gather_top_issues(all_skill_reports),
            "top_recommendations": _gather_top_recommendations(all_skill_reports),
        }

    def _build_single_skill_report(self, skill_result: dict) -> dict:
        """构建单个 Skill 的报告。"""
        dimensions = []

        structure = skill_result.get("structure", {})
        if structure:
            dimensions.append(structure)

        content = skill_result.get("content", {})
        if content:
            dimensions.append(content)

        trigger = skill_result.get("trigger", {})
        if trigger:
            dimensions.append(trigger)

        functional = skill_result.get("functional", {})
        if functional:
            dimensions.append(functional)

        integration = skill_result.get("integration", {})
        if integration:
            dimensions.append(integration)

        overall = _calculate_overall_score(dimensions)
        grade = _grade(overall)

        return {
            "path": skill_result.get("path", ""),
            "name": structure.get("metadata", {}).get("skill_name", "Unknown Skill"),
            "overall_score": round(overall, 4),
            "grade": grade,
            "grade_label": _grade_label(grade),
            "dimensions": dimensions,
        }


def _calculate_overall_score(dimensions: list[dict]) -> float:
    if not dimensions:
        return 0.0

    total_weight = 0.0
    total_score = 0.0

    for dim in dimensions:
        dim_id = dim.get("id", "")
        weight = DIMENSION_WEIGHTS.get(dim_id, 2.0)
        score = dim.get("score", 0.0)
        total_weight += weight
        total_score += score * weight

    return total_score / total_weight if total_weight > 0 else 0.0


def _gather_top_issues(skill_reports: list[dict]) -> list[str]:
    issues = []
    for sr in skill_reports:
        for dim in sr.get("dimensions", []):
            issues.extend(dim.get("issues", []))
    return list(dict.fromkeys(issues))[:8]


def _gather_top_recommendations(skill_reports: list[dict]) -> list[str]:
    recs = []
    for sr in skill_reports:
        for dim in sr.get("dimensions", []):
            recs.extend(dim.get("recommendations", []))
    return list(dict.fromkeys(recs))[:6]


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
        "A": "Production-Grade",
        "B": "Usable",
        "C": "Fragile",
        "D": "Prototype",
    }.get(grade, "Unknown")
