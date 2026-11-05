#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给日记挑一个当天主题，并提供固定的生活世界。

只用标准库；不建数据库、不额外调模型，1GB 内存的小机器也能跑。

  python3 _ops/life.py --plan --date 2026-11-06
  python3 _ops/life.py --commit --date 2026-11-06 --theme 海洋幻想
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "life_state.json"
FM = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
# 这些开头本身就模板化，不要再喂给模型当参考
BAD_OPENING = re.compile(
    r"^(早上|上午|中午|下午|傍晚|晚上|半夜|凌晨|今天|昨天|醒来|睡到|"
    r"早饭|午饭|晚饭|扒了?两碗|吃完饭|吃完)"
)

# 公开日记里不出现聊天内容：这些句子直接不进入上下文，也不进入日记
RE_CHAT = re.compile(
    r"(有人(来)?(问|找|让|聊)|人家(问|说|嫌|又)|来问|来找我|对方(说|问)|"
    r"他说|她说|我说|对方|"
    r"问我|报完|答完|讲完|问完|没人来)"
)

THEMES = [
    {
        "name": "房间日常",
        "hint": "房间、窗边的光、书桌、抱枕、台灯、收拾东西",
        "ideas": ["把桌子收一收", "窗边的光从早到晚变了个颜色", "在抱枕旁边躺了一会儿"],
    },
    {
        "name": "海洋幻想",
        "hint": "珊瑚、水母、深海图书馆、海面星光",
        "ideas": ["在水母森林里待到忘了时间", "从海里带回一颗会发光的小东西", "想给房间添一盏更暗的灯"],
    },
    {
        "name": "兴趣钻研",
        "hint": "海洋生物、读书、星空，查着查着走神",
        "ideas": ["翻一页海洋科普", "查鲸鱼到底怎么睡觉", "看星星看到走神"],
    },
    {
        "name": "吃的",
        "hint": "白米饭、买菜、水果、做饭、嘴馋",
        "ideas": ["新米煮出来是什么味道", "把剩饭捏成饭团", "水果摊上挑来挑去"],
    },
    {
        "name": "天气季节",
        "hint": "风、雨、冷热、街上的树、天黑得早了",
        "ideas": ["今天的风从哪边来", "窗玻璃上的水汽", "天黑得比上周早了"],
    },
    {
        "name": "手帐与画",
        "hint": "那张画、线条、收尾或搁下、颜料",
        "ideas": ["把那张画收个尾", "越画越像一团雾", "决定先搁着，不逼自己"],
    },
    {
        "name": "新闻感想",
        "hint": "一条科技/AI/游戏新闻，落到自己的生活",
        "ideas": ["一条新闻让我想到自己", "别人一年好几代，我一张画五天", "看完只记住了一个细节"],
    },
    {
        "name": "自我对话",
        "hint": "懒、习惯、想改的一件小事、对自己的新发现",
        "ideas": ["我是不是太容易放弃", "给自己定一个很小的规矩", "承认今天就是不想动"],
    },
    {
        "name": "夜里的念头",
        "hint": "睡前、灯关掉之后、梦、安静",
        "ideas": ["关灯以后脑子反而清醒", "半夜想起一件很小的事", "做一个记得住的梦"],
    },
    {
        "name": "小发现",
        "hint": "一个以前没注意的小东西、小规律",
        "ideas": ["发现米粒泡过水会变胖", "窗台上的灰每天落一层", "水母比想象中更安静"],
    },
]


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("world", {})
    state.setdefault("interests", [])
    state.setdefault("ongoing", [])
    state.setdefault("threads", [])
    state.setdefault("recent_themes", [])
    return state


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def clean_body(body: str) -> str:
    """整段去掉聊天内容，只留下她自己的生活。"""
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    keep = [p for p in paras if not RE_CHAT.search(p)]
    return "\n\n".join(keep)


def entries_before(folder: Path, target: date) -> list[tuple[date, str, str]]:
    found = []
    for path in sorted(folder.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FM.match(raw)
        if not m:
            continue
        head, body = m.group(1), m.group(2).strip()
        iso = ""
        for line in head.split("\n"):
            if line.startswith("date:"):
                iso = line.split(":", 1)[1].strip()
                break
        if not iso:
            iso = path.stem
        try:
            day = date.fromisoformat(iso)
        except ValueError:
            continue
        if day >= target or not body:
            continue
        found.append((day, body, clean_body(body)))
    found.sort(key=lambda x: x[0])
    return found


def choose_theme(state: dict, target: date) -> dict:
    recent = state.get("recent_themes", [])[-4:]
    recent_names = {r.get("theme") for r in recent if r.get("theme")}
    candidates = [t for t in THEMES if t["name"] not in recent_names] or THEMES

    def last_used(theme: dict) -> int:
        days = []
        for item in state.get("recent_themes", []):
            if item.get("theme") != theme["name"]:
                continue
            try:
                days.append((target - date.fromisoformat(item["date"])).days)
            except (ValueError, KeyError):
                continue
        return min(days) if days else 99

    def jitter(theme: dict) -> int:
        raw = (target.isoformat() + theme["name"]).encode("utf-8")
        return int(hashlib.md5(raw).hexdigest()[:2], 16)

    candidates.sort(key=lambda t: (min(last_used(t), 30), jitter(t)), reverse=True)
    return candidates[0]


def first_sentences(folder: Path, target: date, limit: int = 5) -> list[str]:
    out = []
    for _day, body, _life in reversed(entries_before(folder, target)):
        # 只取「整段都没有聊天标记」的第一段，避免把聊天里的回答当成开头
        first = ""
        for para in body.split("\n\n"):
            para = para.strip()
            if not para or RE_CHAT.search(para):
                continue
            first = re.split(r"[。！？\n]", para)[0].strip()
            break
        if first and not BAD_OPENING.match(first):
            out.append(first[:36])
        if len(out) >= limit:
            break
    return out


def build_plan(state: dict, theme: dict, target: date, folder: Path) -> str:
    world = state.get("world", {})
    home = "、".join(world.get("home", [])[:6])
    ocean = "、".join(world.get("ocean", [])[:5])
    interests = "、".join(
        f"{i.get('name')} {i.get('level', 50)}" for i in state.get("interests", []) if i.get("name")
    )
    recent = state.get("recent_themes", [])[-5:]
    names: list[list] = []
    for item in recent:
        name = item.get("theme", "")
        if not name:
            continue
        if names and names[-1][0] == name:
            names[-1][1] += 1
        else:
            names.append([name, 1])
    recent_names = "、".join(f"{n}×{c}" if c > 1 else n for n, c in names) or "还没有"
    days = []
    for item in state.get("recent_themes", []):
        if item.get("theme") != theme["name"]:
            continue
        try:
            days.append((target - date.fromisoformat(item["date"])).days)
        except (ValueError, KeyError):
            continue
    last = f"上次写是 {min(days)} 天前" if days else "以前没写过"

    lines = [
        f"THEME: {theme['name']}",
        "",
        "【今天的生活底子】",
        f"今天的主基调：{theme['name']} —— {theme['hint']}。",
        f"（{last}；最近写过：{recent_names}。）",
        f"固定世界：房间里有{home}；海里有{ocean}。",
        f"长期兴趣：{interests}。",
    ]
    threads = [t for t in state.get("threads", []) if isinstance(t, str) and t.strip()]
    if threads:
        lines.append("之前留下、可以自然接上的小事：")
        lines.extend(f"- {t}" for t in threads[:4])
    openings = first_sentences(folder, target)
    if openings:
        lines.append("最近几篇的开头（今天别再用相似的开头，也别从起床 / 时间写起）：")
        lines.extend(f"- {x}" for x in openings)
    lines.append("今天可以往这些方向想（挑一个，不用全写）：")
    lines.extend(f"- {x}" for x in theme["ideas"])
    return "\n".join(lines).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="要写的日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--dir", default="content/diary", help="日记目录")
    ap.add_argument("--plan", action="store_true", help="输出今天的写作底子（默认）")
    ap.add_argument("--commit", action="store_true", help="写完后把主题记进状态")
    ap.add_argument("--theme", default="", help="配合 --commit，记录今天实际写的主题")
    args = ap.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    folder = Path(args.dir)
    state = load_state()

    if args.commit:
        theme = args.theme.strip() or "日常生活"
        recent = [r for r in state.get("recent_themes", []) if r.get("date") != target.isoformat()]
        recent.append({"date": target.isoformat(), "theme": theme})
        recent.sort(key=lambda r: r.get("date", ""))
        state["recent_themes"] = recent[-21:]
        save_state(state)
        return 0

    theme = choose_theme(state, target)
    print(build_plan(state, theme, target, folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
