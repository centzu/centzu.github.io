#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给日记提供「最近写过什么」的最小上下文。

只给日期和心情，不喂旧正文：旧日记里大量是聊天问答，既会把句式模板带回来，
也可能把主人的话题重新写进公开日记。生活事实交给 life_state.json。
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

FM = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="content/diary", help="日记目录")
    ap.add_argument("--date", default="", help="要写的日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--titles", type=int, default=10, help="列多少篇")
    args = ap.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    entries: list[tuple[date, str]] = []
    for path in sorted(Path(args.dir).glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FM.match(raw)
        if not m:
            continue
        head = m.group(1)
        iso = ""
        mood = ""
        for line in head.split("\n"):
            if line.startswith("date:"):
                iso = line.split(":", 1)[1].strip()
            elif line.startswith("mood:"):
                mood = line.split(":", 1)[1].strip()
        if not iso:
            iso = path.stem
        try:
            day = date.fromisoformat(iso)
        except ValueError:
            continue
        if day < target:
            entries.append((day, mood))

    if not entries:
        print("（这是第一篇，还没有旧日记可参考。）")
        return 0

    entries.sort(key=lambda e: e[0], reverse=True)
    lines = ["你最近写过这些日记（只看日期和心情；旧正文不再喂进来，免得重复句式和聊天内容）："]
    for day, mood in entries[: args.titles]:
        lines.append("- " + " · ".join(x for x in (day.isoformat(), mood) if x))

    moods = [m for _, m in entries[:3] if m]
    if moods:
        lines.append("")
        lines.append("最近三天的心情：" + "、".join(moods) + "。今天别再用同一个心情词。")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
