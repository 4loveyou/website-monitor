# -*- coding: utf-8 -*-
"""Alpha123 数据标准化 + 「今日空投」语义还原。

依据前端 /zh/index.html 内嵌逻辑还原：
1. API 的 date/time 为北京时间（UTC+8，无夏令时）；
2. phase=2（二段空投）事件时间 = 公布时间 + 18 小时；
3. 只有日期没有时间的空投按当天处理（前端以 14:00 北京时间为锚，UTC+8 下日期不变）；
4. 「今日空投」= 事件发生在北京今天；无日期的 ongoing/active/live 项按前端规则纳入。
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone

BJ_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
ONGOING_STATUSES = {"ongoing", "active", "live"}


def today_beijing(now: datetime | None = None) -> date:
    """当前北京时间日期。"""
    if now is None:
        now = datetime.now(BJ_TZ)
    return now.astimezone(BJ_TZ).date()


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_phase(value: object) -> int:
    text = _clean(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _parse_time_hhmm(value: str) -> dtime | None:
    if not value:
        return None
    parts = value.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1][:2])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return dtime(hour, minute)
    except ValueError:
        return None


def event_info(item: dict) -> tuple[str | None, str, str]:
    """返回 (event_date_iso, time_display, phase_marker)。

    - event_date_iso：二段空投按 +18h 后的北京日期；
    - time_display：用于消息展示的“时间”列内容；
    - phase_marker：二段标记文本（含括号），非二段为空串。
    """
    date_str = _clean(item.get("date"))
    time_str = _clean(item.get("time"))
    phase = _parse_phase(item.get("phase"))
    is_phase2 = phase == 2
    marker = "（二段）" if is_phase2 else ""
    if not date_str:
        return None, "", marker
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        return None, "", marker

    hm = _parse_time_hhmm(time_str) if time_str else None
    if hm is not None:
        event_dt = datetime(
            day.year, day.month, day.day, hm.hour, hm.minute, tzinfo=BJ_TZ
        )
        if is_phase2:
            event_dt = event_dt + timedelta(hours=18)
        display = event_dt.strftime("%Y-%m-%d %H:%M") + marker
        return event_dt.date().isoformat(), display, marker
    # 只有日期：按当天处理（前端以 14:00 为锚，北京时区下日期不变）
    return day.isoformat(), f"{date_str} 待公布{marker}", marker


def canonical_item(raw: dict) -> dict | None:
    """把 API 一条 airdrop 转成稳定、可比较的规范记录。"""
    if not isinstance(raw, dict):
        return None
    token = _clean(raw.get("token")) or _clean(raw.get("name"))
    if not token:
        return None
    event_date, time_display, _marker = event_info(raw)
    return {
        "token": token,
        "name": _clean(raw.get("name")),
        "points": _clean(raw.get("points")),
        "amount": _clean(raw.get("amount")),
        "date": _clean(raw.get("date")),
        "time": _clean(raw.get("time")),
        "event_date": event_date or "",
        "time_display": time_display,
        "phase": _parse_phase(raw.get("phase")),
        "status": _clean(raw.get("status")).lower(),
        "type": _clean(raw.get("type")),
    }


def extract_today_snapshot(
    payload: dict, today: date | None = None
) -> list[dict]:
    """从 API payload 还原当前「今日空投」规范列表（含排序）。"""
    today = today or today_beijing()
    result: list[dict] = []
    for raw in payload.get("airdrops") or []:
        item = canonical_item(raw)
        if item is None:
            continue
        if item["date"]:
            if item["event_date"] == today.isoformat():
                result.append(item)
        else:
            # 无日期：仅 ongoing/active/live 按前端规则纳入今日
            if item["status"] in ONGOING_STATUSES:
                result.append(item)
    result.sort(
        key=lambda i: (
            i["event_date"] or "9999-12-31",
            i["token"].lower(),
            i["time"] or "",
        )
    )
    return result
