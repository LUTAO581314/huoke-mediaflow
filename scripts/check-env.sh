#!/usr/bin/env bash
# 环境体检：缺什么、版本够不够，一条命令看完。不改任何东西。
set -uo pipefail
ok=0; bad=0; warn=0
pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; ok=$((ok+1)); }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; bad=$((bad+1)); }
soft() { printf '  \033[33m!\033[0m %s\n' "$1"; warn=$((warn+1)); }

need_cmd() { # name, min 提示
  if command -v "$1" >/dev/null 2>&1; then
    local v; v=$("$1" --version 2>&1 | head -1)
    pass "$1 → $v"
  else
    fail "$1 未安装（$2）"
  fi
}

echo "== 基础二进制 =="
need_cmd ffmpeg   "brew install ffmpeg"
need_cmd ffprobe  "brew install ffmpeg"
need_cmd yt-dlp   "brew install yt-dlp"
need_cmd node     "brew install node"
need_cmd npm      "随 node"
need_cmd uv       "brew install uv（可选，crv 用）"

echo "== Node 版本（D剪 要求 >=22.18）=="
if command -v node >/dev/null 2>&1; then
  nv=$(node -p 'process.versions.node' 2>/dev/null || echo 0.0.0)
  major=${nv%%.*}; rest=${nv#*.}; minor=${rest%%.*}
  if [ "$major" -gt 22 ] || { [ "$major" -eq 22 ] && [ "$minor" -ge 18 ]; }; then
    pass "node $nv"
  else
    fail "node $nv 太旧，需要 >=22.18"
  fi
fi

echo "== 目录与规则 =="
for d in "$HOME/mediaflow" "$HOME/媒体库" "$HOME/获客平台/知识库"; do
  [ -d "$d" ] && pass "$d" || fail "$d 不存在"
done
RULES="${MF_RULES:-$HOME/获客平台/知识库/剪辑规范.md}"
if [ -f "$RULES" ]; then
  pass "规则文件 $RULES"
  if grep -q '"lufs"' "$RULES" 2>/dev/null; then pass "§9 机器参数块存在"; else fail "§9 机器参数块缺失（mf 解析不到参数）"; fi
else
  fail "规则文件缺失：$RULES（cp docs/剪辑规范.md 过去）"
fi

echo "== mf =="
if command -v mf >/dev/null 2>&1; then
  pass "mf 在 PATH：$(command -v mf)"
else
  fail "mf 不在 PATH（~/.local/bin/mf 软链脚本）"
fi
[ -e "$HOME/mediaflow/mf.py" ] && pass "~/mediaflow/mf.py" || fail "~/mediaflow/mf.py 缺失（软链到仓库）"

echo "== D剪 引擎（核心，缺了就剪不了）=="
DJ="${DJIAN_API:-http://127.0.0.1:5180}"
if curl -fsS --max-time 3 "$DJ/api/health" >/dev/null 2>&1; then
  pass "引擎在线 $DJ"
else
  fail "引擎不在线 $DJ（mf dj up 起一个；日志 ~/.djian/logs/engine.log）"
fi
if [ -d "$HOME/mediaflow/djian/packages/webui" ]; then
  pass "上游源码 ~/mediaflow/djian"
  if grep -q "bindSessionTo" "$HOME/mediaflow/djian/packages/webui/server/store.mjs" 2>/dev/null; then
    pass "session-binding 补丁已打"
  else
    fail "session-binding 补丁未打（每个新会话会多建空项目）"
  fi
else
  fail "上游源码缺 ~/mediaflow/djian（clone DSHL-DeepPack-Jian，checkout e1b6130）"
fi
if [ -d "$HOME/.dsh/profiles/desktop/node_modules/@djian" ]; then
  cnt=$(ls "$HOME/.dsh/profiles/desktop/node_modules/@djian" 2>/dev/null | wc -l | tr -d ' ')
  [ "$cnt" -ge 6 ] && pass "DSH 已 link @djian（$cnt 个包）" || fail "DSH link 不全（只有 $cnt 个，需要 6 个）"
else
  fail "DSH 未接入 D剪（profile 里没 link @djian/*）"
fi

echo "== Multiplane / crv =="
[ -d "$HOME/mediaflow/tools/multiplane/node_modules/multiplane" ] && pass "multiplane 已装" || fail "multiplane 未装（install 后 npx playwright install chromium）"
[ -d "$HOME/mediaflow/tools/multiplane/node_modules/playwright" ] && pass "playwright 已装" || soft "playwright 未装（渲染要 Chromium）"
[ -x "$HOME/mediaflow/tools/crv/bin/crv" ] && pass "crv 已装" || soft "crv 未装（只影响拆片看图）"

echo "== GPU 从机（可选）=="
if ssh -o BatchMode=yes -o ConnectTimeout=4 l-l "echo ok" >/dev/null 2>&1; then
  pass "ssh l-l 可连"
else
  soft "ssh l-l 连不上（不配也能本机出片，只是识别/配音用不了）"
fi

echo
printf "结果：\033[32m%d 通过\033[0m / \033[31m%d 失败\033[0m / \033[33m%d 提醒\033[0m\n" "$ok" "$bad" "$warn"
[ "$bad" -eq 0 ] && echo "→ 可以开始：mf new <名称> -b 品硕 --platform dy" || echo "→ 先按上面 ✗ 的提示补齐"
exit 0
