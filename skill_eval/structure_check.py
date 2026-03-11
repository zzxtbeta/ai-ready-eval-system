"""
skill_eval/structure_check.py — 结构合规检查

检查 SKILL.md 的行数、Frontmatter 完整性、分层合理性。
依据：Anthropic skill-creator 渐进式加载原则
  - metadata 始终在 context（约 100 词）
  - SKILL.md 触发时加载（< 500 行，理想 < 200 行）
  - resources 按需加载
"""

from __future__ import annotations

import os
import re
from typing import Any


class StructureChecker:
    """检查 Skill 文件的结构合规性。"""

    def __init__(self, skill_path: str):
        self.skill_path = skill_path
        self.content = ""
        self.frontmatter: dict = {}
        self.body = ""

    def load(self) -> bool:
        if not os.path.exists(self.skill_path):
            return False
        with open(self.skill_path, "r", encoding="utf-8") as f:
            self.content = f.read()
        self.frontmatter, self.body = _parse_frontmatter(self.content)
        return True

    def run(self) -> dict:
        """运行结构检查，返回评估结果。"""
        if not self.content and not self.load():
            return {
                "name": "结构合规",
                "id": "structure",
                "score": 0.0,
                "checks": [],
                "issues": [f"无法加载文件: {self.skill_path}"],
                "recommendations": [],
            }

        checks = []
        issues = []
        recommendations = []

        lines = self.content.splitlines()
        line_count = len(lines)

        # ── 检查 1：行数 ──
        if line_count <= 200:
            line_score = 1.0
        elif line_count <= 500:
            line_score = 0.7
        else:
            line_score = 0.2

        checks.append({
            "id": "line_count",
            "name": "SKILL.md 行数",
            "weight": "high",
            "score": line_score,
            "detail": f"当前 {line_count} 行（理想 < 200，最大 < 500）",
        })
        if line_count > 500:
            issues.append(f"SKILL.md 过长（{line_count} 行），超出 500 行上限")
            recommendations.append("将详细规范移至 references/ 子目录，SKILL.md 只保留核心逻辑")
        elif line_count > 200:
            recommendations.append(f"SKILL.md 目前 {line_count} 行，考虑精简至 200 行以下")

        # ── 检查 2：Frontmatter 完整性 ──
        fm_score, fm_issues = _check_frontmatter(self.frontmatter)
        checks.append({
            "id": "frontmatter",
            "name": "Frontmatter 完整性",
            "weight": "high",
            "score": fm_score,
            "detail": f"name={'✓' if self.frontmatter.get('name') else '✗'}, "
                      f"description={'✓' if self.frontmatter.get('description') else '✗'}",
        })
        issues.extend(fm_issues)
        if fm_score < 0.7:
            recommendations.append("确保 frontmatter 包含 name 和至少 30 词的 description")

        # ── 检查 3：分层合理性 ──
        layering_score, layering_issues = _check_layering(self.skill_path, self.body)
        checks.append({
            "id": "layering",
            "name": "分层合理性",
            "weight": "high",
            "score": layering_score,
            "detail": "检查详细规范是否放在 references/ 中",
        })
        issues.extend(layering_issues)

        # ── 检查 4：References 引用指引 ──
        ref_guidance_score = _check_reference_guidance(self.body)
        checks.append({
            "id": "reference_guidance",
            "name": "References 引用指引",
            "weight": "medium",
            "score": ref_guidance_score,
            "detail": "检查是否说明何时读取哪个 reference",
        })
        if ref_guidance_score < 0.5:
            recommendations.append("在 SKILL.md 中明确说明'在 [场景] 时读取 references/[文件]'")

        # ── 检查 5：无硬编码业务数据 ──
        hardcode_score, hardcode_issues = _check_hardcoded_data(self.body)
        checks.append({
            "id": "no_hardcoded_data",
            "name": "无硬编码业务数据",
            "weight": "medium",
            "score": hardcode_score,
            "detail": "检查是否含会过时的具体数据（年份、URL、版本号等）",
        })
        issues.extend(hardcode_issues)

        # ── 综合评分 ──
        weights = {"high": 3, "medium": 2, "low": 1}
        total_w = sum(weights[c["weight"]] for c in checks)
        score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

        return {
            "name": "结构合规",
            "id": "structure",
            "score": round(score, 4),
            "checks": checks,
            "issues": issues[:10],
            "recommendations": recommendations,
            "metadata": {
                "line_count": line_count,
                "has_frontmatter": bool(self.frontmatter),
                "skill_name": self.frontmatter.get("name", ""),
                "description_word_count": len(
                    str(self.frontmatter.get("description", "")).split()
                ),
            },
        }


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter（--- 块）。"""
    import yaml

    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = {}

    return fm, parts[2].strip()


def _check_frontmatter(fm: dict) -> tuple[float, list[str]]:
    issues = []
    score = 1.0

    if not fm.get("name"):
        issues.append("frontmatter 缺少 name 字段")
        score -= 0.3

    desc = str(fm.get("description", "")).strip()
    desc_words = len(desc.split())
    if not desc:
        issues.append("frontmatter 缺少 description 字段")
        score -= 0.4
    elif desc_words < 30:
        issues.append(f"description 过短（{desc_words} 词，建议 ≥ 30 词）")
        score -= 0.2

    return max(0.0, score), issues


def _check_layering(skill_path: str, body: str) -> tuple[float, list[str]]:
    """检查是否有 references/ 目录或合理分层。"""
    skill_dir = os.path.dirname(skill_path)
    ref_dir = os.path.join(skill_dir, "references")
    has_ref_dir = os.path.isdir(ref_dir)

    # 检查 body 中是否提到 references
    mentions_references = bool(
        re.search(r"references?/|reference file|read.*reference", body, re.IGNORECASE)
    )

    issues = []
    if not has_ref_dir and not mentions_references:
        issues.append("未发现 references/ 目录，详细规范可能都堆在 SKILL.md 中")
        return 0.4, issues
    elif has_ref_dir:
        return 1.0, []
    else:
        return 0.7, []


def _check_reference_guidance(body: str) -> float:
    """检查是否有'何时读哪个 reference'的指引。"""
    guidance_patterns = [
        r"when.*read.*references?/",
        r"see.*references?/",
        r"references?/\S+\.(md|txt|yaml|json)",
        r"load.*references?",
    ]
    for pattern in guidance_patterns:
        if re.search(pattern, body, re.IGNORECASE):
            return 1.0
    return 0.3


def _check_hardcoded_data(body: str) -> tuple[float, list[str]]:
    """检查是否含会过时的硬编码数据。"""
    issues = []
    deductions = 0

    # 检查硬编码年份（如 2024、2025）
    year_matches = re.findall(r"\b20[2-3]\d\b", body)
    if len(year_matches) > 2:
        issues.append(f"包含 {len(year_matches)} 处硬编码年份，可能会过时")
        deductions += 0.2

    # 检查硬编码 URL
    url_matches = re.findall(r"https?://[^\s\)\"'>]+", body)
    if len(url_matches) > 3:
        issues.append(f"包含 {len(url_matches)} 处硬编码 URL，建议移至 references/")
        deductions += 0.2

    # 检查版本号
    version_matches = re.findall(r"\bv?\d+\.\d+\.\d+\b", body)
    if len(version_matches) > 2:
        issues.append(f"包含 {len(version_matches)} 处具体版本号，建议改为'最新版'")
        deductions += 0.1

    return max(0.0, 1.0 - deductions), issues
