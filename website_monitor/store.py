# -*- coding: utf-8 -*-
"""文件型状态/历史存储（本地与云端共用）。

云端（GitHub Actions）使用同一代码：把 data_dir 指向仓库内 cloud-state，
工作流仅在 state/changes/history/notifications 发生变化时提交，避免每小时提交。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _default_state() -> dict:
    return {
        "init_done": False,
        "upcoming_init_done": False,
        "consecutive_failures": 0,
        "failure_notified": False,
        "last_error": "",
        "baseline_ts": None,
        "boards": {"today": [], "upcoming": []},
    }


class FileStore:
    def __init__(self, data_dir: str | os.PathLike):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.history_dir = self.dir / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def load_state(self) -> dict:
        path = self.state_path
        if not path.exists():
            return _default_state()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return _default_state()
        base = _default_state()
        if isinstance(data, dict):
            base.update(data)
        return base

    def save_state(self, state: dict) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.state_path)

    def append_jsonl(self, name: str, record: dict) -> None:
        """追加 JSONL 记录（changes / notifications / runs）。"""
        path = self.dir / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_history_snapshot(self, ts: str, snapshot: list[dict]) -> None:
        path = self.history_dir / f"snapshot-{ts}.json"
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def append_run(self, record: dict) -> None:
        """运行日志（本地全量；云端每个周期也会写，但工作流不提交该文件）。"""
        self.append_jsonl("runs", record)
