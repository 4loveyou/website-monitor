# -*- coding: utf-8 -*-
"""命令行入口：python -m website_monitor <command>

命令：
  run          执行一轮监控检查（云端 schedule 每轮调用一次）
  fetch-sample 抓取一次原始数据用于排查（不落状态）
  version      打印版本
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .fetcher import Alpha123Fetcher
from .notifier import LogOnlyNotifier, build_notifier
from .runner import run_once
from .store import FileStore


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="website_monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行一轮监控检查")
    p_run.add_argument(
        "--data-dir",
        default=os.environ.get("MONITOR_DATA_DIR", "05-data/state"),
        help="状态/历史/记录目录（默认 05-data/state 或 $MONITOR_DATA_DIR）",
    )
    p_run.add_argument(
        "--sendkey-env",
        default="SC_SENDKEY",
        help="SendKey 环境变量名（默认 SC_SENDKEY）",
    )
    p_run.add_argument(
        "--url",
        default=None,
        help="覆盖数据源 URL（默认 https://alpha123.uk/api/data?fresh=0）",
    )
    p_run.add_argument(
        "--dry-notify",
        action="store_true",
        help="即使配置了 SendKey 也只记录不真实推送（安全测试用）",
    )

    p_fetch = sub.add_parser("fetch-sample", help="抓取一次原始数据（排查用）")
    p_fetch.add_argument("--out", default=None, help="保存原始 JSON 到文件")

    sub.add_parser("version", help="打印版本")
    return parser.parse_args(argv)


def _cmd_run(args: argparse.Namespace) -> int:
    notifier = build_notifier(args.sendkey_env)
    if args.dry_notify:
        notifier = LogOnlyNotifier()
    fetcher = Alpha123Fetcher(url=args.url) if args.url else Alpha123Fetcher()
    store = FileStore(args.data_dir)
    result = run_once(fetcher=fetcher, store=store, notifier=notifier)
    print(
        json.dumps(
            {
                "outcome": result.outcome,
                "consecutive_failures": result.consecutive_failures,
                "added": result.added,
                "modified": result.modified,
                "removed": result.removed,
                "message_sent": result.message_sent,
                "summary": result.summary,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


def _cmd_fetch_sample(args: argparse.Namespace) -> int:
    data = Alpha123Fetcher().fetch_json()
    count = len(data.get("airdrops") or [])
    print(f"fetch ok: airdrops={count}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        print(f"saved: {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "fetch-sample":
        return _cmd_fetch_sample(args)
    if args.command == "version":
        print(f"website-monitor {__version__}")
        return 0
    return 2
