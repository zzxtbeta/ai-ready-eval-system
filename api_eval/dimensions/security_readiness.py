"""
维度 8：安全就绪（Security Readiness）

检查认证标准化、最小权限支持、敏感数据标记。
依据：Salt Security 报告；Nordic APIs 2026 预测 — agent 权限委托
"""

from __future__ import annotations


def evaluate(spec: dict) -> dict:
    checks = []
    issues = []
    recommendations = []

    security_schemes = spec.get("components", {}).get("securitySchemes", {})

    # ── 检查 1：认证标准化 ──
    auth_score, auth_issues = _check_auth_standard(security_schemes)
    checks.append({
        "id": "auth_standard",
        "name": "认证标准化",
        "weight": "high",
        "score": auth_score,
        "detail": f"认证方式: {list(security_schemes.keys()) or ['未定义']}",
    })
    issues.extend(auth_issues)
    if auth_score < 0.5:
        recommendations.append("使用 OAuth2（Authorization Code / Client Credentials）或标准 API Key，支持自动化认证流程")

    # ── 检查 2：最小权限（scope）支持 ──
    scope_score, scope_detail = _check_scope_support(security_schemes, spec)
    checks.append({
        "id": "scope_support",
        "name": "最小权限 Scope 支持",
        "weight": "high",
        "score": scope_score,
        "detail": scope_detail,
    })
    if scope_score < 0.5:
        issues.append("缺少细粒度 scope 控制，agent 可能获得过大权限")
        recommendations.append("为 OAuth2 定义细粒度 scope（如 tasks:read / tasks:write / admin）")

    # ── 检查 3：敏感数据标记 ──
    sensitive_score = _check_sensitive_data_marking(spec)
    checks.append({
        "id": "sensitive_data_marking",
        "name": "敏感数据标记",
        "weight": "medium",
        "score": sensitive_score,
        "detail": "检查敏感字段是否有 x-sensitive / writeOnly / format: password 等标记",
    })
    if sensitive_score < 0.5:
        recommendations.append("为密码、token、PII 等敏感字段添加 writeOnly: true 或 x-sensitive: true 标记")

    # ── 检查 4：API inventory 完整性（无 shadow endpoints）──
    # 静态检查：所有端点是否都有 security 定义
    inventory_score, inventory_issues = _check_security_coverage(spec)
    checks.append({
        "id": "security_coverage",
        "name": "端点安全定义覆盖率",
        "weight": "medium",
        "score": inventory_score,
        "detail": "检查每个端点是否有 security 定义或继承全局 security",
    })
    issues.extend(inventory_issues)
    if inventory_score < 0.7:
        recommendations.append("为所有端点显式定义 security 要求，避免存在未保护的端点")

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "安全就绪",
        "id": "security_readiness",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def _check_auth_standard(schemes: dict) -> tuple[float, list[str]]:
    """检查是否使用标准认证方式。"""
    if not schemes:
        return 0.0, ["未定义任何认证方式（securitySchemes 为空）"]

    issues = []
    standard_types = {"oauth2", "openIdConnect", "apiKey", "http"}
    non_standard = [
        name for name, scheme in schemes.items()
        if scheme.get("type", "").lower() not in {t.lower() for t in standard_types}
    ]

    # 优先选择 OAuth2
    has_oauth2 = any(
        scheme.get("type", "").lower() == "oauth2"
        for scheme in schemes.values()
    )

    score = 1.0 if has_oauth2 else (0.8 if not non_standard else 0.5)
    if non_standard:
        issues.append(f"非标准认证方式: {non_standard}")
    if not has_oauth2:
        issues.append("建议使用 OAuth2 支持 agent 权限委托")

    return score, issues


def _check_scope_support(schemes: dict, spec: dict) -> tuple[float, str]:
    """检查 OAuth2 scope 定义丰富度。"""
    if not schemes:
        return 0.0, "无认证方案"

    scopes_found = []
    for scheme in schemes.values():
        if scheme.get("type", "").lower() == "oauth2":
            flows = scheme.get("flows", {})
            for flow in flows.values():
                scopes_found.extend(flow.get("scopes", {}).keys())

    if not scopes_found:
        return 0.3, "OAuth2 未定义 scopes"

    # scope 数量越多、越细粒度越好
    score = min(len(scopes_found) / 4, 1.0)  # 4 个 scope 以上得满分
    return score, f"定义了 {len(scopes_found)} 个 scope: {scopes_found[:5]}"


def _check_sensitive_data_marking(spec: dict) -> float:
    """检查 schema 中是否有敏感字段标记。"""
    sensitive_field_patterns = {"password", "token", "secret", "private_key", "api_key", "credential"}
    sensitive_markers = {"writeOnly", "x-sensitive", "x-pii"}

    marked = 0
    potentially_sensitive = 0

    def _scan(schema: dict, field_name: str = "", depth: int = 0):
        nonlocal marked, potentially_sensitive
        if depth > 4 or not isinstance(schema, dict):
            return
        if any(kw in field_name.lower() for kw in sensitive_field_patterns):
            potentially_sensitive += 1
            if (
                schema.get("writeOnly")
                or any(m in schema for m in sensitive_markers)
                or schema.get("format") in ("password",)
            ):
                marked += 1
        for fname, fsub in schema.get("properties", {}).items():
            _scan(fsub, fname, depth + 1)

    for schema in spec.get("components", {}).get("schemas", {}).values():
        _scan(schema)

    if potentially_sensitive == 0:
        return 0.8  # 无明显敏感字段时中等得分
    return marked / potentially_sensitive


def _check_security_coverage(spec: dict) -> tuple[float, list[str]]:
    """检查各端点是否有 security 定义（或全局 security）。"""
    global_security = spec.get("security", [])
    has_global = bool(global_security)

    total_ops = 0
    secured_ops = 0
    issues = []

    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, dict):
                continue
            total_ops += 1
            has_local_security = "security" in op
            # 全局 security 覆盖 OR 本地 security 定义（即使是空列表也视为明确声明）
            if has_global or has_local_security:
                secured_ops += 1
            else:
                issues.append(f"{method.upper()} {path}: 无 security 定义")

    if total_ops == 0:
        return 0.5, []

    return secured_ops / total_ops, issues[:3]
