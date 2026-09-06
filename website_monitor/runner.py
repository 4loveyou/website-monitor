# -*- coding: utf-8 -*-
"""监控单轮编排：获取 → 标准化 → 变化检测 → 持久化 → 通知。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .fetcher import FetchError
from .messages import (
    build_alert_message,
    build_change_message,
    build_init_message,
    build_recovery_message,
)
from .normalizer import BJ_TZ, extract_today_snapshot


@dataclass
class RunResult:
    outcome: str = "no_change"  # init|changed|deleted_only|no_change|failure
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


def run_once(*, fetcher, store, notifier, now: datetime | None = None) -> RunResult:
    """执行一轮检查，返回结果摘要。参数均依赖注入，便于测试。"""
    now = now or datetime.now(BJ_TZ)
    ts = _run_ts(now)
    state = store.load_state()

    # ---------- 获取 ----------
    try:
        payload = fetcher.fetch_json()
    except FetchError as exc:
        return _handle_fetch_failure(store, notifier, state, exc, ts)

    # ---------- 成功路径 ----------
    snapshot = extract_today_snapshot(payload, today=now.astimezone(BJ_TZ).date())
    previous = state.get("snapshot") or []
    was_init = not state.get("init_done", False)
    was_streak = int(state.get("consecutive_failures") or 0) >= 3
    result = compare_snapshots(previous, snapshot)

    recovery_note = "⚠️ 已从连续失败状态恢复正常。" if was_streak and not was_init else ""

    sent = False
    if was_init:
        title, desp = build_init_message(snapshot)
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        _record(
            store,
            "notifications",
            "init",
            {"title": title[:80], "channel": getattr(notifier, "kind", "?")},
            "ok" if sent else "skip/fail",
            ts,
        )
    elif result["added_count"] or result["modified_count"]:
        title, desp = build_change_message(result, recovery_note=recovery_note)
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        _record(
            store,
            "notifications",
            "change",
            {
                "title": title[:80],
                "added": result["added_count"],
                "modified": result["modified_count"],
                "channel": getattr(notifier, "kind", "?"),
            },
            "ok" if sent else "skip/fail",
            ts,
        )
    elif recovery_note:
        title, desp = build_recovery_message()
        send_result = notifier.send(title, desp)
        sent = send_result.ok
        _record(
            store,
            "notifications",
            "recovery",
            {"title": title[:80], "channel": getattr(notifier, "kind", "?")},
            "ok" if sent else "skip/fail",
            ts,
        )

    # ---------- 持久化基线（成功且内容/失败状态有变化时才写） ----------
    baseline_changed = was_init or bool(
        result["added_count"] or result["modified_count"] or result["removed_count"]
    )
    failure_state_changed = int(state.get("consecutive_failures") or 0) > 0
    if baseline_changed or failure_state_changed:
        state["snapshot"] = snapshot
        state["baseline_ts"] = ts
        state["consecutive_failures"] = 0
        state["failure_notified"] = False
        state["last_error"] = ""
        state["init_done"] = True
        store.save_state(state)
    if baseline_changed:
        store.write_history_snapshot(ts, snapshot)
        if not was_init and (
            result["added_count"]
            or result["modified_count"]
            or result["removed_count"]
        ):
            for item in result["added"]:
                _record(store, "changes", "add", {"item": item}, "ok", ts)
            for entry in result["modified"]:
                _record(
                    store,
                    "changes",
                    "modify",
                    {
                        "token": entry["token"],
                        "before": entry["before"],
                        "after": entry["after"],
                        "changes": entry["changes"],
                    },
                    "ok",
                    ts,
                )
            for item in result["removed"]:
                _record(store, "changes", "delete", {"item": item}, "ok", ts)

    # ---------- 运行日志 ----------
    if was_init:
        outcome = "init"
    elif result["added_count"] or result["modified_count"]:
        outcome = "changed"
    elif result["removed_count"]:
        outcome = "deleted_only"
    else:
        outcome = "no_change"
    store.append_run(
        {
            "ts": ts,
            "outcome": outcome,
            "added": result["added_count"],
            "modified": result["modified_count"],
            "removed": result["removed_count"],
            "consecutive_failures": 0,
        }
    )
    if was_init:
        # 初始化建立基线，不把全量数据当作“新增/修改/删除”变化
        return RunResult(
            outcome=outcome,
            message_sent=sent,
            summary=f"init: baseline {len(snapshot)} items",
        )
    return RunResult(
        outcome=outcome,
        added=result["added_count"],
        modified=result["modified_count"],
        removed=result["removed_count"],
        message_sent=sent,
        summary=(
            f"{outcome}: +{result['added_count']} "
            f"~{result['modified_count']} -{result['removed_count']}"
        ),
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


def compare_snapshots(previous, snapshot):
    from .comparator import compare_snapshots as _impl

    return _impl(previous, snapshot)
