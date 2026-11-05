#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清洗并校验模型输出的日记，再写入 content/diary。

从 diary.sh 里拆出来，方便单测；只用标准库，低配机器也能跑。

  python3 _ops/clean_diary.py --raw /tmp/raw --entry content/diary/2026-11-06.md \
      --date 2026-11-06 --source life --log /tmp/log --fest /tmp/fest.json
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

FM = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
# 公开日记里不该出现的聊天痕迹（比 life.py 窄一些，避免误伤“有人拿它复刻”这种新闻句）
LEAK_CHAT = re.compile(
    r"(有人(来)?(问|找|让|聊)|人家(问|说|嫌|又)|来问|来找我|对方(说|问)|"
    r"他(说|问)[，,：:「“]|她(说|问)[，,：:「“]|我(说|答)[，,：:「“]|"
    r"主人(问|说)|问我|报完|答完)"
)
PRIVATE_WORDS = (
    "房贷", "贷款", "月供", "首付", "公积金", "工资", "薪水", "年终奖",
    "借钱", "欠款", "彩礼", "房租", "身份证", "银行卡", "密码",
)
CLICHES = ("晚饭扒两碗", "碗洗了", "一天就这么过去", "明天再说", "今天没人来")


def log_line(log_path: str, text: str) -> None:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text.rstrip("\n") + "\n")


def fail(log_path: str, reason: str) -> None:
    log_line(log_path, "[!] 输出不合格：" + reason)
    print("! 输出不合格：" + reason, file=sys.stderr)
    sys.exit(3)


def recent_bodies(folder: Path, target: str, limit: int = 7) -> list[str]:
    bodies: list[str] = []
    for path in sorted(folder.glob("*.md")):
        if path.stem >= target:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FM.match(raw)
        if m:
            body = m.group(2).strip()
            if body:
                bodies.append(body)
    return bodies[-limit:]


def make_summary(body: str) -> str:
    first = re.split(r"[。！？\n]", body)[0].strip()
    first = re.sub(r"^[「『（(【\s]+", "", first)
    if len(first) <= 20:
        return first
    # 太长就按逗号切成短句，尽量在完整的分句处收住
    out = ""
    for part in re.split(r"[，,；;]", first):
        part = part.strip()
        if not part:
            continue
        candidate = (out + "，" + part) if out else part
        if len(candidate) > 20:
            break
        out = candidate
    return out or first[:20].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--fest", default="")
    ap.add_argument("--dir", default="content/diary")
    args = ap.parse_args()

    raw = Path(args.raw).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip()

    # 去掉模型偶尔加的代码块围栏和开场白
    raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
    raw = re.sub(r"\n```$", "", raw).strip()
    if not raw.startswith("---"):
        idx = raw.find("\n---")
        if idx != -1:
            raw = raw[idx + 1:]

    m = FM.match(raw)
    if not m:
        fail(args.log, "没有找到 --- front-matter ---")

    head, body = m.group(1), m.group(2).strip()

    # 模型偶尔会把整篇输出两遍：只留第一份
    second = re.search(r"\n---\s*\ndate:\s*", body)
    if second:
        body = body[: second.start()].rstrip()
        log_line(args.log, "[!] 检测到重复输出，已截断到第一份")

    fields: dict[str, str] = {}
    for line in head.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

    if not fields.get("date"):
        fail(args.log, "front-matter 缺 date")

    fields["date"] = args.date
    fields["source"] = args.source

    if args.fest:
        try:
            fest = json.load(open(args.fest, encoding="utf-8"))
        except (OSError, ValueError):
            fest = {}
        if fest.get("name"):
            fields["festival"] = fest["name"]
        else:
            fields.pop("festival", None)

    body = re.sub(r"^(正文|日记|正文：)[:：]?\s*", "", body).strip()

    # 公开日记不写聊天内容：疑似聊天段落直接删掉，宁可少一段
    kept = []
    for para in body.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if LEAK_CHAT.search(para):
            log_line(args.log, "[!] 删掉疑似聊天段落：" + para[:30])
            continue
        kept.append(para)
    body = "\n\n".join(kept)

    body_chars = len(re.sub(r"\s", "", body))
    if body_chars < 300:
        fail(args.log, "正文太短（%d 字）" % body_chars)
    if body_chars > 1600:
        body = body[:1600].rstrip()

    # 发布前自检：公开正文里不该有联系方式或私事细节
    leaks = []
    if re.search(r"\d{6,}", body):
        leaks.append("6 位以上数字")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", body):
        leaks.append("邮箱")
    if re.search(r"@\S+", body):
        leaks.append("@昵称")
    if re.search(r"https?://", body):
        leaks.append("链接")
    if leaks:
        fail(args.log, "正文里出现" + "、".join(leaks) + "，可能泄露隐私，不发布")

    probe = body + "\n" + " ".join(str(fields.get(k, "")) for k in ("summary", "tags"))
    hit = [w for w in PRIVATE_WORDS if w in probe]
    if hit:
        fail(args.log, "正文/摘要写到私事细节（" + "、".join(hit) + "），不发布")

    summary = fields.get("summary", "").strip()
    if (not summary) or len(summary) > 20 or summary.endswith("都") or LEAK_CHAT.search(summary):
        fields["summary"] = make_summary(body)
    if not fields.get("mood"):
        fields["mood"] = "平静"
    if "tags" not in fields:
        fields["tags"] = "[日常]"

    # 和最近几篇太像就记一笔（不拦发布，方便回头调 prompt）
    try:
        target = args.date
        old = recent_bodies(Path(args.dir), target)
        if old:
            ratio = max(difflib.SequenceMatcher(None, body, x).ratio() for x in old)
            if ratio > 0.62:
                log_line(args.log, "[!] 和最近某篇相似度 %.2f，偏模板" % ratio)
    except Exception:  # noqa: BLE001
        pass

    for phrase in CLICHES:
        if phrase in body:
            log_line(args.log, "[!] 出现旧口头禅：" + phrase)
            break

    order = ["date", "mood", "weather", "rice", "tags", "summary", "festival", "source"]
    out_head = "\n".join("%s: %s" % (k, fields[k]) for k in order if k in fields)
    text = "---\n%s\n---\n\n%s\n" % (out_head, body)
    Path(args.entry).write_text(text, encoding="utf-8")
    print("✓ 写入 %s（%d 字）" % (args.entry, body_chars))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
