#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 DSH 的会话日志里抽出「今天」的聊天，做成给日记用的摘要。

  python3 _ops/collect_chat.py                     # 最近 26 小时
  python3 _ops/collect_chat.py --hours 24 --max-chars 5000

日志默认在 ~/.dsh/sessions（可用 DSH_HOME 或 --root 覆盖）。
后端默认写 .jsonl.zstd；本脚本优先调 `zstd -dc`，其次尝试 python 的 zstandard 模块，
都没有就跳过压缩日志（并在 stderr 提示 apt install zstd）。

输出到 stdout，形如：

  今天有 2 位朋友来找我，一共 37 条消息。

  [10:12] 对方: 在吗
  [10:12] 我: 在。

如果今天没人说话，输出「（今天没人来找我）。」
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))  # 固定按北京时间聚合，服务器时区是 UTC 也不会错

# 日记任务自己的 headless 会话也写在这个目录里。整份日志只要出现这些标记，
# 就说明它是日记生成任务，不是聊天——整个跳过，免得「昨天的日记」变成今天的素材。
DIARY_MARKERS = ("【今天发生的事】", "【今天网上的 ACG 新闻】")

# ── 脱敏 ────────────────────────────────────────────────

RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_URL = re.compile(r"https?://\S+")
RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
RE_IDCARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
RE_QQ = re.compile(r"(?<!\d)\d{5,13}(?!\d)")
RE_AT = re.compile(r"@\S+")


def scrub(text: str) -> str:
    text = RE_EMAIL.sub("[邮箱]", text)
    text = RE_URL.sub("[链接]", text)
    text = RE_IDCARD.sub("[号码]", text)
    text = RE_PHONE.sub("[号码]", text)
    text = RE_QQ.sub("[号码]", text)
    text = RE_AT.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── 读日志 ──────────────────────────────────────────────

def read_lines(path: Path) -> list[str]:
    """读一个会话日志，返回逻辑行（自动处理 zstd）。"""
    name = path.name
    if name.endswith(".jsonl.zstd"):
        zstd = shutil.which("zstd")
        if zstd:
            try:
                out = subprocess.run(
                    [zstd, "-dc", str(path)],
                    capture_output=True, check=True, timeout=30,
                ).stdout
                return out.decode("utf-8", "replace").splitlines()
            except (subprocess.SubprocessError, OSError) as exc:
                print(f"[warn] zstd 解压失败 {path}: {exc}", file=sys.stderr)
                return []
        try:
            import zstandard  # type: ignore
        except ImportError:
            print("[warn] 缺少 zstd 命令和 zstandard 模块，跳过压缩日志", file=sys.stderr)
            print("[hint] Ubuntu/Debian: sudo apt install -y zstd", file=sys.stderr)
            return []
        try:
            dctx = zstandard.ZstdDecompressor()
            with open(path, "rb") as fh:
                return dctx.stream_reader(fh).read().decode("utf-8", "replace").splitlines()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] zstandard 解压失败 {path}: {exc}", file=sys.stderr)
            return []

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[warn] 读取失败 {path}: {exc}", file=sys.stderr)
        return []
    return raw.splitlines()


def text_of(content) -> str:
    """从 message.content 里取纯文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def extract_messages(lines: list[str], since_ms: int) -> list[dict]:
    """把 JSONL 行变成 [{time, role, text}]，只保留人类用户和助手说的话。"""
    if any(marker in line for line in lines for marker in DIARY_MARKERS):
        return []  # 这是日记生成任务自己的会话，跳过

    msgs: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = rec.get("type")
        if kind not in ("user/message", "assistant/message"):
            continue

        ts = rec.get("time")
        if isinstance(ts, (int, float)) and ts < since_ms:
            continue

        data = rec.get("data")
        if not isinstance(data, dict):
            continue

        if kind == "user/message":
            source = data.get("source") or {}
            if isinstance(source, dict) and source.get("kind") != "user":
                continue  # 插件注入的上下文、工具结果，不算聊天
            text = text_of(data.get("content"))
            role = "对方"
        else:
            message = data.get("message")
            if not isinstance(message, dict):
                continue
            text = text_of(message.get("content"))
            role = "我"

        text = text.strip()
        if not text or text.startswith("<") or len(text) > 4000:
            continue
        # 一次性 headless 日记任务本身的输入，别让它污染第二天的素材
        if "【今天发生的事】" in text or "【今天网上的 ACG 新闻】" in text:
            continue

        msgs.append({
            "time": ts if isinstance(ts, (int, float)) else 0,
            "role": role,
            "text": text,
        })
    return msgs


# ── 输出 ────────────────────────────────────────────────

def render(msgs: list[dict], max_chars: int) -> str:
    if not msgs:
        return "（今天没人来找我）。"

    # 只留真正有内容的短句，长段落压到 180 字，避免把整篇代码贴进来
    cleaned = []
    for m in msgs:
        text = scrub(m["text"]).replace("\n", " ")
        if not text:
            continue
        if len(text) > 180:
            text = text[:178] + "…"
        cleaned.append({**m, "text": text})

    if not cleaned:
        return "（今天没人来找我）。"

    def fmt(m: dict) -> str:
        when = datetime.fromtimestamp(m["time"] / 1000, TZ).strftime("%H:%M") if m["time"] else "??:??"
        return f"[{when}] {m['role']}: {m['text']}"

    lines = [fmt(m) for m in cleaned]
    budget = max_chars
    # 超出预算时保留「开场几条 + 最近几条」，中间省略
    if sum(len(x) + 1 for x in lines) > budget:
        head, tail = lines[:3], []
        used = sum(len(x) + 1 for x in head)
        for line in reversed(lines[3:]):
            if used + len(line) + 1 > budget:
                break
            tail.append(line)
            used += len(line) + 1
        tail.reverse()
        body = head + ["……（中间省略）"] + tail
    else:
        body = lines

    hours = {m["time"] // 3_600_000 for m in cleaned if m["time"]}
    span = f"，分布在 {len(hours)} 个时段" if hours else ""
    header = f"今天断断续续有 {len(cleaned)} 条消息{span}。"
    return header + "\n\n" + "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=26, help="往回看多少小时（默认 26）")
    ap.add_argument("--max-chars", type=int, default=6000, help="摘要最大字符数")
    ap.add_argument("--root", default="", help="会话日志根目录，默认 $DSH_HOME/sessions")
    args = ap.parse_args()

    if args.root:
        root = Path(args.root).expanduser()
    else:
        home = os.environ.get("DSH_HOME") or str(Path.home() / ".dsh")
        root = Path(home) / "sessions"

    if not root.is_dir():
        print(f"（没找到会话日志目录 {root}，今天就算没人来吧）。")
        return 0

    since_ms = int((time.time() - args.hours * 3600) * 1000)
    files = [
        p for p in root.rglob("session.jsonl*")
        if p.is_file() and p.stat().st_mtime * 1000 >= since_ms
    ]
    files.sort(key=lambda p: p.stat().st_mtime)

    all_msgs: list[dict] = []
    for path in files:
        all_msgs.extend(extract_messages(read_lines(path), since_ms))

    all_msgs.sort(key=lambda m: m["time"])
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(render(all_msgs, args.max_chars))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
