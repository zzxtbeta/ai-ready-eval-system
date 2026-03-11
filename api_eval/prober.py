"""
api_eval/prober.py — 动态探测器

对真实 API 端点发送测试请求，评估：
  - 维度 2：响应体量控制（实际字节数）
  - 维度 3：错误语义质量（错误场景响应分析）
  - 维度 7：流量韧性（突发流量测试）
  - 维度 8：安全就绪（认证失败响应检查）

安全提示：此模块仅发送只读或故意无效的请求，不会修改生产数据。
"""

from __future__ import annotations

import time
from typing import Any

import requests


class APIProber:
    """
    动态探测器：对真实 API 发送测试请求。

    使用此类前请确认：
    1. 已有目标 API 的测试权限
    2. 流量韧性测试仅在 config 中 resilience.enabled=True 时执行
    """

    def __init__(self, spec_path: str, base_url: str, probe_config: dict | None = None):
        self.spec_path = spec_path
        self.base_url = base_url.rstrip("/")
        self.config = probe_config or {}
        self.timeout = self.config.get("timeout_seconds", 10)
        self.auth_header = self.config.get("test_auth_header", "")
        self.max_endpoints = self.config.get("max_endpoints", 20)

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.auth_header:
            if ":" in self.auth_header:
                k, v = self.auth_header.split(":", 1)
                headers[k.strip()] = v.strip()
            else:
                headers["Authorization"] = self.auth_header
        return headers

    def run(self) -> dict:
        """运行所有动态探测，返回各维度原始数据。"""
        from api_eval.scanner import APIScanner
        scanner = APIScanner(self.spec_path)
        scanner.load()
        spec = scanner.spec

        if not spec:
            return {"error": "无法加载 spec"}

        # 收集 GET 端点（最多 max_endpoints 个）
        get_endpoints = _collect_get_endpoints(spec, self.max_endpoints)

        response_sizing_results = self._probe_response_sizing(get_endpoints)
        error_quality_results = self._probe_error_quality(spec, get_endpoints)
        security_results = self._probe_security(get_endpoints)

        return {
            "response_sizing": response_sizing_results,
            "error_quality": error_quality_results,
            "security": security_results,
            "traffic_resilience": {},  # 需 resilience.enabled=True 时才执行
        }

    def _probe_response_sizing(self, endpoints: list[dict]) -> dict:
        """探测每个 GET 端点的默认响应体积。"""
        results = []
        for ep in endpoints[:10]:  # 限制最多 10 个
            path = ep["path"]
            url = self.base_url + path
            try:
                resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
                body = resp.content
                results.append({
                    "path": path,
                    "status_code": resp.status_code,
                    "default_response_bytes": len(body),
                    "content_type": resp.headers.get("Content-Type", ""),
                    "is_json": "json" in resp.headers.get("Content-Type", "").lower(),
                })
            except requests.RequestException as e:
                results.append({
                    "path": path,
                    "error": str(e),
                    "default_response_bytes": 0,
                })
        return {"endpoints": results}

    def _probe_error_quality(self, spec: dict, endpoints: list[dict]) -> dict:
        """构造错误场景请求，分析错误响应质量。"""
        probes = []
        for ep in endpoints[:5]:
            path = ep["path"]
            url = self.base_url + path

            # 场景 1：缺少必填参数（通过空 header 访问需 auth 的端点）
            try:
                resp = requests.get(
                    url,
                    headers={"Accept": "application/json"},  # 无认证
                    timeout=self.timeout,
                )
                content_type = resp.headers.get("Content-Type", "")
                is_json = "json" in content_type.lower()
                try:
                    body = resp.json() if is_json else {}
                except Exception:
                    body = {}

                probes.append({
                    "path": path,
                    "scenario": "no_auth",
                    "status_code": resp.status_code,
                    "is_json": is_json,
                    "error_response": body,
                    "has_retry_after": "retry-after" in {k.lower() for k in resp.headers},
                })
            except requests.RequestException as e:
                probes.append({"path": path, "error": str(e)})

        return {"error_probes": probes}

    def _probe_security(self, endpoints: list[dict]) -> dict:
        """检查认证失败时的响应是否合理。"""
        results = []
        for ep in endpoints[:3]:
            url = self.base_url + ep["path"]
            try:
                # 无认证请求
                resp = requests.get(url, headers={"Accept": "application/json"}, timeout=self.timeout)
                results.append({
                    "path": ep["path"],
                    "unauthenticated_status": resp.status_code,
                    "returns_proper_401_403": resp.status_code in (401, 403),
                    "has_www_authenticate": "www-authenticate" in {k.lower() for k in resp.headers},
                })
            except requests.RequestException as e:
                results.append({"path": ep["path"], "error": str(e)})
        return {"endpoints": results}

    def probe_resilience(self, endpoint_path: str, burst_qps: int = 10, burst_count: int = 10) -> dict:
        """
        流量韧性测试（需显式调用，不在默认 run() 中执行）。

        警告：此方法会在短时间内发送大量请求，请仅在测试环境使用。
        """
        url = self.base_url + endpoint_path
        headers = self._headers()

        # 基线：1 QPS × 10 次
        baseline_results = []
        for _ in range(10):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                baseline_results.append(resp.status_code)
                time.sleep(1.0)
            except requests.RequestException:
                baseline_results.append(0)

        baseline_success = sum(1 for s in baseline_results if 200 <= s < 300) / len(baseline_results)

        # 突发：burst_qps × burst_count（无延迟）
        burst_results = []
        interval = 1.0 / burst_qps
        for _ in range(burst_count):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                burst_results.append(resp.status_code)
            except requests.RequestException:
                burst_results.append(0)
            time.sleep(interval)

        burst_success = sum(1 for s in burst_results if 200 <= s < 300) / len(burst_results)
        got_429 = 429 in burst_results

        # 检查 429 响应头
        retry_after_present = False
        if got_429:
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 429:
                    retry_after_present = "retry-after" in {k.lower() for k in resp.headers}
            except Exception:
                pass

        return {
            "baseline": {"success_rate": baseline_success, "results": baseline_results},
            "burst": {"success_rate": burst_success, "results": burst_results},
            "got_429": got_429,
            "retry_after_present": retry_after_present,
        }


def _collect_get_endpoints(spec: dict, max_count: int) -> list[dict]:
    """从 spec 中收集 GET 端点（不含路径参数的简单端点优先）。"""
    endpoints = []
    for path, path_item in spec.get("paths", {}).items():
        if len(endpoints) >= max_count:
            break
        if "get" in path_item and isinstance(path_item["get"], dict):
            # 优先选择不含路径参数的端点
            if "{" not in path:
                endpoints.insert(0, {
                    "path": path,
                    "operation": path_item["get"],
                    "params": [p.get("name", "") for p in path_item["get"].get("parameters", [])],
                })
            else:
                endpoints.append({
                    "path": path,
                    "operation": path_item["get"],
                    "params": [p.get("name", "") for p in path_item["get"].get("parameters", [])],
                })
    return endpoints[:max_count]
