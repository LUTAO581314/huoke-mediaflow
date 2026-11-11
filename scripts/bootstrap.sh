#!/usr/bin/env bash
# 半自动安装：只装 Mac 侧工具与剪辑引擎，**绝不装任何模型**。
#   bash scripts/bootstrap.sh          # 每步问一句
#   bash scripts/bootstrap.sh --yes    # 全部同意（仍然不会装模型）
# 装完自动跑 check-env.sh。
set -o pipefail
ASSUME=0; [ "${1:-}" = "--yes" ] && ASSUME=1
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DJ="$HOME/mediaflow/djian"
ENGINE_REF="e1b6130"

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
no()   { printf '  \033[31m✗\033[0m %s\n' "$1"; }
skip() { printf '  \033[33m·\033[0m %s\n' "$1"; }

ask() { # ask "要做的事" "命令"
  if [ "$ASSUME" = 1 ]; then echo "  → $2"; eval "$2"; return $?; fi
  printf '  ? %s\n    执行：%s\n    继续？[y/N] ' "$1" "$2"
  read -r a; case "$a" in y|Y) echo "  → $2"; eval "$2";; *) skip "跳过：$1";; esac
}

step "1/6 基础二进制"
if command -v brew >/dev/null 2>&1; then
  for c in ffmpeg yt-dlp node uv; do
    if command -v "$c" >/dev/null 2>&1; then ok "$c 已有"; else ask "装 $c" "brew install $c"; fi
  done
else
  no "没有 Homebrew。先装 brew（https://brew.sh），或手动装 ffmpeg/yt-dlp/node/uv"
fi

step "2/6 D剪 上游 + 两个补丁"
if [ -d "$DJ/.git" ]; then
  ok "上游已存在 $DJ"
  grep -q "bindSessionTo" "$DJ/packages/webui/server/store.mjs" 2>/dev/null \
    && ok "补丁已打" || ask "打 session-binding 补丁" "git -C '$DJ' apply '$REPO/engine/patches/djian-session-binding.patch'"
else
  mkdir -p "$(dirname "$DJ")"
  ask "clone 上游并 checkout $ENGINE_REF" \
    "git clone https://github.com/Loliyer520/DSHL-DeepPack-Jian.git '$DJ' && git -C '$DJ' checkout $ENGINE_REF"
  for p in djian-session-binding.patch djian-desktop-shell.patch; do
    ask "打补丁 $p" "git -C '$DJ' apply '$REPO/engine/patches/$p'"
  done
fi
[ -d "$DJ/node_modules" ] && ok "依赖已装" || ask "装引擎依赖（Remotion，约 300MB）" "cd '$DJ' && npm install"

step "3/6 把 @djian/* link 进 DSH（要手动改一行 JSON）"
if [ -d "$HOME/.dsh/profiles/desktop/node_modules/@djian" ]; then
  ok "已 link：$(ls "$HOME/.dsh/profiles/desktop/node_modules/@djian" | wc -l | tr -d ' ') 个包"
else
  no "还没接入。这一步脚本不代劳（要改 profile 的 package.json）："
  sed -n '/第 3 步 · 把 D剪 装进 DSH/,/重启 DSH/p' "$REPO/docs/安装与复现.md" | head -30
fi

step "4/6 Multiplane（片头卡/参数卡/封面）"
MP="$HOME/mediaflow/tools/multiplane"
if [ -d "$MP/node_modules/multiplane" ]; then ok "已装"; else
  mkdir -p "$MP"
  ask "装 multiplane + Chromium" \
    "cd '$MP' && (test -f package.json || npm init -y) && npm install multiplane@0.3.13 --legacy-peer-deps && npx playwright install chromium"
fi

step "5/6 crv（拆片看图，可选）"
if [ -x "$HOME/mediaflow/tools/crv/bin/crv" ]; then ok "已装"; else
  ask "装 crv（独立 venv，约 200MB）" \
    "cd '$HOME/mediaflow' && (test -d .venv || uv venv --python 3.12 .venv) && uv pip install --python '$HOME/mediaflow/.venv/bin/python' 'claude-real-video[whisper]'"
fi

step "6/6 mf 与规则"
[ -f "$HOME/获客平台/知识库/剪辑规范.md" ] && ok "规则已就位" || ask "拷入规则文件" "mkdir -p '$HOME/获客平台/知识库' && cp '$REPO/docs/剪辑规范.md' '$HOME/获客平台/知识库/剪辑规范.md'"
[ -e "$HOME/mediaflow/mf.py" ] && ok "mf.py 软链已就位" || ask "软链 mf.py" "ln -sf '$REPO/mf.py' '$HOME/mediaflow/mf.py'"
if command -v mf >/dev/null 2>&1; then ok "mf 在 PATH"; else
  ask "写 ~/.local/bin/mf" "mkdir -p \"\$HOME/.local/bin\" && printf '#!/usr/bin/env bash\\nexec \"\$HOME/mediaflow/.venv/bin/python\" \"\$HOME/mediaflow/mf.py\" \"\$@\"\\n' > \"\$HOME/.local/bin/mf\" && chmod +x \"\$HOME/.local/bin/mf\""
fi

cat <<'NOTE'

──────────────────────────────────────────────────────────────
模型不装、也不在这里下：
  识别(faster-whisper) / 分离(demucs) / 翻译(ollama) / 配音(GPT-SoVITS)
  都在 Windows GPU 从机（C:\mediagpu，ssh l-l）。
  真要用，先问这套环境的主人，不要自行安装或下载权重。
──────────────────────────────────────────────────────────────
NOTE

bash "$REPO/scripts/check-env.sh"
