# -*- coding: utf-8 -*-
"""微信消息排版（手机阅读优先；title <= 32 字符）。"""

from __future__ import annotations

from .comparator import FIELD_LABELS


def _line(item: dict) -> str:
    token = item.get("token") or "?"
    name = item.get("name") or ""
    name_part = f"（{name}）" if name and name != token else ""
    points = item.get("points") or "-"
    amount = item.get("amount") or "-"
    time_display = item.get("time_display") or "-"
    return f"- **{token}**{name_part}｜积分：{points}｜数量：{amount}｜时间：{time_display}"


def build_init_message(snapshot: list[dict]) -> tuple[str, str]:
    count = len(snapshot)
    title = f"Alpha123监控初始化｜今日空投 {count} 项"
    if count:
        body = "Alpha123「今日空投」监控已启动，以下为当前完整数据（北京时间）：\n\n"
        body += "\n".join(_line(item) for item in snapshot)
    else:
        body = "Alpha123「今日空投」监控已启动。当前今日空投为空（暂无数据）。"
    body += "\n\n每小时自动检查：新增/修改将通知；删除仅记录不通知。"
    return title, body


def build_change_message(result: dict, recovery_note: str = "") -> tuple[str, str]:
    added = result["added"]
    modified = result["modified"]
    title = f"Alpha123监控｜新增 {len(added)} 项"
    if modified:
        title += f" / 修改 {len(modified)} 项"
    sections: list[str] = []
    if added:
        sections.append(f"【新增 {len(added)} 项】")
        sections.extend(_line(item) for item in added)
    if modified:
        sections.append(f"【修改 {len(modified)} 项】")
        for entry in modified:
            token = entry["token"]
            name = entry.get("after", {}).get("name") or ""
            head = f"- **{token}**" + (
                f"（{name}）" if name and name != token else ""
            )
            lines = [head]
            for field, (old, new) in entry["changes"].items():
                label = FIELD_LABELS.get(field, field)
                old_disp = old if old else "空"
                new_disp = new if new else "空"
                lines.append(f"  - {label}：{old_disp} → {new_disp}")
            sections.append("\n".join(lines))
    if recovery_note:
        sections.append(recovery_note)
    return title, "\n\n".join(sections)


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
