"""
api_eval/scanner.py — 静态扫描器

解析 OpenAPI spec（本地文件或 URL），运行静态维度评估：
  - 维度 1：语义描述完整性
  - 维度 4：可发现性
  - 维度 5：工作流文档化
  - 维度 6：设计一致性
  - 维度 7：流量韧性（静态部分）
  - 维度 8：安全就绪
  以及响应体量控制（静态部分）、错误质量（静态部分）
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

import yaml


class APIScanner:
    """静态扫描器：加载并解析 OpenAPI spec，运行所有静态维度评估。"""

    def __init__(self, spec_path: str):
        """
        Args:
            spec_path: OpenAPI spec 的本地路径或 URL
        """
        self.spec_path = spec_path
        self.spec: dict = {}
        self._load_errors: list[str] = []

    def load(self) -> bool:
        """
        加载 OpenAPI spec。

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if self.spec_path.startswith(("http://", "https://")):
                with urllib.request.urlopen(self.spec_path, timeout=10) as resp:
                    content = resp.read().decode("utf-8")
            else:
                if not os.path.exists(self.spec_path):
                    self._load_errors.append(f"文件不存在: {self.spec_path}")
                    return False
                with open(self.spec_path, "r", encoding="utf-8") as f:
                    content = f.read()

            if self.spec_path.endswith(".json") or content.lstrip().startswith("{"):
                self.spec = json.loads(content)
            else:
                self.spec = yaml.safe_load(content) or {}

            return bool(self.spec)

        except Exception as e:
            self._load_errors.append(f"加载失败: {e}")
            return False

    def run(self) -> dict:
        """
        运行所有静态评估维度。

        Returns:
            dict: {
                "spec_loaded": bool,
                "spec_path": str,
                "dimensions": list[dict],
                "load_errors": list[str]
            }
        """
        if not self.spec:
            loaded = self.load()
        else:
            loaded = True

        if not loaded:
            return {
                "spec_loaded": False,
                "spec_path": self.spec_path,
                "dimensions": [],
                "load_errors": self._load_errors,
            }

        from api_eval.dimensions import semantic_description
        from api_eval.dimensions import discoverability
        from api_eval.dimensions import response_sizing
        from api_eval.dimensions import error_quality
        from api_eval.dimensions import workflow_documentation
        from api_eval.dimensions import design_consistency
        from api_eval.dimensions import traffic_resilience
        from api_eval.dimensions import security_readiness

        dimensions = []

        try:
            dimensions.append(semantic_description.evaluate(self.spec))
        except Exception as e:
            dimensions.append(_error_dimension("语义描述完整性", "semantic_description", str(e)))

        try:
            dim = response_sizing.evaluate_static(self.spec)
            dimensions.append(dim)
        except Exception as e:
            dimensions.append(_error_dimension("响应体量控制", "response_sizing", str(e)))

        try:
            dim = error_quality.evaluate_static(self.spec)
            dimensions.append(dim)
        except Exception as e:
            dimensions.append(_error_dimension("错误语义质量", "error_quality", str(e)))

        try:
            dimensions.append(discoverability.evaluate(self.spec, self.spec_path))
        except Exception as e:
            dimensions.append(_error_dimension("可发现性", "discoverability", str(e)))

        try:
            dimensions.append(workflow_documentation.evaluate(self.spec))
        except Exception as e:
            dimensions.append(_error_dimension("工作流文档化", "workflow_documentation", str(e)))

        try:
            dimensions.append(design_consistency.evaluate(self.spec))
        except Exception as e:
            dimensions.append(_error_dimension("设计一致性", "design_consistency", str(e)))

        try:
            dimensions.append(traffic_resilience.evaluate_static(self.spec))
        except Exception as e:
            dimensions.append(_error_dimension("流量韧性", "traffic_resilience", str(e)))

        try:
            dimensions.append(security_readiness.evaluate(self.spec))
        except Exception as e:
            dimensions.append(_error_dimension("安全就绪", "security_readiness", str(e)))

        return {
            "spec_loaded": True,
            "spec_path": self.spec_path,
            "spec_info": _extract_spec_info(self.spec),
            "dimensions": dimensions,
            "load_errors": self._load_errors,
        }


def _extract_spec_info(spec: dict) -> dict:
    """提取 spec 基础信息用于报告展示。"""
    info = spec.get("info", {})
    paths = spec.get("paths", {})

    endpoint_count = sum(
        sum(1 for m in path_item.keys() if m.lower() in {"get", "post", "put", "patch", "delete"})
        for path_item in paths.values()
        if isinstance(path_item, dict)
    )

    return {
        "title": info.get("title", "Unknown API"),
        "version": info.get("version", ""),
        "description": info.get("description", ""),
        "openapi_version": spec.get("openapi", ""),
        "endpoint_count": endpoint_count,
        "path_count": len(paths),
        "has_components": bool(spec.get("components")),
        "has_security": bool(spec.get("security") or spec.get("components", {}).get("securitySchemes")),
    }


def _error_dimension(name: str, dim_id: str, error: str) -> dict:
    return {
        "name": name,
        "id": dim_id,
        "score": 0.0,
        "checks": [],
        "issues": [f"评估出错: {error}"],
        "recommendations": [],
        "error": error,
    }
