#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查当天是不是中国的法定节假日，是的话输出一行 JSON。

  python3 _ops/festival.py                 # 查今天（北京时间）
  python3 _ops/festival.py --date 2026-10-01

数据来自 timor.tech 的免费节假日接口（每天只查一次，结果缓存到
~/.dsh-diary/festivals/，断网时用缓存）。日期本身不写死在仓库里，
所以 2031、2042 年也不用改代码。

输出：
  {"date": "2026-10-01", "name": "国庆节", "kind": "modern",
   "hint": "假期、堵车、人山人海、宅家", "source": "timor.tech"}
  或  {}   （不是节假日 / 查不到）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
API = "https://timor.tech/api/holiday/info/{date}"
UA = "Mozilla/5.0 (X11; Linux x86_64) dsh-diary/1.0"

# 接口给的名字 → 统一叫法（春节假期里每天返回的名字不一样）
CANON = {
    "元旦": "元旦",
    "春节": "春节",
    "除夕": "除夕",
    "初一": "春节",
    "初二": "春节",
    "初三": "春节",
    "初四": "春节",
    "初五": "春节",
    "初六": "春节",
    "初七": "春节",
    "清明节": "清明节",
    "劳动节": "劳动节",
    "端午节": "端午节",
    "中秋节": "中秋节",
    "国庆节": "国庆节",
}

# 写日记时给模型一个「从哪个角度想」的提示，不是必须照抄
HINTS = {
    "元旦": ("modern", "新的一年、跨年、计划"),
    "春节": ("traditional", "回家、年夜饭、被亲戚问工作、鞭炮"),
    "除夕": ("traditional", "守岁、年夜饭、这一年最后一天"),
    "清明节": ("traditional", "扫墓、想念的人、春天"),
    "劳动节": ("modern", "放假、人多、劳动"),
    "端午节": ("traditional", "粽子甜咸、龙舟、艾草"),
    "中秋节": ("traditional", "月饼、月亮、团圆或者一个人"),
    "国庆节": ("modern", "假期、堵车、人山人海、宅家"),
}

CACHE_DIR = Path(os.environ.get("DSH_DIARY_STATE", str(Path.home() / ".dsh-diary"))) / "festivals"


def fetch(target: date) -> dict:
    url = API.format(date=target.isoformat())
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))

    holiday = payload.get("holiday") or {}
    if not holiday.get("holiday"):
        return {}

    raw = str(holiday.get("name") or "").strip()
    name = CANON.get(raw)
    if not name:
        return {}

    kind, hint = HINTS.get(name, ("modern", ""))
    return {
        "date": target.isoformat(),
        "name": name,
        "kind": kind,
        "hint": hint,
        "source": "timor.tech",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD，默认今天（北京时间）")
    args = ap.parse_args()

    target = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    cache = CACHE_DIR / f"{target.isoformat()}.json"

    data: dict = {}
    try:
        data = fetch(target)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[warn] 节假日接口不可用：{exc}", file=sys.stderr)
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}

    if data:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
