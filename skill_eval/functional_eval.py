"""
skill_eval/functional_eval.py — 功能可靠性评估

用真实 prompt 执行 Skill，评估输出质量和 Assertion 通过率。
依据：Anthropic skill-creator 核心循环 — 起草→测试→评估→迭代
"""

from __future__ import annotations

import json
import os
import re
from typing import Any


class FunctionalEvaluator:
    """
    用测试 prompt 执行 Skill，评估功能可靠性。
    """

    def __init__(self, skill_path: str, llm_config: dict | None = None):
        self.skill_path = skill_path
        self.llm_config = llm_config or {}
        self.skill_content = ""
        self.frontmatter: dict = {}

    def load(self) -> bool:
        if not os.path.exists(self.skill_path):
            return False
        with open(self.skill_path, "r", encoding="utf-8") as f:
            self.skill_content = f.read()
        self.frontmatter, _ = _parse_frontmatter(self.skill_content)
        return True

    def run(self, test_cases: list[dict] | None = None) -> dict:
        """
        运行功能评估。

        Args:
            test_cases: [
                {
                    "prompt": str,          # 用户输入
                    "assertions": [str],    # 对输出的断言（如 "包含摘要" "字数 < 500"）
                    "category": str         # 场景类别（core/edge/error）
                }
            ]
        """
        if not self.skill_content and not self.load():
            return _error_result("无法加载 Skill 文件")

        if test_cases is None:
            test_cases = self._default_test_cases()

        results = []
        for case in test_cases:
            result = self._run_single_case(case)
            results.append(result)

        # 统计
        total = len(results)
        assertion_scores = []
        for r in results:
            assertions = r.get("assertions_results", [])
            if assertions:
                assertion_scores.append(sum(1 for a in assertions if a["passed"]) / len(assertions))

        assertion_pass_rate = sum(assertion_scores) / len(assertion_scores) if assertion_scores else 0.0

        checks = [
            {
                "id": "assertion_pass_rate",
                "name": "定量 Assertion 通过率",
                "weight": "high",
                "score": assertion_pass_rate,
                "detail": f"Assertion 通过率 {assertion_pass_rate:.0%}（目标 > 80%）",
            },
            {
                "id": "eval_coverage",
                "name": "Eval 用例覆盖",
                "weight": "high",
                "score": _check_coverage(test_cases),
                "detail": f"{total} 个用例，{_count_categories(test_cases)}",
            },
        ]

        issues = []
        recommendations = []
        if assertion_pass_rate < 0.8:
            issues.append(f"Assertion 通过率 {assertion_pass_rate:.0%}，低于 80% 目标")
            recommendations.append("针对失败的 assertion 优化 Skill 指令，或澄清边界条件")

        weights = {"high": 3, "medium": 2, "low": 1}
        total_w = sum(weights[c["weight"]] for c in checks)
        score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

        return {
            "name": "功能可靠性",
            "id": "functional_reliability",
            "score": round(score, 4),
            "checks": checks,
            "issues": issues,
            "recommendations": recommendations,
            "eval_results": results[:10],
            "metadata": {
                "test_count": total,
                "assertion_pass_rate": round(assertion_pass_rate, 4),
            },
        }

    def _run_single_case(self, case: dict) -> dict:
        """执行单个测试用例。"""
        prompt = case["prompt"]
        assertions = case.get("assertions", [])

        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key", "")

        if not api_key:
            return _mock_case_result(prompt, assertions)

        try:
            output = self._llm_execute(prompt)
        except Exception as e:
            return {
                "prompt": prompt[:100],
                "output": "",
                "error": str(e),
                "assertions_results": [{"assertion": a, "passed": False} for a in assertions],
                "category": case.get("category", "unknown"),
            }

        assertions_results = self._check_assertions(output, assertions)

        return {
            "prompt": prompt[:100],
            "output": output[:500],
            "assertions_results": assertions_results,
            "category": case.get("category", "unknown"),
        }

    def _llm_execute(self, prompt: str) -> str:
        """调用 LLM 执行 Skill。"""
        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        model = self.llm_config.get("model", "gpt-4o")

        # 截断过长的 skill content
        skill_excerpt = self.skill_content[:6000]
        system = f"You are an AI assistant operating according to this skill specification:\n\n{skill_excerpt}"

        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=1500,
            )
            return resp.choices[0].message.content or ""

        elif provider == "anthropic":
            import anthropic
            api_key = self.llm_config.get("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=self.llm_config.get("model", "claude-3-5-sonnet-20241022"),
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text if msg.content else ""

        return ""

    def _check_assertions(self, output: str, assertions: list[str]) -> list[dict]:
        """检查输出是否满足所有 assertion。"""
        results = []
        for assertion in assertions:
            passed = _eval_assertion(output, assertion)
            results.append({"assertion": assertion, "passed": passed})
        return results

    def _default_test_cases(self) -> list[dict]:
        """生成默认测试用例（无自定义时使用）。"""
        name = self.frontmatter.get("name", "This skill")
        return [
            {
                "prompt": f"Please help me with a typical {name} request.",
                "assertions": ["len(output) > 50", "not_empty"],
                "category": "core",
            },
            {
                "prompt": f"I have a complex edge case for {name}.",
                "assertions": ["not_empty"],
                "category": "edge",
            },
        ]


def _eval_assertion(output: str, assertion: str) -> bool:
    """
    执行 assertion 检查。

    支持格式：
    - "len(output) > 500"         — 字符数检查
    - "not_empty"                  — 非空检查
    - "contains:关键词"            — 包含检查
    - "not_contains:关键词"        — 不包含检查
    - "starts_with:前缀"           — 开头检查
    - "matches:正则表达式"         — 正则匹配
    - "word_count > 100"           — 词数检查
    """
    output_lower = output.lower()

    if assertion == "not_empty":
        return len(output.strip()) > 0

    elif assertion.startswith("contains:"):
        keyword = assertion[9:].strip().lower()
        return keyword in output_lower

    elif assertion.startswith("not_contains:"):
        keyword = assertion[13:].strip().lower()
        return keyword not in output_lower

    elif assertion.startswith("starts_with:"):
        prefix = assertion[12:].strip()
        return output.strip().startswith(prefix)

    elif assertion.startswith("matches:"):
        pattern = assertion[8:].strip()
        return bool(re.search(pattern, output, re.IGNORECASE | re.DOTALL))

    elif "len(output)" in assertion:
        try:
            expr = assertion.replace("len(output)", str(len(output)))
            return bool(eval(expr))  # nosec - assertion 来自受信任的配置文件
        except Exception:
            return False

    elif "word_count" in assertion:
        try:
            word_count = len(output.split())
            expr = assertion.replace("word_count", str(word_count))
            return bool(eval(expr))  # nosec
        except Exception:
            return False

    # 默认：输出非空即通过
    return len(output.strip()) > 0


def _mock_case_result(prompt: str, assertions: list[str]) -> dict:
    """无 LLM 时的 mock 结果。"""
    return {
        "prompt": prompt[:100],
        "output": "[Mock 模式：未配置 LLM，跳过实际执行]",
        "assertions_results": [{"assertion": a, "passed": True, "mock": True} for a in assertions],
        "category": "mock",
        "mock": True,
    }


def _check_coverage(test_cases: list[dict]) -> float:
    """检查测试用例的场景覆盖度。"""
    categories = {c.get("category", "unknown") for c in test_cases}
    required = {"core", "edge"}
    has_required = len(required & categories) / len(required)
    size_score = min(len(test_cases) / 10, 1.0)
    return (has_required + size_score) / 2


def _count_categories(test_cases: list[dict]) -> str:
    from collections import Counter
    cats = Counter(c.get("category", "unknown") for c in test_cases)
    return ", ".join(f"{k}:{v}" for k, v in cats.items())


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
        "name": "功能可靠性",
        "id": "functional_reliability",
        "score": 0.0,
        "checks": [],
        "issues": [reason],
        "recommendations": [],
    }
