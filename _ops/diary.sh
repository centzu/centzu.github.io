#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 大肥鱼日记 · 每日生成 + 构建 + 推送
#
#   ./_ops/diary.sh                     正常跑（cron / systemd timer 用这个）
#   ./_ops/diary.sh --force             今天已经写过也重写
#   ./_ops/diary.sh --dry-run           只打印 prompt，不调模型、不写文件
#   ./_ops/diary.sh --date 2026-10-30   补写指定日期
#   ./_ops/diary.sh --no-push           写完不推送（本地预览用）
#
# 环境变量：
#   DSH_BIN             dsh 可执行文件（默认 /usr/local/bin/dsh，找不到就退回 PATH）
#   DSH_HOME            DSH 主目录（默认 ~/.dsh）
#   DSH_DIARY_STATE     状态/日志目录（默认 ~/.dsh-diary）
#   DSH_DIARY_TIMEOUT   单次模型调用超时秒数（默认 420）
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

STATE_DIR="${DSH_DIARY_STATE:-$HOME/.dsh-diary}"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"

DSH_BIN="${DSH_BIN:-}"
if [[ -z "$DSH_BIN" ]]; then
  if [[ -x /usr/local/bin/dsh ]]; then
    DSH_BIN=/usr/local/bin/dsh
  elif command -v dsh >/dev/null 2>&1; then
    DSH_BIN="$(command -v dsh)"
  else
    echo "✗ 找不到 dsh，用 DSH_BIN=/path/to/dsh 指定" >&2
    exit 1
  fi
fi

# ── 0. headless 要的 API Key ───────────────────────────────
# dsh 的 headless profile 会显式关掉 credentials 服务（一次性任务只用「启动环境」
# 里的凭证），所以 DEEPSEEK_API_KEY 必须出现在进程环境里。systemd 不继承登录
# shell 的环境变量，这里就从同一个 DSH_HOME 的凭证库（网页 Models 页写的那份）
# 里补一条；已经有环境变量的（cron、手动跑）原样不动。
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  CRED_FILE="${DSH_HOME:-$HOME/.dsh}/.credentials.yaml"
  if [[ -r "$CRED_FILE" ]]; then
    DEEPSEEK_API_KEY="$(sed -n 's/^[[:space:]]*DEEPSEEK_API_KEY:[[:space:]]*//p' "$CRED_FILE" | head -n 1)"
    DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY%\"}"; DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY#\"}"
    DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY%\'}"; DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY#\'}"
    if [[ -n "$DEEPSEEK_API_KEY" ]]; then
      export DEEPSEEK_API_KEY
    fi
  fi
fi

PY="${PYTHON:-python3}"
TIMEOUT="${DSH_DIARY_TIMEOUT:-420}"

FORCE=0
NO_PUSH=0
DRY_RUN=0
TARGET_DATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --no-push) NO_PUSH=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --date) TARGET_DATE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

export TZ=Asia/Shanghai
DATE="${TARGET_DATE:-$(date +%F)}"
case "$(date -d "$DATE" +%u)" in
  1) WEEKDAY_CN=周一 ;; 2) WEEKDAY_CN=周二 ;; 3) WEEKDAY_CN=周三 ;;
  4) WEEKDAY_CN=周四 ;; 5) WEEKDAY_CN=周五 ;; 6) WEEKDAY_CN=周六 ;;
  *) WEEKDAY_CN=周日 ;;
esac

ENTRY="content/diary/$DATE.md"
LOG="$LOG_DIR/diary-$DATE.log"

# 全新 clone 里没有 content/（它不进 git），第一次跑先把目录建出来
mkdir -p "$(dirname "$ENTRY")"

log() {
  local line
  line="[$(date '+%F %T')] $*"
  echo "$line"
  echo "$line" >>"$LOG"
}

if [[ -f "$ENTRY" && "$FORCE" -ne 1 ]]; then
  log "✓ $ENTRY 已经存在，今天写过就不写了（要重写加 --force）"
  exit 0
fi

# 同一时间只跑一个，防止定时任务和手动执行撞车
exec 9>"$STATE_DIR/lock"
if ! flock -n 9; then
  log "✗ 已经有一个日记任务在跑，退出"
  exit 0
fi

log "── 开始写 $DATE 的日记 ──"

# ── 1. 收集素材 ────────────────────────────────────────────
CHAT_TMP="$(mktemp)"
NEWS_TMP="$(mktemp)"
PROMPT_TMP="$(mktemp)"
RAW_TMP="$(mktemp)"
FEST_TMP="$(mktemp)"
trap 'rm -f "${CHAT_TMP:-}" "${NEWS_TMP:-}" "${PROMPT_TMP:-}" "${RAW_TMP:-}" "${FEST_TMP:-}" 2>/dev/null || true' EXIT

if ! "$PY" _ops/collect_chat.py --hours 26 >"$CHAT_TMP" 2>>"$LOG"; then
  echo "（聊天记录没读出来，今天先不写这个）。" >"$CHAT_TMP"
fi

if ! "$PY" _ops/collect_news.py --hours 48 --limit 8 >"$NEWS_TMP" 2>>"$LOG"; then
  echo "（今天没抓到什么新闻，可能是网又抽了）。" >"$NEWS_TMP"
fi

# 今天是不是节假日：交给服务器联网查（结果会缓存），断了就当作不是
if ! "$PY" _ops/festival.py --date "$DATE" >"$FEST_TMP" 2>>"$LOG"; then
  echo '{}' >"$FEST_TMP"
fi

if grep -q "今天没人来找我" "$CHAT_TMP"; then
  SOURCE=acg
  if grep -q "没抓到什么新闻" "$NEWS_TMP"; then
    SOURCE=quiet
  fi
else
  SOURCE=chat
fi

# ── 2. 拼 prompt ──────────────────────────────────────────
"$PY" - "$DATE" "$WEEKDAY_CN" "$CHAT_TMP" "$NEWS_TMP" "$SOURCE" "$PROMPT_TMP" "$FEST_TMP" <<'PYEOF'
import json
import sys

date, weekday, chat_path, news_path, source, out_path, fest_path = sys.argv[1:8]
tpl = open("_ops/prompt.md", encoding="utf-8").read()
chat = open(chat_path, encoding="utf-8").read().strip()
news = open(news_path, encoding="utf-8").read().strip()
try:
    fest = json.load(open(fest_path, encoding="utf-8"))
except (OSError, ValueError):
    fest = {}

if fest.get("name"):
    festival = (
        "今天是%s。可以写一段你对这个节日的真实感想（不是感谢、不是歌颂）："
        "从「%s」这类细节里挑你真有感觉的写，也可以吐槽。"
        % (fest["name"], fest.get("hint") or "放假、吃食、老规矩")
    )
else:
    festival = "今天不是节日，按平常写就行。"

text = (tpl.replace("{{DATE}}", date)
           .replace("{{WEEKDAY}}", weekday)
           .replace("{{CHAT}}", chat)
           .replace("{{NEWS}}", news)
           .replace("{{FESTIVAL}}", festival)
           .replace("{{SOURCE}}", source))
open(out_path, "w", encoding="utf-8").write(text)
PYEOF

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "── dry-run：下面是这次要喂给模型的 prompt ──"
  cat "$PROMPT_TMP"
  exit 0
fi

# ── 3. 调模型 ─────────────────────────────────────────────
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  log "! 环境里和 ${CRED_FILE:-$HOME/.dsh/.credentials.yaml} 里都没有 DEEPSEEK_API_KEY"
  log "! headless 不读交互式凭证库，这样调模型会直接 MISSING_CREDENTIAL"
fi

run_model() {
  local attempt="$1"
  log "→ 第 $attempt 次调用 dsh（headless，超时 ${TIMEOUT}s）"
  if timeout "$TIMEOUT" "$DSH_BIN" --profile headless \
        --patch _ops/persona.yml "$(cat "$PROMPT_TMP")" \
        >"$RAW_TMP" 2>>"$LOG"; then
    return 0
  fi
  log "✗ dsh 返回非零（第 $attempt 次）"
  return 1
}

ok=0
for attempt in 1 2; do
  if run_model "$attempt"; then ok=1; break; fi
  sleep 5
done

if [[ "$ok" -ne 1 ]]; then
  log "✗ 两次都失败了，今天先不写（不会推送半成品）"
  exit 1
fi

# ── 4. 清洗与校验 ─────────────────────────────────────────
"$PY" - "$RAW_TMP" "$ENTRY" "$DATE" "$SOURCE" "$LOG" "$FEST_TMP" <<'PYEOF'
import json
import re
import sys

raw_path, entry_path, date, source, log_path, fest_path = sys.argv[1:7]
raw = open(raw_path, encoding="utf-8").read().replace("\r\n", "\n").strip()

# 去掉模型偶尔加的代码块围栏和开场白
raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
raw = re.sub(r"\n```$", "", raw).strip()
if not raw.startswith("---"):
    idx = raw.find("\n---")
    if idx != -1:
        raw = raw[idx + 1:]


def fail(reason):
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write("[!] 输出不合格：" + reason + "\n")
    print("! 输出不合格：" + reason, file=sys.stderr)
    sys.exit(3)


m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
if not m:
    fail("没有找到 --- front-matter ---")

head, body = m.group(1), m.group(2).strip()
fields = {}
for line in head.split("\n"):
    if ":" in line:
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()

if not fields.get("date"):
    fail("front-matter 缺 date")

fields["date"] = date
fields["source"] = source

try:
    fest = json.load(open(fest_path, encoding="utf-8"))
except (OSError, ValueError):
    fest = {}
if fest.get("name"):
    fields["festival"] = fest["name"]
else:
    fields.pop("festival", None)

body = re.sub(r"^(正文|日记|正文：)[:：]?\s*", "", body).strip()
body_chars = len(re.sub(r"\s", "", body))
if body_chars < 150:
    fail("正文太短（%d 字）" % body_chars)
if body_chars > 2000:
    body = body[:2000]

# 发布前自检：正文是公开的，出现这些就说明脱敏没兜住
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
    fail("正文里出现" + "、".join(leaks) + "，可能泄露隐私，不发布")

if not fields.get("summary"):
    fields["summary"] = body.replace("\n", " ")[:18]
if not fields.get("mood"):
    fields["mood"] = "摸鱼"
if "tags" not in fields:
    fields["tags"] = "[日常]"

order = ["date", "mood", "weather", "rice", "tags", "summary", "festival", "source"]
out_head = "\n".join("%s: %s" % (k, fields[k]) for k in order if k in fields)
text = "---\n%s\n---\n\n%s\n" % (out_head, body)
open(entry_path, "w", encoding="utf-8").write(text)
print("✓ 写入 %s（%d 字）" % (entry_path, body_chars))
PYEOF

# ── 5. 构建 + 推送 ────────────────────────────────────────
if ! node site/build.mjs >>"$LOG" 2>&1; then
  log "✗ 站点构建失败，日记文件先留着，不推送"
  exit 1
fi
log "✓ 站点构建完成"

if [[ "$NO_PUSH" -eq 1 ]]; then
  log "— 指定了 --no-push，不提交也不推送"
  exit 0
fi

if [[ -z "$(git status --porcelain)" ]]; then
  log "— 没有任何改动，跳过提交"
  exit 0
fi

git add -A
git -c user.name="${GIT_AUTHOR_NAME:-大肥鱼}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-fish@centzu.github.io}" \
    commit -q -m "diary: $DATE"
log "✓ 已提交"

if git push -q origin HEAD 2>>"$LOG"; then
  log "✓ 已推送，GitHub Pages 几十秒后更新"
else
  log "! 推送失败，试试 rebase 后再推一次"
  git pull --rebase --autostash -q >>"$LOG" 2>&1 || true
  if git push -q origin HEAD 2>>"$LOG"; then
    log "✓ rebase 后推送成功"
  else
    log "✗ 推送还是失败，看 $LOG"
    exit 1
  fi
fi

log "── $DATE 的日记写完了 ──"
