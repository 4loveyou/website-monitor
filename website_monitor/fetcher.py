# -*- coding: utf-8 -*-
"""Alpha123 数据源获取（纯标准库 HTTP）。

实测结论（2026-09-06）：https://alpha123.uk/api/data?fresh=0 直连返回 403；
携带与网页同源的浏览器请求头（尤其 Referer: /zh/index.html）后可返回 200 JSON。
"""

from __future__ import annotations

import json
import time
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

DEFAULT_API_URL = "https://alpha123.uk/api/data?fresh=0"
PAGE_URL = "https://alpha123.uk/zh/index.html"

# 与网页前端同源的关键请求头（实测：缺 Referer 会被 Cloudflare 403）
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": PAGE_URL,
    "Origin": "https://alpha123.uk",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class FetchError(Exception):
    """Alpha123 获取失败（网络 / HTTP 状态 / JSON / 结构不符）。"""

    def __init__(self, message: str, *, status: int | None = None, reason: str = ""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.reason = reason

    def __str__(self) -> str:
        if self.status:
            return f"{self.message} (http {self.status})"
        return self.message


class Alpha123Fetcher:
    """获取 /api/data JSON。失败抛 FetchError，调用方负责失败语义。"""

    def __init__(
        self,
        url: str = DEFAULT_API_URL,
        *,
        timeout: float = 20.0,
        attempts: int = 2,
        retry_delay: float = 3.0,
        headers: dict[str, str] | None = None,
    ):
        self.url = url
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self.retry_delay = retry_delay
        self.headers = dict(BROWSER_HEADERS)
        if headers:
            self.headers.update(headers)

    def fetch_json(self) -> dict:
        last_error: FetchError | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                return self._request_once()
            except FetchError as exc:
                # 结构/解析类错误重试无意义，立即抛出
                if exc.status is None and not exc.reason:
                    raise
                last_error = exc
            except (HTTPError, URLError, OSError) as exc:
                if isinstance(exc, HTTPError):
                    last_error = FetchError(
                        "Alpha123 请求失败", status=exc.code, reason=str(exc.reason)
                    )
                else:
                    last_error = FetchError("Alpha123 网络错误", reason=str(exc))
            if attempt < self.attempts:
                time.sleep(self.retry_delay)
        assert last_error is not None
        raise last_error

    def _request_once(self) -> dict:
        request = urllib.request.Request(self.url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise FetchError("Alpha123 请求失败", status=exc.code, reason=str(exc.reason)) from exc
        except (URLError, OSError) as exc:
            raise FetchError("Alpha123 网络错误", reason=str(exc)) from exc
        if status != 200:
            raise FetchError("Alpha123 返回非 200", status=status)
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise FetchError("Alpha123 响应不是合法 JSON", reason=str(exc)) from exc
        if not isinstance(data, dict):
            raise FetchError("Alpha123 响应结构异常：不是 JSON 对象")
        if not isinstance(data.get("airdrops"), list):
            raise FetchError("Alpha123 响应结构异常：缺少 airdrops 数组")
        return data


def make_api_url(*, fresh: int = 0) -> str:
    """生成带 fresh 参数的 URL（默认 fresh=0 走上游缓存，对监控足够）。"""
    return "https://alpha123.uk/api/data?" + urlencode({"fresh": fresh})
