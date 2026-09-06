# -*- coding: utf-8 -*-
"""监控单轮编排：获取 → 标准化（双板块）→ 变化检测 → 持久化 → 通知。

板块：today（今日空投）与 upcoming（空投预告），各自独立基线；
升级到预告监控的首轮只发一次「空投预告当前完整数据」，不当作新增。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .comparator import compare_snapshots
from .fetcher import FetchError
from .messages import (
    build_alert_message,
    build_change_message,
    build_change_sections,
    build_init_message,
    build_recovery_message,
    build_upcoming_init_message,
)
from .normalizer import BJ_TZ, extract_boards

BOARDS = ("today", "upcoming")


@dataclass
class RunResult:
    outcome: str = "no_change"  # init|upcoming_init|changed|deleted_only|no_change|failure
    consecutive_failures: int = 0
    added: int = 0
    modified: int = 0
    removed: int = 0
    message_sent: bool = False
    summary: str = ""


def _run_ts(now: datetime) -> str:
    return now.astimezone(BJ_TZ).strftime("%Y%m%dT%H%M%S%z")


def _record(store, name: str, kind: str, payload: dict, status: str, ts: str):
    store.append_jsonl(
        name,
        {
            "ts": ts,
            "kind": kind,
            "status": status,
            **payload,
        },
    )


def _migrate_state(state: dict) -> dict:
    """兼容旧版（只存 snapshot 今日列表）状态 → 双板块状态。"""
    if isinstance(state.get("snapshot"), list):
        state["boards"] = {
            "today": state["snapshot"] or [],
            "upcoming": [],
        }
        state.pop("snapshot", None)
        if state.get("init_done"):
            # 旧版没有预告基线：下一轮需要发一次预告完整数据
            state["upcoming_init_done"] = False
    elif "boards" not in state or not isinstance(state.get("boards"), dict):
        state["boards"] = {"today": [], "upcoming": []}
    if "upcoming_init_done" not in state:
        state["upcoming_init_done"] = bool(state.get("init_done"))
    return state


def run_once(*, fetcher, store, notifier, now: datetime | None = None) -> RunResult:
    """执行一轮检查，返回结果摘要。参数均依赖注入，便于测试。"""
    now = now or datetime.now(BJ_TZ)
    ts = _run_ts(now)
    state = _migrate_state(store.load_state())

    # ---------- 获取 ----------
    try:
        payload = fetcher.fetch_json()
    except FetchError as exc:
        return _handle_fetch_failure(store, notifier, state, exc, ts)

    # ---------- 成功路径 ----------
    boards = extract_boards(payload, today=now.astimezone(BJ_TZ).date())
    prev_boards = state.get("boards") or {"today": [], "upcoming": []}
    was_init = not state.get("init_done", False)
    was_streak = int(state.get("consecutive_failures") or 0) >= 3

    results: list[dict] = []
    totals = {"added": 0, "modified": 0, "removed": 0}
    today_totals = {"added": 0, "modified": 0, "removed": 0}
    for board in BOARDS:
        result = compare_snapshots(
            prev_boards.get(board) or [], boards.get(board) or []
        )
        result["board"] = board
        results.append(result)
        totals["added"] += result["added_count"]
        totals["modified"] += result["modified_count"]
        totals["removed"] += result["removed_count"]
        if board == "today":
            today_totals["added"] += result["added_count"]
            today_totals["modified"] += result["modified_count"]
            today_totals["removed"] += result["removed_count"]

    upcoming_first = (
        not was_init and state.get("upcoming_init_done") is False
    )
    recovery_note = "⚠️ 已从连续失败状态恢复正常。" if was_streak and not was_init else ""

    # ---------- 通知选择（一次检查最多一条普通消息） ----------
    sent = False
    notify_kind = ""
    change_results = [r for r in results if r["added"] or r["modified"]]
    today_change_results = [
        r for r in results if r["board"] == "today" and (r["added"] or r["modified"])
    ]
    if was_init:
        title, desp = build_init_message(boards)
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        notify_kind = "init"
        _record(
            store,
            "notifications",
            notify_kind,
            {
                "title": title[:80],
                "today": len(boards.get("today") or []),
                "upcoming": len(boards.get("upcoming") or []),
                "channel": getattr(notifier, "kind", "?"),
            },
            "ok" if sent else "skip/fail",
            ts,
        )
    elif upcoming_first:
        extra = build_change_sections(today_change_results)
        title, desp = build_upcoming_init_message(
            boards.get("upcoming") or [], extra_sections=extra, recovery_note=recovery_note
        )
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        notify_kind = "upcoming_init"
        _record(
            store,
            "notifications",
            notify_kind,
            {
                "title": title[:80],
                "upcoming": len(boards.get("upcoming") or []),
                "channel": getattr(notifier, "kind", "?"),
            },
            "ok" if sent else "skip/fail",
            ts,
        )
    elif change_results:
        title, desp = build_change_message(change_results, recovery_note=recovery_note)
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        notify_kind = "change"
        _record(
            store,
            "notifications",
            notify_kind,
            {
                "title": title[:80],
                "added": totals["added"],
                "modified": totals["modified"],
                "channel": getattr(notifier, "kind", "?"),
            },
            "ok" if sent else "skip/fail",
            ts,
        )
    elif recovery_note:
        title, desp = build_recovery_message()
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        notify_kind = "recovery"
        _record(
            store,
            "notifications",
            notify_kind,
            {"title": title[:80], "channel": getattr(notifier, "kind", "?")},
            "ok" if sent else "skip/fail",
            ts,
        )

    # ---------- 持久化基线 ----------
    baseline_changed = was_init or bool(
        totals["added"] or totals["modified"] or totals["removed"]
    )
    failure_state_changed = int(state.get("consecutive_failures") or 0) > 0
    if baseline_changed or failure_state_changed:
        state["boards"] = boards
        state["baseline_ts"] = ts
        state["consecutive_failures"] = 0
        state["failure_notified"] = False
        state["last_error"] = ""
        state["init_done"] = True
        state["upcoming_init_done"] = True
        store.save_state(state)
    if baseline_changed:
        store.write_history_snapshot(ts, boards)
        if not was_init and not upcoming_first:
            for result in results:
                board = result["board"]
                for item in result["added"]:
                    _record(
                        store,
                        "changes",
                        "add",
                        {"board": board, "item": item},
                        "ok",
                        ts,
                    )
                for entry in result["modified"]:
                    _record(
                        store,
                        "changes",
                        "modify",
                        {
                            "board": board,
                            "token": entry["token"],
                            "before": entry["before"],
                            "after": entry["after"],
                            "changes": entry["changes"],
                        },
                        "ok",
                        ts,
                    )
                for item in result["removed"]:
                    _record(
                        store,
                        "changes",
                        "delete",
                        {"board": board, "item": item},
                        "ok",
                        ts,
                    )
        elif upcoming_first:
            # 只记录今日板块的真实变化；预告板块首轮按初始化处理
            for result in results:
                if result["board"] != "today":
                    continue
                for item in result["added"]:
                    _record(
                        store,
                        "changes",
                        "add",
                        {"board": "today", "item": item},
                        "ok",
                        ts,
                    )
                for entry in result["modified"]:
                    _record(
                        store,
                        "changes",
                        "modify",
                        {
                            "board": "today",
                            "token": entry["token"],
                            "before": entry["before"],
                            "after": entry["after"],
                            "changes": entry["changes"],
                        },
                        "ok",
                        ts,
                    )
                for item in result["removed"]:
                    _record(
                        store,
                        "changes",
                        "delete",
                        {"board": "today", "item": item},
                        "ok",
                        ts,
                    )

    # ---------- 运行日志 / 返回 ----------
    if was_init:
        outcome = "init"
        report = {"added": 0, "modified": 0, "removed": 0}
    elif upcoming_first:
        outcome = "upcoming_init"
        # 预告首轮按初始化处理；只报告今日板块的真实变化
        report = today_totals
    elif totals["added"] or totals["modified"]:
        outcome = "changed"
        report = totals
    elif totals["removed"]:
        outcome = "deleted_only"
        report = totals
    else:
        outcome = "no_change"
        report = totals
    store.append_run(
        {
            "ts": ts,
            "outcome": outcome,
            "added": report["added"],
            "modified": report["modified"],
            "removed": report["removed"],
            "consecutive_failures": 0,
        }
    )
    summary = (
        f"{outcome}: +{report['added']} ~{report['modified']} "
        f"-{report['removed']}"
    )
    if was_init:
        summary = (
            f"init: baseline today={len(boards.get('today') or [])} "
            f"upcoming={len(boards.get('upcoming') or [])}"
        )
    return RunResult(
        outcome=outcome,
        added=report["added"],
        modified=report["modified"],
        removed=report["removed"],
        message_sent=sent,
        summary=summary,
    )


def _handle_fetch_failure(store, notifier, state, exc: FetchError, ts: str):
    """失败语义：不更新基线、不删除判断、不普通通知；连续 3 次提醒一次。"""
    failures = int(state.get("consecutive_failures") or 0) + 1
    state["consecutive_failures"] = failures
    state["last_error"] = str(exc)[:500]
    store.save_state(state)
    store.append_run(
        {
            "ts": ts,
            "outcome": "failure",
            "added": 0,
            "modified": 0,
            "removed": 0,
            "consecutive_failures": failures,
            "error": str(exc)[:300],
        }
    )
    sent = False
    if failures >= 3 and not state.get("failure_notified"):
        title, desp = build_alert_message(failures, str(exc))
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        state["failure_notified"] = True
        store.save_state(state)
        _record(
            store,
            "notifications",
            "alert",
            {
                "title": title[:80],
                "failures": failures,
                "channel": getattr(notifier, "kind", "?"),
            },
            "ok" if sent else "skip/fail",
            ts,
        )
    return RunResult(
        outcome="failure",
        consecutive_failures=failures,
        message_sent=sent,
        summary=f"failure x{failures}",
    )
