#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 在 Linux 服务器上安装「每天 23:30 写日记」的 systemd 定时任务
#
#   sudo ./_ops/install.sh                       # 用当前位置的仓库
#   sudo ./_ops/install.sh --user qqbot --time 23:30
#   sudo ./_ops/install.sh --uninstall
#   ./_ops/install.sh --dry-run                  # 只看会做什么，不写系统文件
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME=dsh-diary
UNIT_DIR=/etc/systemd/system

USER_NAME=""
RUN_TIME="23:30"
DRY_RUN=0
UNINSTALL=0
SKIP_TEST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) USER_NAME="$2"; shift 2 ;;
    --time) RUN_TIME="$2"; shift 2 ;;
    --repo) REPO_DIR="$(cd "$2" && pwd)"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --no-test) SKIP_TEST=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

# 没指定用户时：仓库在 /home/<谁>/ 下就用那个用户，否则按 qqbot
if [[ -z "$USER_NAME" ]]; then
  case "$REPO_DIR" in
    /home/*/*) USER_NAME="$(printf '%s' "$REPO_DIR" | cut -d/ -f3)" ;;
    *) USER_NAME=qqbot ;;
  esac
fi

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$DRY_RUN" -eq 1 ]] || [[ "$(id -u)" -eq 0 ]] || die "需要 root：sudo ./_ops/install.sh"

if [[ "$UNINSTALL" -eq 1 ]]; then
  say "卸载定时任务"
  systemctl disable --now "$SERVICE_NAME.timer" 2>/dev/null || true
  rm -f "$UNIT_DIR/$SERVICE_NAME.service" "$UNIT_DIR/$SERVICE_NAME.timer"
  systemctl daemon-reload
  say "已卸载。日记文件、仓库和历史保留着，没动。"
  exit 0
fi

[[ -f "$REPO_DIR/site/build.mjs" ]] || die "$REPO_DIR 不像日记仓库（缺 site/build.mjs）"
id -u "$USER_NAME" >/dev/null 2>&1 || die "用户 $USER_NAME 不存在"

USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
[[ -n "$USER_HOME" ]] || die "拿不到 $USER_NAME 的 home 目录"

say "仓库：$REPO_DIR"
say "运行用户：$USER_NAME（$USER_HOME）"
say "每天：$RUN_TIME"

# ── 依赖检查 ──────────────────────────────────────────────
missing=()
for cmd in node python3 git flock systemctl; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
command -v zstd >/dev/null 2>&1 || warn "没装 zstd：读不了压缩的会话日志，日记会退化成没有聊天素材（sudo apt install -y zstd）"
if [[ ${#missing[@]} -gt 0 ]]; then
  die "缺少命令：${missing[*]}"
fi
say "依赖检查通过（node $(node -v)、python3 $(python3 -V 2>&1 | awk '{print $2}')）"

# ── 权限与可执行位 ────────────────────────────────────────
if [[ "$DRY_RUN" -eq 0 ]]; then
  say "把仓库交给 $USER_NAME 并补上可执行位"
  chown -R "$USER_NAME:$USER_NAME" "$REPO_DIR"
  chmod +x "$REPO_DIR"/_ops/*.sh
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 700 "$USER_HOME/.dsh-diary" "$USER_HOME/.dsh-diary/logs"
fi

# ── 生成 unit ─────────────────────────────────────────────
render() {
  sed -e "s|__USER__|$USER_NAME|g" \
      -e "s|__REPO__|$REPO_DIR|g" \
      -e "s|__HOME__|$USER_HOME|g" \
      -e "s|^OnCalendar=.*|OnCalendar=*-*-* $RUN_TIME:00|" \
      "$1"
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  say "dry-run：下面是会写进 $UNIT_DIR 的内容"
  echo "──── $SERVICE_NAME.service ────"
  render "$REPO_DIR/_ops/dsh-diary.service"
  echo "──── $SERVICE_NAME.timer ────"
  render "$REPO_DIR/_ops/dsh-diary.timer"
  exit 0
fi

say "写 systemd unit"
render "$REPO_DIR/_ops/dsh-diary.service" >"$UNIT_DIR/$SERVICE_NAME.service"
render "$REPO_DIR/_ops/dsh-diary.timer" >"$UNIT_DIR/$SERVICE_NAME.timer"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME.timer"

# ── 冒烟测试（不调模型）──────────────────────────────────
if [[ "$SKIP_TEST" -eq 0 ]]; then
  say "冒烟测试：只收集素材并打印 prompt，不调模型"
  if runuser -u "$USER_NAME" -- env HOME="$USER_HOME" DSH_HOME="$USER_HOME/.dsh" \
        /bin/bash "$REPO_DIR/_ops/diary.sh" --dry-run >/tmp/diary-dryrun.log 2>&1; then
    say "冒烟测试通过，prompt 预览：/tmp/diary-dryrun.log"
    sed -n '1,12p' /tmp/diary-dryrun.log | sed 's/^/    /'
  else
    warn "冒烟测试失败，看 /tmp/diary-dryrun.log"
    tail -20 /tmp/diary-dryrun.log | sed 's/^/    /' || true
  fi
fi

# ── 收尾提示 ─────────────────────────────────────────────
cat <<EOF

────────────────────────────────────────────────────────────
装好了。还差三件事（都要用 $USER_NAME 身份做）：

1) 配 git 推送凭据（GitHub → Settings → Developer settings →
   Fine-grained tokens，只给 centzu/centzu.github.io 的 Contents: Read and write）：

   sudo -u $USER_NAME git -C $REPO_DIR remote set-url origin \\
     https://<你的PAT>@github.com/centzu/centzu.github.io.git
   sudo -u $USER_NAME git -C $REPO_DIR config user.name  "蓝色大肥鱼"
   sudo -u $USER_NAME git -C $REPO_DIR config user.email "fish@centzu.github.io"

2) 手动试跑一次（会真的调模型、真的推送）：

   sudo systemctl start $SERVICE_NAME.service
   sudo journalctl -u $SERVICE_NAME.service -f

3) 确认 GitHub 仓库 Settings → Pages 仍是
   Source: Deploy from a branch / Branch: master / 目录: / (root)

定时器状态：
   systemctl list-timers $SERVICE_NAME.timer
   sudo journalctl -u $SERVICE_NAME.service -n 50 --no-pager
────────────────────────────────────────────────────────────
EOF
