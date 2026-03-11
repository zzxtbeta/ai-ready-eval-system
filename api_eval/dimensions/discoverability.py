"""
维度 4：可发现性（Discoverability）

检查 API 的 OpenAPI spec 格式合法性、可访问入口、与实现的一致性。
依据：The New Stack - MCP Server、llms.txt、Arazzo 等发现机制讨论
"""

from __future__ import annotations
import re
from typing import Any


def evaluate(spec: dict, spec_path: str = "") -> dict:
    """
    评估 API 可发现性。

    Args:
        spec: 已解析的 OpenAPI spec dict
        spec_path: spec 文件路径或 URL

    Returns:
        dict: 与其他维度同格式的评估结果
    """
    checks = []
    issues = []
    recommendations = []

    # ── 检查 1：OpenAPI spec 可访问（通过文件路径/URL 判断）──
    spec_accessible = bool(spec and spec_path)
    checks.append({
        "id": "spec_accessible",
        "name": "OpenAPI spec 可访问",
        "weight": "high",
        "score": 1.0 if spec_accessible else 0.0,
        "detail": f"Spec 已从 {spec_path or '未知'} 加载" if spec_accessible else "无法访问 spec",
    })
    if not spec_accessible:
        issues.append("OpenAPI spec 不可访问，agent 工具链无法自动导入")

    # ── 检查 2：Spec 格式有效性 ──
    format_score, format_issues = _check_spec_format(spec)
    checks.append({
        "id": "spec_format_valid",
        "name": "Spec 格式有效性",
        "weight": "high",
        "score": format_score,
        "detail": f"格式检查{'通过' if format_score == 1.0 else '存在问题'}",
    })
    issues.extend(format_issues)

    # ── 检查 3：MCP Server 支持 ──
    # 检查 spec 中是否有 x-mcp 扩展字段或 x-ai-agent 提示
    has_mcp = _check_mcp_hints(spec)
    checks.append({
        "id": "mcp_support",
        "name": "MCP Server 支持",
        "weight": "medium",
        "score": 1.0 if has_mcp else 0.0,
        "detail": "发现 MCP 扩展字段" if has_mcp else "无 MCP Server 封装",
    })
    if not has_mcp:
        recommendations.append("提供 MCP Server 封装（x-mcp 扩展或独立 MCP 包），降低 agent 集成成本")

    # ── 检查 4：llms.txt ──
    # 静态检查 spec info 中是否有 llms.txt 链接提示
    has_llms_txt = _check_llms_txt_hint(spec)
    checks.append({
        "id": "llms_txt",
        "name": "llms.txt 支持",
        "weight": "low",
        "score": 1.0 if has_llms_txt else 0.0,
        "detail": "发现 llms.txt 引用" if has_llms_txt else "未发现 llms.txt 引用",
    })

    # ── 检查 5：Spec-实现一致性（静态层面）──
    # 检查 spec 是否有冗余定义、循环引用、$ref 断链等问题
    consistency_score, consistency_issues = _check_spec_consistency(spec)
    checks.append({
        "id": "spec_consistency",
        "name": "Spec 内部一致性",
        "weight": "high",
        "score": consistency_score,
        "detail": f"内部一致性检查，{len(consistency_issues)} 个问题",
    })
    issues.extend(consistency_issues)
    if consistency_score < 0.8:
        recommendations.append("修复 spec 中的 $ref 断链和未定义引用，确保解析工具可正常消费")

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    if not has_llms_txt:
        recommendations.append("在域名根目录添加 llms.txt，提升被 AI 爬虫发现的概率")

    return {
        "name": "可发现性",
        "id": "discoverability",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def _check_spec_format(spec: dict) -> tuple[float, list[str]]:
    """检查 spec 基础格式合规性。"""
    issues = []

    if not spec:
        return 0.0, ["spec 为空"]

    # 检查 openapi 版本
    version = spec.get("openapi", "")
    if not version:
        issues.append("缺少 openapi 版本字段（应为 3.0.x 或 3.1.x）")
    elif not version.startswith("3."):
        issues.append(f"openapi 版本 {version} 过旧，建议升级到 3.0+")

    # 检查 info 字段
    info = spec.get("info", {})
    if not info.get("title"):
        issues.append("缺少 info.title")
    if not info.get("version"):
        issues.append("缺少 info.version")
    if not info.get("description"):
        issues.append("缺少 info.description（影响 agent 理解 API 整体用途）")

    # 检查 paths
    if not spec.get("paths"):
        issues.append("paths 为空，没有任何端点定义")

    score = max(0.0, 1.0 - len(issues) * 0.15)
    return score, issues


def _check_mcp_hints(spec: dict) -> bool:
    """检查 spec 中是否有 MCP 或 AI agent 相关扩展。"""
    # 检查常见 MCP/agent 扩展字段
    ai_extensions = {"x-mcp", "x-ai-agent", "x-agent", "x-llm", "x-openai-plugin"}
    
    spec_str = str(spec).lower()
    for ext in ai_extensions:
        if ext in spec_str:
            return True
    
    # 检查 external docs 中是否有 mcp 引用
    external_docs = spec.get("externalDocs", {})
    if "mcp" in str(external_docs).lower():
        return True

    return False


def _check_llms_txt_hint(spec: dict) -> bool:
    """检查 spec 中是否有 llms.txt 引用。"""
    spec_str = str(spec).lower()
    return "llms.txt" in spec_str or "llms-full.txt" in spec_str


def _check_spec_consistency(spec: dict) -> tuple[float, list[str]]:
    """检查 spec 内部一致性（断链引用、未使用 schema 等）。"""
    issues = []

    components_schemas = set(
        spec.get("components", {}).get("schemas", {}).keys()
    )
    components_params = set(
        spec.get("components", {}).get("parameters", {}).keys()
    )

    # 递归找所有 $ref
    refs = _find_refs(spec)
    broken_refs = []
    for ref in refs:
        if ref.startswith("#/components/schemas/"):
            name = ref.split("/")[-1]
            if name not in components_schemas:
                broken_refs.append(ref)
        elif ref.startswith("#/components/parameters/"):
            name = ref.split("/")[-1]
            if name not in components_params:
                broken_refs.append(ref)

    for ref in broken_refs[:5]:
        issues.append(f"断链 $ref: {ref}")

    score = max(0.0, 1.0 - len(broken_refs) * 0.2)
    return score, issues


def _find_refs(obj: Any, refs: list | None = None) -> list[str]:
    """递归找 spec 中所有 $ref 值。"""
    if refs is None:
        refs = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str):
                refs.append(v)
            else:
                _find_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _find_refs(item, refs)
    return refs
