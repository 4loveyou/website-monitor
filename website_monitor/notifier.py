# -*- coding: utf-8 -*-
"""可替换通知 Provider。

V1 实现 Server酱：SendKey 以 sctp 开头 → Server酱³(SC3)，否则 Server酱 Turbo。
接口保持 send(title, desp) -> SendResult，未来可替换为其他渠道而不改监控核心。
Secret 只从环境变量注入（本地经 sm run，云端经 GitHub Actions Secrets），
禁止写入代码/配置/日志。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from urllib.error import HTTPError, URLError


class SendResult:
    def __init__(self, ok: bool, code: str, message: str):
        self.ok = ok
        self.code = code
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover
        return f"SendResult(ok={self.ok}, code={self.code})"


class Notifier:
    """通知接口（抽象基类）。"""

    kind = "base"

    def send(self, title: str, desp: str) -> SendResult:  # pragma: no cover
        raise NotImplementedError


class ServerChanNotifier(Notifier):
    kind = "serverchan"

    SC3_RE = re.compile(r"^sctp(\d+)t")

    def __init__(self, sendkey: str, timeout: float = 15.0):
        if not sendkey or not isinstance(sendkey, str):
            raise ValueError("SendKey 不能为空")
        self.sendkey = sendkey
        self.timeout = timeout
        sc3 = self.SC3_RE.match(sendkey)
        if sc3:
            uid = sc3.group(1)
            self._url = f"https://{uid}.push.ft07.com/send/{sendkey}.send"
            self.channel = "serverchan3"
        else:
            self._url = f"https://sctapi.ftqq.com/{sendkey}.send"
            self.channel = "serverchan-turbo"

    def send(self, title: str, desp: str) -> SendResult:
        body = json.dumps(
            {"title": title, "desp": desp}, ensure_ascii=False
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json;charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            code = data.get("code", -1)
            ok = str(code) in ("0",)
            return SendResult(
                ok=ok,
                code=str(code),
                message=str(data.get("message") or data.get("errmsg") or ""),
            )
        except HTTPError as exc:
            return SendResult(False, str(exc.code), "HTTP 错误")
        except (URLError, OSError, ValueError) as exc:
            return SendResult(False, "error", str(exc)[:200])


class LogOnlyNotifier(Notifier):
    """未配置 SendKey 时使用：只记录，不联网（本地开发/测试安全兜底）。"""

    kind = "log-only"

    def send(self, title: str, desp: str) -> SendResult:
        return SendResult(
            False, "dry-run", "未配置 SendKey，本次仅记录，未真实推送"
        )


def build_notifier(env_var: str = "SC_SENDKEY") -> Notifier:
    """从环境变量构建通知器；无 Key 时安全降级为 LogOnly。"""
    key = os.environ.get(env_var, "").strip()
    if not key:
        return LogOnlyNotifier()
    return ServerChanNotifier(key)
