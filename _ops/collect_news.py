#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓今天的科技 / AI / 二次元新闻，作为日记素材。

  python3 _ops/collect_news.py                 # 最近 48 小时，最多 10 条
  python3 _ops/collect_news.py --hours 24 --limit 8

数据源（能连上哪个用哪个，全挂就输出一句「没抓到」）：
  · 科技 / AI：IT之家、新浪科技、量子位、雷锋网、极客公园、爱范儿、钛媒体、InfoQ、开源中国
  · 二次元 / 游戏：巴哈姆特 GNN、4Gamers、机核 GCORES、Anime News Network、Bilibili 番剧时间表

排序时国内科技新闻权重更高：源权重 + 国内关键词 + 科技关键词 + 新鲜度。
输出按「科技 / AI」「动画 / 游戏」分组，并保证 ACG 条目不缺席。

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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (X11; Linux x86_64) dsh-diary/1.0 (+https://centzu.github.io)"

# (名字, RSS 地址, 分类, 源权重)
RSS_SOURCES = [
    ("IT之家", "https://www.ithome.com/rss/", "tech", 7),
    ("新浪科技", "https://rss.sina.com.cn/tech/rollnews.xml", "tech", 6),
    ("量子位", "https://www.qbitai.com/feed", "ai", 6),
    ("极客公园", "https://www.geekpark.net/rss", "tech", 5),
    ("爱范儿", "https://www.ifanr.com/feed", "tech", 4),
    ("钛媒体", "https://www.tmtpost.com/rss.xml", "tech", 4),
    ("InfoQ", "https://www.infoq.cn/feed", "tech", 3),
    ("开源中国", "https://www.oschina.net/news/rss", "tech", 3),
    ("巴哈姆特", "https://gnn.gamer.com.tw/rss.xml", "acg", 3),
    ("4Gamers", "https://www.4gamers.com.tw/rss/latest-news", "acg", 3),
    ("机核", "https://www.gcores.com/rss", "acg", 3),
    ("ANN", "https://www.animenewsnetwork.com/all/rss.xml", "acg", 2),
]

# 国内相关：命中越多分越高，最多加三档
DOMESTIC_WORDS = (
    "中国", "国内", "国产", "中文", "华为", "小米", "阿里", "腾讯", "字节", "百度",
    "DeepSeek", "深度求索", "月之暗面", "智谱", "MiniMax", "商汤", "科大讯飞",
    "中芯", "长江存储", "比亚迪", "宁德时代", "大疆", "鸿蒙", "麒麟", "昇腾",
    "寒武纪", "联想", "vivo", "OPPO", "荣耀", "美团", "京东", "拼多多",
    "宇树", "智元", "地平线", "Momenta", "蔚来", "小鹏", "理想", "问界",
)

# 技术相关：有技术含量的话题再抬一手
TECH_WORDS = (
    "AI", "人工智能", "大模型", "模型", "芯片", "半导体", "算力", "GPU", "CPU",
    "机器人", "具身智能", "自动驾驶", "量子", "操作系统", "开源", "算法",
    "数据中心", "云计算", "光刻", "电池", "新能源", "XR", "VR", "AR", "终端",
    "多模态", "推理", "训练", "Agent", "智能体", "手机", "手機", "笔记本", "筆記型",
    "平板", "耳机", "耳機", "眼镜", "眼鏡", "处理器", "處理器", "显卡", "顯卡",
)

# 标题里有这些词，才真的算动画 / 游戏；否则 4Gamers 的手机稿会被塞进 ACG 组
ACG_HINTS = (
    "动画", "動畫", "漫画", "漫畫", "番剧", "新番", "游戏", "遊戲", "主机", "主機",
    "卡牌", "Steam", "Switch", "PS5", "PlayStation", "Xbox", "手办", "聲優", "声优",
    "剧场版", "劇場版", "电竞", "電競", "任天堂", "米哈游", "鹰角", "万代", "集英社",
    "轻小说", "轻改", "动画化", "联动", "聯動", "玩家",
)

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
        desc = clean_text(fields.get("description") or fields.get("summary") or fields.get("content") or "", 110)
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


def _norm(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text).lower()


def _grams(text: str) -> set[str]:
    norm = _norm(text)
    return {norm[i:i + 2] for i in range(len(norm) - 1)}


def near_dup(a: str, b: str) -> bool:
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return False
    return len(ga & gb) / len(ga | gb) >= 0.62


def score(it: dict, now: datetime) -> float:
    """源权重 + 国内关键词 + 技术关键词 + 新鲜度。"""
    text = (it["title"] + " " + it["desc"]).lower()
    value = it["weight"] * 10.0
    value += min(sum(1 for w in DOMESTIC_WORDS if w.lower() in text), 3) * 7
    value += min(sum(1 for w in TECH_WORDS if w.lower() in text), 3) * 3
    if it["when"]:
        age = (now - it["when"]).total_seconds() / 3600
        if age <= 12:
            value += 8
        elif age <= 24:
            value += 6
        elif age <= 36:
            value += 3
    return value


def ranked(items: list[dict], now: datetime) -> list[dict]:
    return sorted(items, key=lambda it: (score(it, now), it["when"] or now), reverse=True)


def take(items: list[dict], count: int, now: datetime, cap: int = 2) -> list[dict]:
    """挑前 count 条；同一个源最多 cap 条，标题几乎一样的重复报道只留一条。"""
    picked: list[dict] = []
    per_source: Counter = Counter()
    for it in ranked(items, now):
        if per_source[it["source"]] >= cap:
            continue
        if any(near_dup(it["title"], x["title"]) for x in picked):
            continue
        picked.append(it)
        per_source[it["source"]] += 1
        if len(picked) >= count:
            break
    if len(picked) < count:
        for it in ranked(items, now):
            if it in picked:
                continue
            picked.append(it)
            if len(picked) >= count:
                break
    return picked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=10)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)

    def load(src: tuple[str, str, str, int]) -> list[dict]:
        name, url, category, weight = src
        got = read_feed(name, url, args.timeout, since)
        for it in got:
            it["category"] = category
            it["weight"] = weight
        return got

    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for batch in pool.map(load, RSS_SOURCES):
            items.extend(batch)

    for it in bilibili_today(args.timeout):
        it["category"] = "acg"
        it["weight"] = 2
        items.append(it)

    # 4Gamers 也会发手机/硬件稿：标题里没有 ACG 关键词、只有消费电子词的，改判科技
    HARDWARE = (
        "手机", "手機", "笔记本", "筆記型", "平板", "耳机", "耳機", "眼镜", "眼鏡",
        "芯片", "晶片", "处理器", "處理器", "显卡", "顯卡", "OPPO", "vivo", "iPhone",
        "三星", "Samsung", "苹果", "華碩", "华硕", "戴尔", "戴爾", "惠普", "微星",
        "联想", "聯想", "上市", "售價", "售价",
    )
    for it in items:
        if it["category"] != "acg":
            continue
        if any(w in it["title"] for w in ACG_HINTS):
            continue
        if any(w in it["title"] for w in HARDWARE):
            it["category"] = "tech"

    # 去重（同标题 + 近似标题）、过滤敏感词
    unique: list[dict] = []
    seen: set[str] = set()
    for it in items:
        key = _norm(it["title"])
        if not key or key in seen:
            continue
        if blocked(it["title"] + " " + it["desc"]):
            continue
        if any(near_dup(it["title"], x["title"]) for x in unique):
            continue
        seen.add(key)
        unique.append(it)

    if not unique:
        print("（今天没抓到什么新闻，可能是网又抽了）。")
        return 0

    # 配额：ACG 最多三条，其余给科技 / AI；凑不满再互相补
    acg = [it for it in unique if it["category"] == "acg"]
    tech = [it for it in unique if it["category"] != "acg"]
    n_acg = min(3, len(acg))
    picked = take(tech, max(0, args.limit - n_acg), now) + take(acg, n_acg, now)
    if len(picked) < args.limit:
        rest = [it for it in ranked(unique, now) if it not in picked]
        picked.extend(rest[: args.limit - len(picked)])

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    for label, group in (
        ("科技 / AI", [it for it in picked if it["category"] != "acg"]),
        ("动画 / 游戏", [it for it in picked if it["category"] == "acg"]),
    ):
        if not group:
            continue
        print(f"【{label}】")
        for it in group:
            line = f"[{it['source']}] {it['title']}"
            if it["desc"]:
                line += f" —— {it['desc']}"
            if it["link"]:
                line += f" {it['link']}"
            print(line)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
