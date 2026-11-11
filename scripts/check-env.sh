#!/usr/bin/env bash
# 环境体检：缺什么、版本够不够，一条命令看完。只读，不改任何东西。
#   bash scripts/check-env.sh          # 人看
#   bash scripts/check-env.sh --json   # AI/脚本解析
set -o pipefail
JSON=0; [ "${1:-}" = "--json" ] && JSON=1
ok=0; bad=0; warn=0; ISSUES=(); NEXT=()
pass() { ok=$((ok+1)); [ "$JSON" = 1 ] || printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { bad=$((bad+1)); ISSUES+=("$1"); [ "$JSON" = 1 ] || printf '  \033[31m✗\033[0m %s\n' "$1"; }
soft() { warn=$((warn+1)); [ "$JSON" = 1 ] || printf '  \033[33m!\033[0m %s\n' "$1"; }
sec()  { [ "$JSON" = 1 ] || printf '\n== %s ==\n' "$1"; }

[ "$JSON" = 1 ] || cat <<'BANNER'
┌──────────────────────────────────────────────────────────────────┐
│ 给 AI 助手：先跑完这个脚本，再决定装什么。                        │
│ 不要在本机装 ollama / faster-whisper / GPT-SoVITS / torch / 模型权重 │
│ ——那些是 Windows GPU 从机的事，Mac 上装了也用不上。                 │
│ 步骤见 docs/安装与复现.md，铁律见 AGENTS.md。                     │
└──────────────────────────────────────────────────────────────────┘
BANNER

need_cmd() { if command -v "$1" >/dev/null 2>&1; then pass "$1 → $("$1" --version 2>&1 | head -1)"; else fail "$1 未安装（$2）"; NEXT+=("装 $1：$2"); fi }

sec "基础二进制"
need_cmd ffmpeg  "brew install ffmpeg"
need_cmd ffprobe "brew install ffmpeg"
need_cmd yt-dlp  "brew install yt-dlp"
need_cmd node    "brew install node（需 >=22.18）"
need_cmd npm     "随 node"
need_cmd uv      "brew install uv（只给 crv 用，可选）"

sec "Node 版本（D剪 要求 >=22.18）"
if command -v node >/dev/null 2>&1; then
  nv=$(node -p 'process.versions.node' 2>/dev/null || echo 0.0.0)
  major=${nv%%.*}; rest=${nv#*.}; minor=${rest%%.*}
  if [ "$major" -gt 22 ] || { [ "$major" -eq 22 ] && [ "$minor" -ge 18 ]; }; then pass "node $nv"
  else fail "node $nv 太旧（需要 >=22.18）"; NEXT+=("升 Node 到 22.18+"); fi
fi

sec "目录与规则"
for d in "$HOME/mediaflow" "$HOME/媒体库" "$HOME/获客平台/知识库"; do
  [ -d "$d" ] && pass "$d" || { fail "$d 不存在"; NEXT+=("mkdir -p $d"); }
done
RULES="${MF_RULES:-$HOME/获客平台/知识库/剪辑规范.md}"
if [ -f "$RULES" ]; then
  pass "规则文件 $RULES"
  grep -q '"lufs"' "$RULES" 2>/dev/null && pass "§9 机器参数块存在" || { fail "§9 机器参数块缺失"; NEXT+=("cp docs/剪辑规范.md $RULES"); }
else
  fail "规则文件缺失：$RULES"; NEXT+=("cp docs/剪辑规范.md $RULES")
fi

sec "mf"
command -v mf >/dev/null 2>&1 && pass "mf 在 PATH：$(command -v mf)" || { fail "mf 不在 PATH"; NEXT+=("按 docs/安装与复现.md 第 6 步写 ~/.local/bin/mf"); }
[ -e "$HOME/mediaflow/mf.py" ] && pass "~/mediaflow/mf.py" || { fail "~/mediaflow/mf.py 缺失"; NEXT+=("ln -sf \$HOME/获客平台/仓库/huoke-mediaflow/mf.py \$HOME/mediaflow/mf.py"); }

sec "D剪 引擎（核心；缺了就剪不了）"
DJ="${DJIAN_API:-http://127.0.0.1:5180}"
curl -fsS --max-time 3 "$DJ/api/health" >/dev/null 2>&1 && pass "引擎在线 $DJ" || { fail "引擎不在线 $DJ"; NEXT+=("起引擎：mf dj up（日志 ~/.djian/logs/engine.log）"); }
if [ -d "$HOME/mediaflow/djian/packages/webui" ]; then
  pass "上游源码 ~/mediaflow/djian"
  grep -q "bindSessionTo" "$HOME/mediaflow/djian/packages/webui/server/store.mjs" 2>/dev/null \
    && pass "session-binding 补丁已打" \
    || { fail "session-binding 补丁未打"; NEXT+=("git apply engine/patches/djian-session-binding.patch"); }
else
  fail "上游源码缺 ~/mediaflow/djian"; NEXT+=("git clone DSHL-DeepPack-Jian 到 ~/mediaflow/djian 并 checkout e1b6130")
fi
if [ -d "$HOME/.dsh/profiles/desktop/node_modules/@djian" ]; then
  cnt=$(ls "$HOME/.dsh/profiles/desktop/node_modules/@djian" 2>/dev/null | wc -l | tr -d ' ')
  [ "$cnt" -ge 6 ] && pass "DSH 已 link @djian（$cnt 个）" || { fail "DSH link 不全（$cnt/6）"; NEXT+=("按安装文档第 3 步在 profile package.json 加 6 条 link: 后 npm install"); }
else
  fail "DSH 未接入 D剪"; NEXT+=("按安装文档第 3 步 link @djian/* 进 DSH profile")
fi

sec "Multiplane / crv"
[ -d "$HOME/mediaflow/tools/multiplane/node_modules/multiplane" ] && pass "multiplane 已装" || { fail "multiplane 未装"; NEXT+=("安装文档第 4 步：npm install multiplane@0.3.13 --legacy-peer-deps + npx playwright install chromium"); }
[ -d "$HOME/mediaflow/tools/multiplane/node_modules/playwright" ] && pass "playwright 已装" || soft "playwright 未装（渲染要 Chromium）"
[ -x "$HOME/mediaflow/tools/crv/bin/crv" ] && pass "crv 已装" || soft "crv 未装（只影响拆片看图）"

sec "GPU 从机（可选，Mac 本机不需要）"
if ssh -o BatchMode=yes -o ConnectTimeout=4 l-l "echo ok" >/dev/null 2>&1; then
  pass "ssh l-l 可连"
else
  soft "ssh l-l 连不上（不配也能本机出片；识别/配音才需要）"
fi
for p in ollama whisper gpt-sovits torch; do
  if command -v "$p" >/dev/null 2>&1; then soft "本机装了 $p —— 这些应该只在 Windows GPU 上跑"; fi
done

if [ "$JSON" = 1 ]; then
  printf '{"ok":%d,"fail":%d,"warn":%d,"issues":[' "$ok" "$bad" "$warn"
  first=1; for i in "${ISSUES[@]}"; do [ $first = 1 ] || printf ','; first=0; printf '"%s"' "${i//\"/\\\"}"; done
  printf '],"next":['
  first=1; for n in "${NEXT[@]}"; do [ $first = 1 ] || printf ','; first=0; printf '"%s"' "${n//\"/\\\"}"; done
  printf ']}\n'; exit 0
fi

printf '\n结果：\033[32m%d 通过\033[0m / \033[31m%d 失败\033[0m / \033[33m%d 提醒\033[0m\n' "$ok" "$bad" "$warn"
if [ "$bad" -eq 0 ]; then
  echo "→ 可以开始：mf new <名称> -b 品硕 --platform dy"
else
  echo "→ 按顺序补（别乱装）："
  n=0; for x in "${NEXT[@]}"; do n=$((n+1)); printf '   %d) %s\n' "$n" "$x"; done
  echo "   * 本机不需要装 ollama / faster-whisper / GPT-SoVITS / torch —— 那是 Windows GPU 从机的事"
fi
exit 0
