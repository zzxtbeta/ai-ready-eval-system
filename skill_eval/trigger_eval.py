"""
skill_eval/trigger_eval.py — 触发准确率评估

构造 should/should-not trigger eval 集，通过 LLM 判断触发准确性。
依据：Anthropic skill-creator — 构造 eval 集，分 60%/40% 训练/测试，迭代优化
"""

from __future__ import annotations

import json
import os
import re
from typing import Any


class TriggerEvaluator:
    """评估 Skill 的触发准确率。"""

    def __init__(self, skill_path: str, llm_config: dict | None = None):
        self.skill_path = skill_path
        self.llm_config = llm_config or {}
        self.frontmatter: dict = {}
        self.description = ""

    def load(self) -> bool:
        if not os.path.exists(self.skill_path):
            return False
        with open(self.skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.frontmatter, _ = _parse_frontmatter(content)
        self.description = str(self.frontmatter.get("description", ""))
        return bool(self.description)

    def run(self, eval_set: list[dict] | None = None) -> dict:
        """
        运行触发准确率评估。

        Args:
            eval_set: [{"prompt": str, "should_trigger": bool}, ...]
                     如果为 None，使用 LLM 自动生成 eval 集

        Returns:
            dict: 评估结果
        """
        if not self.description and not self.load():
            return _error_result("无法加载 Skill 文件或缺少 description")

        if eval_set is None:
            eval_set = self._generate_eval_set()

        if not eval_set:
            return _error_result("eval 集为空")

        results = []
        for item in eval_set:
            prompt = item["prompt"]
            should_trigger = item["should_trigger"]
            actually_triggered = self._judge_trigger(prompt)
            correct = actually_triggered == should_trigger
            results.append({
                "prompt": prompt,
                "should_trigger": should_trigger,
                "actually_triggered": actually_triggered,
                "correct": correct,
            })

        # 计算指标
        total = len(results)
        correct_count = sum(1 for r in results if r["correct"])
        should_trigger_items = [r for r in results if r["should_trigger"]]
        should_not_trigger_items = [r for r in results if not r["should_trigger"]]

        sensitivity = (
            sum(1 for r in should_trigger_items if r["actually_triggered"]) / len(should_trigger_items)
            if should_trigger_items else 1.0
        )
        specificity = (
            sum(1 for r in should_not_trigger_items if not r["actually_triggered"]) / len(should_not_trigger_items)
            if should_not_trigger_items else 1.0
        )
        accuracy = correct_count / total if total > 0 else 0.0

        # 综合得分：sensitivity 和 specificity 各占一半
        score = (sensitivity + specificity) / 2

        checks = [
            {
                "id": "should_trigger_accuracy",
                "name": "Should-trigger 准确率",
                "weight": "high",
                "score": sensitivity,
                "detail": f"{sum(1 for r in should_trigger_items if r['actually_triggered'])}/{len(should_trigger_items)} 正例正确触发",
            },
            {
                "id": "should_not_trigger_accuracy",
                "name": "Should-not-trigger 准确率",
                "weight": "high",
                "score": specificity,
                "detail": f"{sum(1 for r in should_not_trigger_items if not r['actually_triggered'])}/{len(should_not_trigger_items)} 反例未触发",
            },
            {
                "id": "eval_set_size",
                "name": "Eval 集规模",
                "weight": "medium",
                "score": min(total / 20, 1.0),
                "detail": f"{total} 条 eval（建议 ≥ 20 条）",
            },
        ]

        issues = []
        recommendations = []
        if sensitivity < 0.9:
            issues.append(f"Should-trigger 准确率 {sensitivity:.0%}（目标 > 90%）")
            recommendations.append("扩展 description，覆盖更多触发场景的表达方式")
        if specificity < 0.9:
            issues.append(f"Should-not-trigger 准确率 {specificity:.0%}（目标 > 90%）")
            recommendations.append("收紧 description，避免描述过宽导致误触发")

        return {
            "name": "触发准确率",
            "id": "trigger_accuracy",
            "score": round(score, 4),
            "checks": checks,
            "issues": issues,
            "recommendations": recommendations,
            "eval_results": results[:20],  # 最多返回 20 条
            "metadata": {
                "eval_count": total,
                "accuracy": round(accuracy, 4),
                "sensitivity": round(sensitivity, 4),
                "specificity": round(specificity, 4),
            },
        }

    def _judge_trigger(self, prompt: str) -> bool:
        """判断给定 prompt 是否应该触发此 Skill。"""
        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key", "")

        if not api_key:
            # 无 LLM 时用关键词匹配（降级方案）
            return _keyword_trigger_judge(prompt, self.description)

        try:
            if provider == "openai":
                return self._openai_judge(prompt)
            elif provider == "anthropic":
                return self._anthropic_judge(prompt)
        except Exception:
            pass

        return _keyword_trigger_judge(prompt, self.description)

    def _openai_judge(self, prompt: str) -> bool:
        from openai import OpenAI
        api_key = self.llm_config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        client = OpenAI(api_key=api_key)
        model = self.llm_config.get("model", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are evaluating whether to activate a skill.\n"
                        f"Skill description: {self.description}\n\n"
                        f"Reply with ONLY 'YES' or 'NO'."
                    ),
                },
                {"role": "user", "content": f"User message: {prompt}\n\nShould this skill be activated?"},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        return "yes" in (response.choices[0].message.content or "").lower()

    def _anthropic_judge(self, prompt: str) -> bool:
        import anthropic
        api_key = self.llm_config.get("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
        client = anthropic.Anthropic(api_key=api_key)
        model = self.llm_config.get("model", "claude-3-haiku-20240307")
        message = client.messages.create(
            model=model,
            max_tokens=5,
            system=(
                f"You are evaluating whether to activate a skill.\n"
                f"Skill description: {self.description}\n\n"
                f"Reply with ONLY 'YES' or 'NO'."
            ),
            messages=[{"role": "user", "content": f"User message: {prompt}\n\nShould this skill be activated?"}],
        )
        return "yes" in (message.content[0].text or "").lower()

    def _generate_eval_set(self) -> list[dict]:
        """基于 description 自动生成最小 eval 集（无 LLM 时用规则生成）。"""
        # 简单的规则式生成（有 LLM 时可替换为 LLM 生成）
        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key", "")

        if api_key:
            try:
                return self._llm_generate_eval_set()
            except Exception:
                pass

        return _rule_based_eval_set(self.description)

    def _llm_generate_eval_set(self) -> list[dict]:
        """用 LLM 生成 eval 集。"""
        provider = self.llm_config.get("provider", "openai")
        api_key = self.llm_config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        model = self.llm_config.get("model", "gpt-4o-mini")

        system = """Generate a trigger evaluation set for a skill.
Return JSON array of 20 items: [{"prompt": "...", "should_trigger": true/false}, ...]
10 items where user intent matches the skill (should_trigger=true)
10 items where user intent does NOT match (should_trigger=false)
Include edge cases, synonyms, and ambiguous phrasings."""

        user = f"Skill description: {self.description}"

        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            items = data if isinstance(data, list) else data.get("items", data.get("eval_set", []))
            return items[:20]

        return _rule_based_eval_set(self.description)


def _keyword_trigger_judge(prompt: str, description: str) -> bool:
    """基于关键词重叠的降级触发判断（无 LLM 时使用）。"""
    desc_words = set(re.findall(r"\w+", description.lower()))
    prompt_words = set(re.findall(r"\w+", prompt.lower()))
    # 停用词
    stopwords = {"a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
                 "have", "has", "had", "do", "does", "did", "will", "would", "could",
                 "should", "may", "might", "shall", "can", "need", "dare", "ought",
                 "i", "you", "he", "she", "it", "we", "they", "this", "that", "and",
                 "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
    desc_meaningful = desc_words - stopwords
    prompt_meaningful = prompt_words - stopwords
    if not desc_meaningful:
        return False
    overlap = len(desc_meaningful & prompt_meaningful) / len(desc_meaningful)
    return overlap > 0.15


def _rule_based_eval_set(description: str) -> list[dict]:
    """为演示目的生成最小 eval 集（实际项目应用 LLM 生成）。"""
    # 提取关键词
    words = [w for w in re.findall(r"\w+", description.lower()) if len(w) > 3][:5]
    name_guess = description.split(".")[0][:30] if description else "this task"

    return [
        {"prompt": f"Help me with {name_guess}", "should_trigger": True},
        {"prompt": f"I need to {words[0] if words else 'do'} something", "should_trigger": True},
        {"prompt": "What's the weather today?", "should_trigger": False},
        {"prompt": "Write me a poem about cats", "should_trigger": False},
        {"prompt": f"Can you {name_guess}?", "should_trigger": True},
        {"prompt": "What is 2+2?", "should_trigger": False},
        {"prompt": f"I have a question about {words[1] if len(words)>1 else 'this'}", "should_trigger": True},
        {"prompt": "Order me a pizza", "should_trigger": False},
        {"prompt": f"How do I {words[0] if words else 'start'}?", "should_trigger": True},
        {"prompt": "Tell me a joke", "should_trigger": False},
    ]


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
        "name": "触发准确率",
        "id": "trigger_accuracy",
        "score": 0.0,
        "checks": [],
        "issues": [reason],
        "recommendations": [],
    }
