"""
skill_eval/content_analysis.py — 内容质量分析

分析 Skill 指令质量：规则密度、Why 解释率、示例覆盖、边界处理。
依据：Anthropic — "大量 ALWAYS/NEVER 是黄色信号，试着解释为什么"
"""

from __future__ import annotations

import re
from typing import Any


# 命令式规则关键词
IMPERATIVE_KEYWORDS = [
    "always", "never", "must", "must not", "mustn't",
    "do not", "don't", "禁止", "必须", "不得", "严禁",
    "should not", "shall not",
]

# Why 解释关键词（出现在规则附近说明有解释）
WHY_KEYWORDS = [
    "because", "since", "so that", "in order to", "this ensures",
    "this prevents", "to avoid", "to prevent", "reason:", "why:",
    "因为", "由于", "为了", "以确保", "避免", "防止",
]

# 边界条件关键词
BOUNDARY_KEYWORDS = [
    "if.*not.*available", "if.*missing", "if.*empty", "if.*null",
    "when.*error", "when.*fail", "on error", "fallback",
    "edge case", "exception", "corner case",
    "如果.*没有", "如果.*缺少", "如果.*为空", "出错时", "异常", "兜底",
]

# 示例标记
EXAMPLE_MARKERS = [
    r"#+\s*example", r"#+\s*示例", r"e\.g\.", r"for example",
    r"```", r"- ✓", r"- ✗", r"\*\*good\*\*", r"\*\*bad\*\*",
]


class ContentAnalyzer:
    """分析 Skill 内容质量。"""

    def __init__(self, skill_path: str):
        self.skill_path = skill_path
        self.content = ""
        self.body = ""

    def load(self) -> bool:
        import os
        if not os.path.exists(self.skill_path):
            return False
        with open(self.skill_path, "r", encoding="utf-8") as f:
            self.content = f.read()
        # 去掉 frontmatter
        if self.content.startswith("---"):
            parts = self.content.split("---", 2)
            self.body = parts[2].strip() if len(parts) >= 3 else self.content
        else:
            self.body = self.content
        return True

    def run(self) -> dict:
        if not self.content and not self.load():
            return {
                "name": "指令质量",
                "id": "instruction_quality",
                "score": 0.0,
                "checks": [],
                "issues": [f"无法加载文件: {self.skill_path}"],
                "recommendations": [],
            }

        checks = []
        issues = []
        recommendations = []

        lines = self.body.splitlines()
        total_lines = max(len(lines), 1)

        # ── 检查 1：命令式规则密度 ──
        imperative_count = _count_imperative_rules(self.body)
        # 基准：每 50 行 1 次以下为良好
        expected_max = total_lines / 50
        density_score = max(0.0, 1.0 - max(0, imperative_count - expected_max) / max(expected_max, 1))

        checks.append({
            "id": "imperative_density",
            "name": "命令式规则密度",
            "weight": "medium",
            "score": density_score,
            "detail": f"{imperative_count} 条命令式规则 / {total_lines} 行（基准：每50行≤1条）",
        })
        if density_score < 0.6:
            issues.append(f"命令式规则过多（{imperative_count} 条），考虑改为解释意图的方式")
            recommendations.append("将 ALWAYS/NEVER/必须 等规则改为'因为[原因]，所以[行为]'的解释式写法")

        # ── 检查 2：Why 解释率 ──
        why_rate = _calculate_why_rate(self.body, imperative_count)
        checks.append({
            "id": "why_explanation_rate",
            "name": "Why 解释率",
            "weight": "high",
            "score": why_rate,
            "detail": f"{why_rate:.0%} 的约束性规则附带了理由说明",
        })
        if why_rate < 0.5:
            issues.append(f"仅 {why_rate:.0%} 的规则有理由说明（目标 ≥ 50%）")
            recommendations.append("为规则添加'为什么'：解释该规则防止什么问题、保证什么质量")

        # ── 检查 3：示例覆盖 ──
        example_score = _check_examples(self.body)
        checks.append({
            "id": "example_coverage",
            "name": "示例覆盖",
            "weight": "medium",
            "score": example_score,
            "detail": "检查是否有正面/反面示例",
        })
        if example_score < 0.5:
            recommendations.append("为关键行为规则添加正面示例（✓ 好的做法）和反面示例（✗ 避免）")

        # ── 检查 4：边界条件处理 ──
        boundary_score = _check_boundary_conditions(self.body)
        checks.append({
            "id": "boundary_conditions",
            "name": "边界条件处理",
            "weight": "high",
            "score": boundary_score,
            "detail": "检查数据不足/异常/冲突时的处理说明",
        })
        if boundary_score < 0.5:
            issues.append("未明确说明数据不足、异常或冲突时的行为")
            recommendations.append("添加'当...时'的边界处理：如数据不足、请求冲突、外部服务不可用等场景")

        # ── 检查 5：输出格式清晰度 ──
        output_score = _check_output_format(self.body)
        checks.append({
            "id": "output_format_clarity",
            "name": "输出格式清晰度",
            "weight": "medium",
            "score": output_score,
            "detail": "检查是否有明确的输出模板或结构说明",
        })
        if output_score < 0.5:
            recommendations.append("定义明确的输出格式模板，说明哪些部分是必填/可选的")

        # ── 综合评分 ──
        weights = {"high": 3, "medium": 2, "low": 1}
        total_w = sum(weights[c["weight"]] for c in checks)
        score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

        return {
            "name": "指令质量",
            "id": "instruction_quality",
            "score": round(score, 4),
            "checks": checks,
            "issues": issues[:10],
            "recommendations": recommendations,
            "metadata": {
                "imperative_count": imperative_count,
                "why_rate": round(why_rate, 3),
                "has_examples": example_score > 0.5,
                "has_boundary_handling": boundary_score > 0.5,
            },
        }


def _count_imperative_rules(text: str) -> int:
    """计算文本中命令式规则的数量。"""
    count = 0
    for line in text.splitlines():
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in IMPERATIVE_KEYWORDS):
            count += 1
    return count


def _calculate_why_rate(text: str, imperative_count: int) -> float:
    """估算有理由说明的规则比例。"""
    if imperative_count == 0:
        return 1.0  # 无命令式规则，天然满分

    lines = text.splitlines()
    rules_with_why = 0

    for i, line in enumerate(lines):
        line_lower = line.lower()
        is_imperative = any(kw in line_lower for kw in IMPERATIVE_KEYWORDS)
        if not is_imperative:
            continue

        # 检查当前行和相邻 3 行是否有 why 解释
        context_start = max(0, i - 1)
        context_end = min(len(lines), i + 3)
        context = " ".join(lines[context_start:context_end]).lower()

        if any(kw in context for kw in WHY_KEYWORDS):
            rules_with_why += 1

    return rules_with_why / imperative_count


def _check_examples(text: str) -> float:
    """检查示例覆盖率。"""
    hits = 0
    text_lower = text.lower()

    for pattern in EXAMPLE_MARKERS:
        if re.search(pattern, text_lower):
            hits += 1

    # 有正反两种示例更好
    has_positive = bool(re.search(r"✓|good example|\*\*do\*\*|recommended", text, re.IGNORECASE))
    has_negative = bool(re.search(r"✗|bad example|\*\*don'?t\*\*|avoid", text, re.IGNORECASE))

    if has_positive and has_negative:
        return 1.0
    elif hits >= 3:
        return 0.8
    elif hits >= 1:
        return 0.5
    else:
        return 0.0


def _check_boundary_conditions(text: str) -> float:
    """检查边界条件和异常处理说明。"""
    hits = 0
    for pattern in BOUNDARY_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            hits += 1

    return min(hits / 3, 1.0)  # 3 种以上边界情况即满分


def _check_output_format(text: str) -> float:
    """检查输出格式定义清晰度。"""
    output_indicators = [
        r"output format", r"response format", r"输出格式", r"响应格式",
        r"## output", r"## 输出", r"```", r"template:", r"模板",
        r"\| (column|字段)", r"structured",
    ]
    hits = sum(1 for p in output_indicators if re.search(p, text, re.IGNORECASE))
    return min(hits / 3, 1.0)
