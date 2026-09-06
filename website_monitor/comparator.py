# -*- coding: utf-8 -*-
"""快照差异比较：新增 / 修改 / 删除。"""

from __future__ import annotations

from collections import defaultdict

# 参与“修改通知”判断的字段（忽略 created/updated/system 等噪声时间戳）
COMPARE_FIELDS = (
    "name",
    "points",
    "amount",
    "time_display",
    "phase",
    "status",
    "type",
)
FIELD_LABELS = {
    "name": "项目名称",
    "points": "积分",
    "amount": "数量",
    "time_display": "时间",
    "phase": "阶段",
    "status": "状态",
    "type": "类型",
}


def _norm(value: object) -> str:
    return "" if value is None else str(value).strip()


def _index_by_token(snapshot: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in snapshot:
        groups[_norm(item.get("token")).lower()].append(item)
    for values in groups.values():
        values.sort(
            key=lambda i: (
                i.get("event_date") or "9999-12-31",
                i.get("time") or "",
            )
        )
    return dict(groups)


def field_changes(before: dict, after: dict) -> dict[str, tuple[str, str]]:
    changes: dict[str, tuple[str, str]] = {}
    for field in COMPARE_FIELDS:
        old = _norm(before.get(field))
        new = _norm(after.get(field))
        if old != new:
            changes[field] = (old, new)
    return changes


def compare_snapshots(
    previous: list[dict], current: list[dict]
) -> dict:
    """比较两轮规范快照。

    返回：
      added    — 本轮新增 item 列表
      removed  — 上轮存在本轮消失 item 列表（仅记录，不通知）
      modified — [{"token", "before", "after", "changes": {field: (old,new)}}]
    """
    prev_groups = _index_by_token(previous or [])
    curr_groups = _index_by_token(current or [])
    added: list[dict] = []
    removed: list[dict] = []
    modified: list[dict] = []

    for token in sorted(set(prev_groups) | set(curr_groups)):
        prev_items = prev_groups.get(token, [])
        curr_items = curr_groups.get(token, [])
        common = min(len(prev_items), len(curr_items))
        for idx in range(common):
            before = prev_items[idx]
            after = curr_items[idx]
            changes = field_changes(before, after)
            if changes:
                modified.append(
                    {
                        "token": token,
                        "before": before,
                        "after": after,
                        "changes": changes,
                    }
                )
        for item in prev_items[common:]:
            removed.append(item)
        for item in curr_items[common:]:
            added.append(item)

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
    }
