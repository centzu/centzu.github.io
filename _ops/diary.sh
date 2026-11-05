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
WATERMARK_FILE="$STATE_DIR/last-collected"
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
MEMORY_TMP="$(mktemp)"
PROMPT_TMP="$(mktemp)"
RAW_TMP="$(mktemp)"
FEST_TMP="$(mktemp)"
LIFE_TMP="$(mktemp)"
trap 'rm -f "${CHAT_TMP:-}" "${NEWS_TMP:-}" "${MEMORY_TMP:-}" "${PROMPT_TMP:-}" "${RAW_TMP:-}" "${FEST_TMP:-}" "${LIFE_TMP:-}" 2>/dev/null || true' EXIT

# 采集窗口：正常日更从上次成功写日记的时间接着收（水位线），补写某天则按自然日
COLLECT_STARTED_MS="$(date +%s%3N)"
CHAT_ARGS=(--hours 26 --digest)
if [[ -n "$TARGET_DATE" ]]; then
  CHAT_ARGS+=(--date "$TARGET_DATE")
elif [[ "$FORCE" -eq 1 ]]; then
  # 重写今天：按自然日重取整天素材，别只拿水位线之后那几条
  CHAT_ARGS+=(--date "$DATE")
elif [[ -s "$WATERMARK_FILE" ]]; then
  WM="$(cat "$WATERMARK_FILE" 2>/dev/null || true)"
  if [[ "$WM" =~ ^[0-9]+$ ]]; then
    CHAT_ARGS+=(--since-ms "$WM")
  fi
fi

if ! "$PY" _ops/collect_chat.py "${CHAT_ARGS[@]}" >"$CHAT_TMP" 2>>"$LOG"; then
  echo "这段时间没有和主人聊天。" >"$CHAT_TMP"
fi

NEWS_ARGS=(--hours 48 --limit 8)
if [[ -n "$TARGET_DATE" || "$FORCE" -eq 1 ]]; then
  NEWS_ARGS+=(--date "$DATE")
fi
if ! "$PY" _ops/collect_news.py "${NEWS_ARGS[@]}" >"$NEWS_TMP" 2>>"$LOG"; then
  echo "（今天没抓到什么新闻，可能是网又抽了）。" >"$NEWS_TMP"
fi

# 前几天的日记：让今天的语气、事实、在追的剧/游戏接得上，别今天说在追、明天说第一次听说
if ! "$PY" _ops/continuity.py --dir content/diary --date "$DATE" >"$MEMORY_TMP" 2>>"$LOG"; then
  echo "（之前的日记没读出来，这篇就当第一天写）。" >"$MEMORY_TMP"
fi

# 今天是不是节假日：交给服务器联网查（结果会缓存），断了就当作不是
if ! "$PY" _ops/festival.py --date "$DATE" >"$FEST_TMP" 2>>"$LOG"; then
  echo '{}' >"$FEST_TMP"
fi

# 今天的写作主题 + 固定世界 + 兴趣 + 还没做完的小事
if ! "$PY" _ops/life.py --plan --date "$DATE" --dir content/diary >"$LIFE_TMP" 2>>"$LOG"; then
  printf 'THEME: 日常生活\n\n【今天的生活底子】\n（今天没有额外素材，按平常写。）\n' >"$LIFE_TMP"
fi
THEME="$(sed -n 's/^THEME: //p' "$LIFE_TMP" | head -n 1)"
[[ -n "$THEME" ]] || THEME="日常生活"

if grep -q "没有和主人聊天" "$CHAT_TMP"; then
  SOURCE=news
  if grep -q "没抓到什么新闻" "$NEWS_TMP"; then
    SOURCE=quiet
  fi
else
  SOURCE=chat
fi

# ── 2. 拼 prompt ──────────────────────────────────────────
"$PY" - "$DATE" "$WEEKDAY_CN" "$CHAT_TMP" "$NEWS_TMP" "$SOURCE" "$PROMPT_TMP" "$FEST_TMP" "$MEMORY_TMP" "$LIFE_TMP" <<'PYEOF'
import json
import sys

date, weekday, chat_path, news_path, source, out_path, fest_path, memory_path, life_path = sys.argv[1:10]
tpl = open("_ops/prompt.md", encoding="utf-8").read()
chat = open(chat_path, encoding="utf-8").read().strip()
news = open(news_path, encoding="utf-8").read().strip()
memory = open(memory_path, encoding="utf-8").read().strip()
life = "\n".join(
    line for line in open(life_path, encoding="utf-8").read().strip().splitlines()
    if not line.startswith("THEME:")
)
try:
    fest = json.load(open(fest_path, encoding="utf-8"))
except (OSError, ValueError):
    fest = {}

if fest.get("name"):
    festival = (
        "今天是%s。可以写一段你对这个节日的真实感想："
        "从「%s」这类细节里挑你真有感觉的写，想夸就夸、想感谢就感谢，想吐槽也可以。"
        % (fest["name"], fest.get("hint") or "放假、吃食、老规矩")
    )
else:
    festival = "今天不是节日，按平常写就行。"

text = (tpl.replace("{{DATE}}", date)
           .replace("{{WEEKDAY}}", weekday)
           .replace("{{LIFE}}", life)
           .replace("{{CHAT}}", chat)
           .replace("{{NEWS}}", news)
           .replace("{{MEMORY}}", memory)
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
if ! "$PY" _ops/clean_diary.py --raw "$RAW_TMP" --entry "$ENTRY" --date "$DATE" \
      --source "$SOURCE" --log "$LOG" --fest "$FEST_TMP" --dir content/diary; then
  log "✗ 输出不合格，今天先不写（不会推送半成品）"
  exit 1
fi
# 素材已经写进日记了，记下这次采集的起点；补写历史日期不动水位线
if [[ -z "$TARGET_DATE" ]]; then
  "$PY" _ops/life.py --commit --date "$DATE" --theme "$THEME" >>"$LOG" 2>&1 || true
  printf '%s\n' "$COLLECT_STARTED_MS" >"$WATERMARK_FILE"
fi

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
git -c user.name="${GIT_AUTHOR_NAME:-蓝色大肥鱼}" \
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
