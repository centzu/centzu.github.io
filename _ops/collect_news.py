#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓今天的二次元 / 游戏新闻，作为日记素材。

  python3 _ops/collect_news.py                 # 最近 48 小时，最多 10 条
  python3 _ops/collect_news.py --hours 24 --limit 8

数据源（能连上哪个用哪个，全挂就输出一句「没抓到」）：
  · 巴哈姆特 GNN（中文 ACG）
  · 4Gamers（中文游戏）
  · 机核 GCORES（中文游戏 / 文化）
  · Anime News Network（英文动画）
  · Bilibili 番剧时间表（今天更新了哪些番）

刻意过滤政治、时事、地域对立类关键词 —— 这个站是写日记的，不是新闻站。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (X11; Linux x86_64) dsh-diary/1.0 (+https://centzu.github.io)"

RSS_SOURCES = [
    ("巴哈姆特", "https://gnn.gamer.com.tw/rss.xml"),
    ("4Gamers", "https://www.4gamers.com.tw/rss/latest-news"),
    ("机核", "https://www.gcores.com/rss"),
    ("ANN", "https://www.animenewsnetwork.com/all/rss.xml"),
]

# 只拦政治 / 时事 / 地域对立。娱乐八卦、明星绯闻不拦——那是可以拿来吐槽的乐子，
# 只要不站队、不造谣就行。想放宽或收紧，直接改这个列表。
BLOCK_WORDS = [
    "选举", "总统", "首相", "主席", "政府", "议会", "国会", "外交", "制裁", "关税",
    "战争", "军演", "导弹", "核武", "恐袭", "抗议", "骚乱", "辱华",
    "台独", "港独", "六四", "新疆", "西藏", "习近平", "特朗普", "拜登", "普京", "泽连斯基",
]

RE_TAG = re.compile(r"<[^>]+>")
RE_WS = re.compile(r"\s+")


def clean_text(raw: str, limit: int) -> str:
    text = html.unescape(RE_TAG.sub(" ", raw or ""))
    text = RE_WS.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def blocked(text: str) -> bool:
    return any(w in text for w in BLOCK_WORDS)


def fetch(url: str, timeout: float) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[warn] {url} -> {exc}", file=sys.stderr)
        return None


def parse_when(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_feed(name: str, url: str, timeout: float, since: datetime) -> list[dict]:
    raw = fetch(url, timeout)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"[warn] {name} XML 解析失败: {exc}", file=sys.stderr)
        return []

    items = []
    for node in root.iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        link = ""
        for child in node:
            key = local(child.tag)
            if key == "link" and not child.text and child.get("href"):
                link = child.get("href", "")
            elif key == "link" and child.text:
                link = child.text.strip()
            elif key in ("title", "description", "summary", "content", "pubDate", "published", "updated") and child.text:
                fields.setdefault(key, child.text)
        title = clean_text(fields.get("title", ""), 90)
        desc = clean_text(fields.get("description") or fields.get("summary") or fields.get("content") or "", 70)
        when = parse_when(fields.get("pubDate") or fields.get("published") or fields.get("updated") or "")
        if not title:
            continue
        if when and when < since:
            continue
        items.append({"source": name, "title": title, "desc": desc, "link": link, "when": when})
    return items


def bilibili_today(timeout: float) -> list[dict]:
    """B 站番剧放送表：今天更新了哪几部。连不上就算了。"""
    url = "https://api.bilibili.com/pgc/web/timeline?types=1&before=1&after=1"
    raw = fetch(url, timeout)
    if not raw:
        return []
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if data.get("code") not in (0, None):
        return []

    weekday = datetime.now(TZ).isoweekday()  # 1=周一
    titles = []
    for day in data.get("result") or []:
        if day.get("day_of_week") not in (None, weekday):
            continue
        for ep in day.get("episodes") or []:
            title = clean_text(str(ep.get("title") or ""), 40)
            if title:
                titles.append(title)
    if not titles:
        return []
    uniq = list(dict.fromkeys(titles))[:6]
    return [{
        "source": "B站番剧",
        "title": f"今天更新：{'、'.join(uniq)}",
        "desc": f"共 {len(titles)} 集更新" if len(titles) > len(uniq) else "今天更新的番",
        "link": "https://www.bilibili.com/anime/timeline/",
        "when": None,
    }]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=10)
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    items: list[dict] = []

    for name, url in RSS_SOURCES:
        items.extend(read_feed(name, url, args.timeout, since))

    items.extend(bilibili_today(args.timeout))

    # 去重（同标题）、过滤敏感词
    seen = set()
    unique = []
    for it in items:
        key = it["title"]
        if key in seen:
            continue
        if blocked(it["title"] + " " + it["desc"]):
            continue
        seen.add(key)
        unique.append(it)

    unique.sort(key=lambda it: it["when"] or since, reverse=True)
    unique = unique[: args.limit]

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if not unique:
        print("（今天没抓到什么新闻，可能是网又抽了）。")
        return 0

    for it in unique:
        line = f"[{it['source']}] {it['title']}"
        if it["desc"]:
            line += f" —— {it['desc']}"
        if it["link"]:
            line += f" {it['link']}"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
