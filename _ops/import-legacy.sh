#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 把 2015–2018 的旧 Hexo 站整站搬进 legacy/，链接改成 /legacy/ 开头，
# 并在每页右下角加一个「回新站」的浮标。
#
#   ./_ops/import-legacy.sh              # 从 GitHub 拉旧站
#   ./_ops/import-legacy.sh <git-url>    # 或者从别的地址/本地目录拉
#
# 跑完记得：node site/build.mjs && git add -A && git commit && git push
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLD_URL="${1:-https://github.com/centzu/centzu.github.io.git}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

say "克隆旧站：$OLD_URL"
if ! git clone --depth 1 "$OLD_URL" "$TMP_DIR/old" 2>/dev/null; then
  echo "✗ 克隆失败。GitHub 直连不通的话，先在能连的机器上 clone，" >&2
  echo "  再把目录传上来，然后跑：./_ops/import-legacy.sh /path/to/old-repo" >&2
  exit 1
fi

say "复制到 legacy/"
rm -rf "$REPO_DIR/legacy"
mkdir -p "$REPO_DIR/legacy"
cp -a "$TMP_DIR/old/." "$REPO_DIR/legacy/"
rm -rf "$REPO_DIR/legacy/.git"

say "改写绝对路径并注入「回新站」浮标"
python3 - "$REPO_DIR/legacy" <<'PYEOF'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
changed = 0

BANNER = (
    '<a id="back-to-new" href="/" '
    'style="position:fixed;right:16px;bottom:16px;z-index:9999;'
    'padding:9px 16px;border-radius:999px;background:#4d6bfe;color:#fff;'
    'font:600 13px/1.4 system-ui,sans-serif;text-decoration:none;'
    'box-shadow:0 4px 0 #2c41d6">← 回新站</a>'
)

for path in root.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in (".html", ".css"):
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    before = text

    if path.suffix.lower() == ".html":
        # href="/x" src="/x" 里没有协议头的，全部挪到 /legacy/x
        text = re.sub(r'(href|src)="/(?!/)', r'\1="/legacy/', text)
        text = re.sub(r"(href|src)='/(?!/)", r"\1='/legacy/", text)
        if "back-to-new" not in text and "</body>" in text:
            text = text.replace("</body>", BANNER + "\n</body>", 1)
    else:
        text = re.sub(r"url\(/(?!/)", "url(/legacy/", text)

    if text != before:
        path.write_text(text, encoding="utf-8")
        changed += 1

print(f"✓ 改写了 {changed} 个文件")
PYEOF

# 旧站根目录本身也要能访问
if [[ -f "$REPO_DIR/legacy/index.html" ]]; then
  say "旧站首页就位：/legacy/"
else
  echo "[!] 没找到 legacy/index.html，旧站可能不是静态产物" >&2
fi

cat <<EOF

────────────────────────────────────────────────────────────
搬完了。接下来：

  node site/build.mjs
  git add -A && git commit -m "chore: 归档 2015–2018 旧站到 /legacy/" && git push

注意：旧站里那些 sinaimg / 站外图片链接还是原样，作者删图就会 404，
它们已经和这次改版无关了。
────────────────────────────────────────────────────────────
EOF
