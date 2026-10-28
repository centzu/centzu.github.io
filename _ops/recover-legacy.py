#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 GitHub 的 Git Data API 恢复被 force push 覆盖的旧站。

你 force push 之后，旧站的提交已经不在 master 上了，但 GitHub 还没回收那些对象。
本脚本按「根树 SHA」把整棵旧站目录树重新下载下来，放进 legacy/，
再把绝对链接改成 /legacy/ 开头、塞一个「回新站」浮标——和 import-legacy.sh 效果一样。

  python3 _ops/recover-legacy.py                       # 用内置的旧站 tree SHA
  python3 _ops/recover-legacy.py --token ghp_xxx       # 建议带 token（不带的限流 60 次/小时）
  python3 _ops/recover-legacy.py --limit 5             # 只抓 5 个文件，先试试

token 也可以放环境变量 GITHUB_TOKEN。只需要 public repo 的只读权限；fine-grained token
勾「Public repositories」或这个仓库的 Contents: Read 即可。

跑完记得：node site/build.mjs && git add -A && git commit -m "chore: 恢复旧站到 legacy/"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "centzu/centzu.github.io"
# 旧站 master 的根树（force push 前最后一次提交的 tree）
DEFAULT_TREE = "e9248ca13ef1124baf67535cda828f6bc411e9f7"
API = f"https://api.github.com/repos/{REPO}/git"

BANNER = (
    '<a id="back-to-new" href="/" '
    'style="position:fixed;right:16px;bottom:16px;z-index:9999;'
    'padding:9px 16px;border-radius:999px;background:#4d6bfe;color:#fff;'
    'font:600 13px/1.4 system-ui,sans-serif;text-decoration:none;'
    'box-shadow:0 4px 0 #2c41d6">← 回新站</a>'
)


def get(url: str, token: str | None, raw: bool = False) -> bytes:
    headers = {"User-Agent": "dsh-diary-recover/1.0"}
    headers["Accept"] = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            print(
                "\n[!] 被 GitHub 限流了（未登录 60 次/小时）。\n"
                "    等一小时，或者带一个 PAT 重跑：--token ghp_xxx\n",
                file=sys.stderr,
            )
        raise


def rewrite(root: Path) -> int:
    """把 href="/x" 改成 /legacy/x，并注入回新站浮标。"""
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (".html", ".css"):
            continue
        before = path.read_text(encoding="utf-8", errors="replace")

        if path.suffix.lower() == ".html":
            text = re.sub(r'(href|src)="/(?!/)', r'\1="/legacy/', before)
            text = re.sub(r"(href|src)='/(?!/)", r"\1='/legacy/", text)
            if "back-to-new" not in text and "</body>" in text:
                text = text.replace("</body>", BANNER + "\n</body>", 1)
        else:
            text = re.sub(r"url\(/(?!/)", "url(/legacy/", before)

        if text != before:
            path.write_text(text, encoding="utf-8")
            changed += 1
    return changed


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=DEFAULT_TREE, help="旧站根树 SHA")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub PAT")
    ap.add_argument("--out", default="legacy", help="输出目录")
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 个文件（调试用）")
    args = ap.parse_args()

    token = args.token or None
    out = Path(args.out)

    print(f"→ 读取旧站目录树 {args.tree[:10]}…")
    tree = json.loads(get(f"{API}/trees/{args.tree}?recursive=1", token))
    if tree.get("truncated"):
        print("[!] 目录树太大被截断了，脚本只处理截断前的部分", file=sys.stderr)

    blobs = [e for e in tree.get("tree", []) if e.get("type") == "blob"]
    if args.limit:
        blobs = blobs[: args.limit]
    total = sum(e.get("size", 0) for e in blobs)
    print(f"  共 {len(blobs)} 个文件，约 {total / 1024 / 1024:.1f} MB")

    if out.exists() and any(out.iterdir()):
        print(f"[!] {out}/ 不是空的，先挪走或删掉再跑", file=sys.stderr)
        return 1

    done = 0
    for entry in blobs:
        data = get(f"{API}/blobs/{entry['sha']}", token, raw=True)
        target = out / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(blobs)}")

    print(f"✓ 下载完成：{done} 个文件 → {out}/")

    changed = rewrite(out)
    print(f"✓ 改写了 {changed} 个 HTML/CSS 的链接")

    if not (out / "index.html").exists():
        print("[!] 没看到 legacy/index.html，旧站可能不是静态产物", file=sys.stderr)

    print("\n下一步：node site/build.mjs && git add -A && git commit -m 'chore: 恢复旧站到 legacy/'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
