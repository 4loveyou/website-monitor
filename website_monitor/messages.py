# -*- coding: utf-8 -*-
"""微信消息排版（手机阅读优先；title <= 32 字符）。

2026-09-06 用户扩展：同时监控「今日空投」与「空投预告」两个板块。
"""

from __future__ import annotations

from .comparator import FIELD_LABELS

BOARD_LABELS = {"today": "今日空投", "upcoming": "空投预告"}


def _line(item: dict) -> str:
    token = item.get("token") or "?"
    name = item.get("name") or ""
    name_part = f"（{name}）" if name and name != token else ""
    points = item.get("points") or "-"
    amount = item.get("amount") or "-"
    time_display = item.get("time_display") or "-"
    return f"- **{token}**{name_part}｜积分：{points}｜数量：{amount}｜时间：{time_display}"


def _lines(items: list[dict]) -> list[str]:
    return [_line(item) for item in items] or ["（暂无）"]


def build_init_message(boards: dict[str, list[dict]]) -> tuple[str, str]:
    today = boards.get("today") or []
    upcoming = boards.get("upcoming") or []
    count_today = len(today)
    count_upcoming = len(upcoming)
    title = f"Alpha123监控初始化｜今日空投 {count_today} 项"
    if count_upcoming:
        title += f"＋预告 {count_upcoming} 项"
    sections = [
        "Alpha123 监控已启动，以下为当前完整数据（北京时间）：",
        "",
        f"【今日空投 {count_today} 项】",
    ]
    sections.extend(_lines(today))
    sections.append("")
    sections.append(f"【空投预告 {count_upcoming} 项】")
    sections.extend(_lines(upcoming))
    sections.append("")
    sections.append("每小时自动检查：新增/修改将通知；删除仅记录不通知。")
    return title, "\n".join(sections)


def build_upcoming_init_message(
    upcoming: list[dict],
    extra_sections: list[str] | None = None,
    recovery_note: str = "",
) -> tuple[str, str]:
    """升级到「空投预告」监控后的首次消息：展示预告完整数据，不当作新增。"""
    count = len(upcoming)
    title = f"Alpha123监控扩展｜空投预告 {count} 项"
    sections = [
        "监控已扩展：除「今日空投」外，现在同时监控「空投预告」。",
        "",
        f"【空投预告（当前完整数据）{count} 项】",
    ]
    sections.extend(_lines(upcoming))
    if extra_sections:
        sections.append("")
        sections.extend(extra_sections)
    if recovery_note:
        sections.append("")
        sections.append(recovery_note)
    return title, "\n".join(sections)


def _change_sections_for_board(board_key: str, result: dict) -> list[str]:
    label = BOARD_LABELS.get(board_key, board_key)
    added = result.get("added") or []
    modified = result.get("modified") or []
    sections: list[str] = []
    if added:
        sections.append(f"【{label}·新增 {len(added)} 项】")
        sections.extend(_line(item) for item in added)
    if modified:
        sections.append(f"【{label}·修改 {len(modified)} 项】")
        for entry in modified:
            token = entry["token"]
            name = entry.get("after", {}).get("name") or ""
            head = f"- **{token}**" + (
                f"（{name}）" if name and name != token else ""
            )
            lines = [head]
            for field, (old, new) in entry["changes"].items():
                field_label = FIELD_LABELS.get(field, field)
                old_disp = old if old else "空"
                new_disp = new if new else "空"
                lines.append(f"  - {field_label}：{old_disp} → {new_disp}")
            sections.append("\n".join(lines))
    return sections


def build_change_message(
    change_results: list[dict], recovery_note: str = ""
) -> tuple[str, str]:
    """多板块变化合并成一条消息。"""
    sections = build_change_sections(change_results)
    if recovery_note:
        sections.append(recovery_note)
    return _change_title(change_results), "\n\n".join(sections)


def build_change_sections(change_results: list[dict]) -> list[str]:
    """把各板块变化转成分节文本（供嵌入升级初始化消息使用）。"""
    sections: list[str] = []
    for result in change_results:
        board_key = result.get("board", "")
        if not (result.get("added") or result.get("modified")):
            continue
        sections.extend(_change_sections_for_board(board_key, result))
    return sections


def _change_title(change_results: list[dict]) -> str:
    added_total = sum(len(r.get("added") or []) for r in change_results)
    modified_total = sum(len(r.get("modified") or []) for r in change_results)
    title = f"Alpha123监控｜新增 {added_total} 项"
    if modified_total:
        title += f" / 修改 {modified_total} 项"
    return title


def build_alert_message(count: int, last_error: str) -> tuple[str, str]:
    title = f"Alpha123监控异常｜连续 {count} 次失败"
    body = (
        f"Alpha123 已连续 {count} 次获取失败。\n\n"
        f"最近错误：{last_error or '未知'}\n\n"
        "系统将在下一周期继续尝试；恢复后会恢复正常监控。"
    )
    return title, body


def build_recovery_message() -> tuple[str, str]:
    return (
        "Alpha123监控已恢复",
        "Alpha123 已恢复正常访问，监控已继续运行。\n\n"
        "中断期间的变化按失败语义处理：未做删除判断、未发送普通变化通知。",
    )
