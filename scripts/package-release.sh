#!/usr/bin/env bash
# 打发布包：把当前 HEAD 的源码快照打成 tar.gz + 校验和，用于 GitHub Release 资产。
#   bash scripts/package-release.sh 0.1.0
# 约定：**包里绝不含** 上游 D剪 源码、模型权重、素材、密钥、客户数据。
set -euo pipefail
VER="${1:?用法: bash scripts/package-release.sh <版本号，如 0.1.0> [--win]}"
WIN=${2:-}
[ "$WIN" = "--win" ] && WIN=1 || WIN=0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
NAME="huoke-mediaflow-$VER"
mkdir -p "$OUT"
cd "$ROOT"

git archive --format=tar.gz --prefix="$NAME/" -o "$OUT/$NAME.tar.gz" HEAD
# Windows 用户更习惯 zip；两份资产内容相同，只是壳不同
if [ "$WIN" = 1 ]; then
  ( cd "$OUT" && rm -rf _wintmp "$NAME-win.zip" && mkdir _wintmp && \
    tar -xzf "$NAME.tar.gz" -C _wintmp && \
    ( cd _wintmp && zip -qr "../$NAME-win.zip" "$NAME" ) && rm -rf _wintmp )
fi

echo "== 包内容（按顶层目录）=="
tar -tzf "$OUT/$NAME.tar.gz" | sed "s|^$NAME/||" | awk -F/ 'NF>0 && $1!="" {print $1}' | sort -u | tr '\n' ' '; echo

echo "== 违禁内容自检 =="
bad=$(tar -tzf "$OUT/$NAME.tar.gz" | grep -E "(^|/)(node_modules|\.env|.*\.pem|.*\.key|models?/|\.venv)(/|$)" || true)
if [ -n "$bad" ]; then echo "✗ 包里出现不该有的东西："; echo "$bad"; exit 1; fi
echo "✓ 无 node_modules / .env / 密钥 / 模型 / venv"

# 校验和里只写文件名（相对路径），别人下载后能直接 `sha256sum -c SHA256SUMS`
( cd "$OUT" && (sha256sum "$NAME.tar.gz" 2>/dev/null || shasum -a 256 "$NAME.tar.gz") > SHA256SUMS
  if [ "$WIN" = 1 ]; then (sha256sum "$NAME-win.zip" 2>/dev/null || shasum -a 256 "$NAME-win.zip") >> SHA256SUMS; fi )
echo "== 产物 =="
ls -lh "$OUT/$NAME.tar.gz" | awk '{print "  "$5"  "$9}'
cat "$OUT/SHA256SUMS" | sed 's/^/  /'
