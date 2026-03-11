"""
维度 7：流量韧性（Traffic Resilience）— 动态探测

检查 API 对 agent 高频/突发流量的处理能力。
依据：APIContext COO 建议；Gravitee 调查 82% 美国公司遇到 agent "失控"
"""

from __future__ import annotations


def evaluate_static(spec: dict) -> dict:
    """静态分析流量韧性相关的 spec 定义。"""
    checks = []
    issues = []
    recommendations = []

    # ── 检查 1：Rate limit 响应头文档 ──
    rate_limit_documented = _check_rate_limit_docs(spec)
    checks.append({
        "id": "rate_limit_documented",
        "name": "Rate limit 文档化",
        "weight": "high",
        "score": rate_limit_documented,
        "detail": "检查响应 headers 中是否定义 X-RateLimit-* 相关头",
        "source": "static",
    })
    if rate_limit_documented < 0.5:
        recommendations.append("在响应 headers 中定义 X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset")

    # ── 检查 2：429 响应定义 ──
    has_429 = _check_429_defined(spec)
    checks.append({
        "id": "has_429_response",
        "name": "429 限流响应定义",
        "weight": "high",
        "score": 1.0 if has_429 else 0.0,
        "detail": "429 Too Many Requests 响应已定义" if has_429 else "未定义 429 响应",
        "source": "static",
    })
    if not has_429:
        issues.append("未在 spec 中定义 429 响应，agent 无法预期限流行为")
        recommendations.append("为高频调用端点定义 429 响应，并在 body 中包含 retry_after 字段")

    # ── 检查 3：Retry-After 头 ──
    has_retry_after = _check_retry_after(spec)
    checks.append({
        "id": "retry_after_header",
        "name": "Retry-After 头定义",
        "weight": "high",
        "score": 1.0 if has_retry_after else 0.0,
        "detail": "Retry-After 头已定义" if has_retry_after else "未定义 Retry-After 头",
        "source": "static",
    })
    if not has_retry_after:
        recommendations.append("在 429 响应中添加 Retry-After 秒数，帮助 agent 实现指数退避")

    # ── 综合评分 ──
    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "流量韧性",
        "id": "traffic_resilience",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def evaluate_dynamic(probe_results: dict) -> dict:
    """融合动态探测的流量韧性结果。"""
    checks = []
    issues = []
    recommendations = []

    # 基线测试（1 QPS）
    baseline = probe_results.get("baseline", {})
    baseline_success_rate = baseline.get("success_rate", 1.0)
    checks.append({
        "id": "baseline_success",
        "name": "基线请求成功率（1 QPS）",
        "weight": "high",
        "score": baseline_success_rate,
        "detail": f"基线成功率 {baseline_success_rate:.0%}",
        "source": "dynamic",
    })

    # 突发测试（10 QPS）
    burst = probe_results.get("burst", {})
    burst_success_rate = burst.get("success_rate", 1.0)
    checks.append({
        "id": "burst_success",
        "name": "突发请求成功率（10 QPS）",
        "weight": "medium",
        "score": burst_success_rate,
        "detail": f"突发成功率 {burst_success_rate:.0%}",
        "source": "dynamic",
    })
    if burst_success_rate < 0.7:
        issues.append(f"突发流量成功率 {burst_success_rate:.0%}，agent 正常节奏就触发限流")

    # 429 响应头检查
    got_429 = probe_results.get("got_429", False)
    retry_after_present = probe_results.get("retry_after_present", False)
    checks.append({
        "id": "rate_limit_headers_present",
        "name": "限流响应头存在",
        "weight": "high",
        "score": 1.0 if retry_after_present else (0.5 if got_429 else 0.0),
        "detail": (
            f"触发 429，Retry-After {'存在' if retry_after_present else '缺失'}"
            if got_429 else "未触发限流"
        ),
        "source": "dynamic",
    })

    weights = {"high": 3, "medium": 2, "low": 1}
    total_w = sum(weights[c["weight"]] for c in checks)
    score = sum(c["score"] * weights[c["weight"]] for c in checks) / total_w

    return {
        "name": "流量韧性（动态）",
        "id": "traffic_resilience_dynamic",
        "score": round(score, 4),
        "checks": checks,
        "issues": issues[:10],
        "recommendations": recommendations,
    }


def _check_rate_limit_docs(spec: dict) -> float:
    rate_limit_keywords = [
        "x-ratelimit", "x-rate-limit", "ratelimit-limit",
        "retry-after", "rate_limit"
    ]
    spec_lower = str(spec).lower()
    hits = sum(1 for kw in rate_limit_keywords if kw in spec_lower)
    return min(hits / 2, 1.0)


def _check_429_defined(spec: dict) -> bool:
    for _, path_item in spec.get("paths", {}).items():
        for _, operation in path_item.items():
            if isinstance(operation, dict):
                if "429" in operation.get("responses", {}):
                    return True
    return False


def _check_retry_after(spec: dict) -> bool:
    spec_lower = str(spec).lower()
    return "retry-after" in spec_lower or "retry_after" in spec_lower
