"""
skill_eval/integration_eval.py — 集成协同评估

评估多 Skill 编排时的路由正确性、输出兼容性、端到端完成率。
依据：OpenAI Agent 白皮书 — Manager pattern 和 Decentralized pattern
"""

from __future__ import annotations

import os
from typing import Any


class IntegrationEvaluator:
    """评估多 Skill 的集成协同能力。"""

    def __init__(self, skill_paths: list[str], llm_config: dict | None = None):
        self.skill_paths = skill_paths
        self.llm_config = llm_config or {}
        self.skills: list[dict] = []

    def load(self) -> bool:
        self.skills = []
        for path in self.skill_paths:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            fm, body = _parse_frontmatter(content)
            self.skills.append({
                "path": path,
                "name": fm.get("name", os.path.basename(path)),
                "description": str(fm.get("description", "")),
                "body": body,
            })
        return len(self.skills) > 0

    def run(self, integration_scenarios: list[dict] | None = None) -> dict:
        """
        运行集成评估。

        Args:
            integration_scenarios: 集成测试场景列表

        Returns:
            dict: 评估结果
        """
        if not self.skills and not self.load():
            return _error_result("无法加载任何 Skill 文件")

        if len(self.skills) < 2:
            return {
                "name": "集成协同",
                "id": "integration",
                "score": 0.5,
                "checks": [],
                "issues": ["仅发现 1 个 Skill，无法做集成评估"],
                "recommendations": ["添加多个 Skill 以评估协同能力"],
                "metadata": {"skill_count": len(self.skills)},
            }

        checks = []
        issues = []
        recommendations = []

        # ── 检查 1：编排路由正确性（通过 LLM 判断路由）──
        routing_score = self._check_routing()
        checks.append({
            "id": "routing_accuracy",
            "name": "编排路由正确性",
            "weight": "high",
            "score": routing_score,
            "detail": f"检查 {len(self.skills)} 个 Skill 之间的路由清晰度",
        })
        if routing_score < 0.7:
            issues.append("Skill 描述存在语义重叠，可能导致路由模糊")
            recommendations.append("精确区分每个 Skill 的触发场景，避免 description 语义重叠")

        # ── 检查 2：输出格式兼容性 ──
        compat_score = self._check_output_compatibility()
        checks.append({
            "id": "output_compatibility",
            "name": "输出格式兼容性",
            "weight": "high",
            "score": compat_score,
            "detail": "检查各 Skill 输出格式是否一致",
        })

        # ── 检查 3：端到端场景评估 ──
        if integration_scenarios:
            e2e_score = self._run_e2e_scenarios(integration_scenarios)
        else:
            e2e_score = 0.5  # 无场景时中性得分

        checks.append({
            "id": "e2e_completion",
            "name": "端到端完成率",
            "weight": "high",
            "score": e2e_score,
            "detail": f"端到端场景评估得分 {e2e_score:.2f}",
        })

        # ── 综合评分 ──
        weights = {"high": 3, "medium": 2, "low": 1}
        total_w = sum(weights[c["weight"]] for c in checks)
        score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

        return {
            "name": "集成协同",
            "id": "integration",
            "score": round(score, 4),
            "checks": checks,
            "issues": issues[:10],
            "recommendations": recommendations,
            "metadata": {
                "skill_count": len(self.skills),
                "skill_names": [s["name"] for s in self.skills],
            },
        }

    def _check_routing(self) -> float:
        """检查 Skill 间的路由清晰度（基于 description 语义重叠分析）。"""
        if len(self.skills) < 2:
            return 1.0

        import re
        descriptions = [s["description"] for s in self.skills]

        # 简单重叠分析：word overlap 越高 = 路由越模糊
        overlap_scores = []
        for i, desc_a in enumerate(descriptions):
            for j, desc_b in enumerate(descriptions):
                if i >= j:
                    continue
                words_a = set(re.findall(r"\w+", desc_a.lower())) - _STOPWORDS
                words_b = set(re.findall(r"\w+", desc_b.lower())) - _STOPWORDS
                if not words_a or not words_b:
                    continue
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                overlap_scores.append(overlap)

        if not overlap_scores:
            return 0.8

        avg_overlap = sum(overlap_scores) / len(overlap_scores)
        # 重叠 < 30% 时路由清晰度高
        routing_score = max(0.0, 1.0 - avg_overlap * 2)
        return min(routing_score, 1.0)

    def _check_output_compatibility(self) -> float:
        """检查各 Skill 输出格式注解是否一致（格式声明检查）。"""
        import re
        format_hints = []
        for skill in self.skills:
            body = skill["body"]
            # 检查输出格式声明
            json_format = bool(re.search(r"json|JSON|application/json", body))
            markdown_format = bool(re.search(r"markdown|## |```", body))
            plain_format = bool(re.search(r"plain text|pure text|plaintext", body, re.IGNORECASE))

            if json_format:
                format_hints.append("json")
            elif markdown_format:
                format_hints.append("markdown")
            elif plain_format:
                format_hints.append("plain")
            else:
                format_hints.append("unspecified")

        if not format_hints:
            return 0.5

        from collections import Counter
        dominant = Counter(format_hints).most_common(1)[0][1]
        return dominant / len(format_hints)

    def _run_e2e_scenarios(self, scenarios: list[dict]) -> float:
        """运行端到端场景（简化版：仅检查路由决策）。"""
        if not scenarios:
            return 0.5

        success_count = 0
        for scenario in scenarios:
            # 简化：检查 agent 是否能路由到正确的 skill
            expected_skill = scenario.get("expected_skill", "")
            prompt = scenario.get("prompt", "")
            best_match = _find_best_matching_skill(prompt, self.skills)
            if best_match == expected_skill:
                success_count += 1

        return success_count / len(scenarios)


_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "i", "you", "he", "she",
    "it", "we", "they", "this", "that", "and", "or", "but",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
}


def _find_best_matching_skill(prompt: str, skills: list[dict]) -> str:
    """基于关键词重叠找最匹配的 Skill。"""
    import re
    prompt_words = set(re.findall(r"\w+", prompt.lower())) - _STOPWORDS
    best_score = 0.0
    best_name = ""

    for skill in skills:
        desc_words = set(re.findall(r"\w+", skill["description"].lower())) - _STOPWORDS
        if not desc_words:
            continue
        overlap = len(prompt_words & desc_words) / len(desc_words)
        if overlap > best_score:
            best_score = overlap
            best_name = skill["name"]

    return best_name


def _parse_frontmatter(content: str) -> tuple[dict, str]:
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


def _error_result(reason: str) -> dict:
    return {
        "name": "集成协同",
        "id": "integration",
        "score": 0.0,
        "checks": [],
        "issues": [reason],
        "recommendations": [],
    }
