"""
api_eval/agent_trial.py — Agent 试用层

给 LLM agent 提供 OpenAPI spec，要求其完成任务，
记录调用链并分析失败原因。

这是最有价值的测试层：模拟真实 agent 使用 API 的全过程。
"""

from __future__ import annotations

import json
import os
from typing import Any


class AgentTrialRunner:
    """
    让 LLM agent 尝试使用 API 完成任务，评估 API 对 agent 的实际可用性。
    """

    def __init__(self, spec_path: str, llm_config: dict | None = None):
        self.spec_path = spec_path
        self.llm_config = llm_config or {}
        self.spec_content = ""
        self._client = None

    def load_spec(self) -> str:
        """加载 spec 文件内容（作为文本传给 LLM）。"""
        if not os.path.exists(self.spec_path):
            return ""
        with open(self.spec_path, "r", encoding="utf-8") as f:
            self.spec_content = f.read()
        return self.spec_content

    def run_trial(self, task: str, base_url: str = "") -> dict:
        """
        运行单次 Agent 试用。

        Args:
            task: 任务描述，如 "获取所有待处理的任务列表，并找到最高优先级的那个"
            base_url: API base URL（可选，用于 agent 构造真实请求）

        Returns:
            dict: {
                "task": str,
                "thought_chain": list[str],
                "api_calls": list[dict],
                "success": bool,
                "failure_reason": str,
                "score": float
            }
        """
        if not self.spec_content:
            self.load_spec()

        provider = self.llm_config.get("provider", "openai")

        try:
            if provider == "openai":
                return self._run_openai_trial(task, base_url)
            elif provider == "anthropic":
                return self._run_anthropic_trial(task, base_url)
            else:
                return self._run_mock_trial(task)
        except ImportError as e:
            return {
                "task": task,
                "thought_chain": [],
                "api_calls": [],
                "success": False,
                "failure_reason": f"LLM client 未安装: {e}",
                "score": 0.0,
                "error": str(e),
            }
        except Exception as e:
            return {
                "task": task,
                "thought_chain": [],
                "api_calls": [],
                "success": False,
                "failure_reason": f"试用出错: {e}",
                "score": 0.0,
                "error": str(e),
            }

    def _run_openai_trial(self, task: str, base_url: str) -> dict:
        from openai import OpenAI

        api_key = self.llm_config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        if not api_key:
            return self._run_mock_trial(task, reason="OPENAI_API_KEY 未配置")

        client = OpenAI(api_key=api_key)
        model = self.llm_config.get("model", "gpt-4o")

        system_prompt = _build_system_prompt(self.spec_content, base_url)
        user_prompt = _build_user_prompt(task)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=2000,
        )

        raw_output = response.choices[0].message.content or ""
        return _parse_agent_output(task, raw_output)

    def _run_anthropic_trial(self, task: str, base_url: str) -> dict:
        import anthropic

        api_key = self.llm_config.get("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
        if not api_key:
            return self._run_mock_trial(task, reason="ANTHROPIC_API_KEY 未配置")

        client = anthropic.Anthropic(api_key=api_key)
        model = self.llm_config.get("model", "claude-3-5-sonnet-20241022")

        system_prompt = _build_system_prompt(self.spec_content, base_url)
        user_prompt = _build_user_prompt(task)

        message = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_output = message.content[0].text if message.content else ""
        return _parse_agent_output(task, raw_output)

    def _run_mock_trial(self, task: str, reason: str = "Mock 模式") -> dict:
        """在无 LLM 配置时返回 mock 结果（用于演示）。"""
        return {
            "task": task,
            "thought_chain": [
                "分析 API spec，寻找相关端点...",
                "发现候选端点，检查参数要求...",
                "构造请求参数（Mock 模式，未实际发送）...",
            ],
            "api_calls": [
                {
                    "endpoint": "GET /tasks",
                    "params": {"status": "pending", "limit": 10},
                    "simulated": True,
                    "success": True,
                }
            ],
            "success": True,
            "failure_reason": "",
            "score": 0.7,
            "mock": True,
            "mock_reason": reason,
        }

    def run_batch(self, tasks: list[str], base_url: str = "") -> dict:
        """运行多个任务，计算综合 Agent 成功率。"""
        results = []
        for task in tasks:
            result = self.run_trial(task, base_url)
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        avg_score = sum(r.get("score", 0) for r in results) / len(results) if results else 0.0

        return {
            "trial_count": len(results),
            "success_count": success_count,
            "success_rate": success_count / len(results) if results else 0.0,
            "average_score": round(avg_score, 4),
            "results": results,
        }


def _build_system_prompt(spec_content: str, base_url: str) -> str:
    base_url_line = f"\nAPI Base URL: {base_url}" if base_url else ""
    # 截断超长 spec，避免 context 爆炸
    spec_excerpt = spec_content[:8000] if len(spec_content) > 8000 else spec_content
    return f"""You are an API agent. You have access to the following API specification:

{spec_excerpt}{base_url_line}

When given a task, analyze the spec and determine:
1. Which endpoints to call
2. What parameters to use
3. In what order to make calls

Respond in JSON format with this structure:
{{
  "thought_chain": ["step 1 reasoning", "step 2 reasoning", ...],
  "api_calls": [
    {{
      "endpoint": "METHOD /path",
      "params": {{}},
      "headers": {{}},
      "body": null,
      "reasoning": "why this call"
    }}
  ],
  "success": true/false,
  "failure_reason": "if failed, explain why",
  "confidence": 0.0-1.0
}}

If the API spec is unclear or missing information needed to complete the task,
set success=false and explain what information was missing."""


def _build_user_prompt(task: str) -> str:
    return f"Task: {task}\n\nPlan and describe the API calls needed to complete this task."


def _parse_agent_output(task: str, raw_output: str) -> dict:
    """解析 LLM 输出，提取 API 调用链和成功状态。"""
    # 提取 JSON 块
    import re
    json_match = re.search(r"\{[\s\S]*\}", raw_output)
    if json_match:
        try:
            data = json.loads(json_match.group())
            confidence = float(data.get("confidence", 0.7))
            success = bool(data.get("success", True))
            return {
                "task": task,
                "thought_chain": data.get("thought_chain", []),
                "api_calls": data.get("api_calls", []),
                "success": success,
                "failure_reason": data.get("failure_reason", ""),
                "score": confidence if success else confidence * 0.3,
                "raw_output": raw_output[:500],
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # fallback：分析关键词判断成功/失败
    failed_keywords = ["cannot", "unclear", "missing", "not defined", "no endpoint"]
    success = not any(kw in raw_output.lower() for kw in failed_keywords)
    return {
        "task": task,
        "thought_chain": [],
        "api_calls": [],
        "success": success,
        "failure_reason": raw_output[:200] if not success else "",
        "score": 0.5,
        "raw_output": raw_output[:500],
    }
