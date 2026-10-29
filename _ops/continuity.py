#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把最近几篇日记压成一小段「记忆」，塞进今天的 prompt。

每天都是新的 headless 会话，模型不会记得昨天写了什么；与其复用同一个会话
让上下文越滚越大，不如每次只喂一份有上限、可检查的摘要：

  · 最近 12 篇的日期 / 心情 / 摘要（知道大致脉络）
  · 最近 3 篇的正文（语气、事实、称呼接得上）
  · 最近 21 天里提到「在追 / 在玩 / 打算 / 还没」的句子（方便 call back）

只读已经发布过的日记，不碰聊天原文，也不生成新内容。
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

FM = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)

# 这些词附近的句子，往往是「还在进行中的事」，最适合拿来 call back
THREAD_WORDS = (
    "在追", "在补", "在玩", "在看", "打算", "准备", "还没", "下次", "明天想",
    "最近在", "一直想", "说好", "想学", "想买", "想补", "追到", "玩到", "看到一半",
)


def load_entry(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = FM.match(raw)
    if not m:
        return None
    fields: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    iso = fields.get("date") or path.stem
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        return None
    body = m.group(2).strip()
    if not body:
        return None
    return {
        "date": iso,
        "day": day,
        "mood": fields.get("mood", ""),
        "summary": fields.get("summary", ""),
        "tags": fields.get("tags", ""),
        "body": body,
    }


def split_sentences(body: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", body)
    return [p.strip() for p in parts if 10 <= len(p.strip()) <= 120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="content/diary", help="日记目录")
    ap.add_argument("--date", default="", help="要写的日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--titles", type=int, default=12, help="列多少篇标题")
    ap.add_argument("--full", type=int, default=3, help="带几篇完整正文")
    ap.add_argument("--thread-days", type=int, default=21, help="回溯多少天找待续的事")
    args = ap.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    entries: list[dict] = []
    for path in sorted(Path(args.dir).glob("*.md")):
        entry = load_entry(path)
        if entry and entry["day"] < target:  # 不把今天自己（重写时）算进记忆
            entries.append(entry)

    entries.sort(key=lambda e: e["day"], reverse=True)
    if not entries:
        print("（这是第一篇，还没有旧日记可参考。）")
        return 0

    out: list[str] = ["你最近写过这些日记（日期 · 心情 · 摘要）："]
    for entry in entries[: args.titles]:
        meta = " · ".join(x for x in (entry["date"], entry["mood"], entry["summary"], entry["tags"]) if x)
        out.append(f"- {meta}")
    out.append("")

    out.append("最近几篇正文（语气、事实、称呼都按这个来）：")
    for entry in entries[: args.full]:
        out.append(f"### {entry['date']}")
        out.append(entry["body"][:900])
        out.append("")

    threads: list[str] = []
    for entry in entries:
        if (target - entry["day"]).days > args.thread_days:
            continue
        picked = 0
        for sentence in split_sentences(entry["body"]):
            if any(word in sentence for word in THREAD_WORDS):
                threads.append(f"- {entry['date'][5:]}：{sentence}")
                picked += 1
                if picked >= 2:
                    break
    if threads:
        out.append("之前提过、今天可以自然接着写的事：")
        out.extend(threads[:12])

    print("\n".join(out).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
