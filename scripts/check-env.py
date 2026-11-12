#!/usr/bin/env python3
"""环境体检（跨平台版）：缺什么、版本够不够，一条命令看完。只读，不改任何东西。

    python scripts/check-env.py          # 人看
    python scripts/check-env.py --json   # AI/脚本解析：{"ok","fail","warn","issues","next"}

比 check-env.sh 多的：在 Windows 上也能跑（macOS / Linux / Windows 同一套逻辑）。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

WIN = os.name == "nt"
HOME = Path.home()
LIB = Path(os.environ.get("MF_LIB", HOME / "媒体库"))
MF = Path(os.environ.get("MF_HOME", HOME / "mediaflow"))
RULES = Path(os.environ.get("MF_RULES", HOME / "获客平台" / "知识库" / "剪辑规范.md"))
DJIAN = os.environ.get("DJIAN_API", "http://127.0.0.1:5180")
DJ_SRC = Path(os.environ.get("DJIAN_SRC", MF / "djian"))
DSH_PROFILE = HOME / ".dsh" / "profiles" / "desktop" / "node_modules" / "@djian"

JSON = "--json" in sys.argv
ok = bad = warn = 0
ISSUES: list[str] = []
NEXT: list[str] = []


def pass_(m: str) -> None:
    global ok
    ok += 1
    if not JSON:
        print(f"  \033[32m✓\033[0m {m}")


def fail(m: str, nxt: str | None = None) -> None:
    global bad
    bad += 1
    ISSUES.append(m)
    if nxt:
        NEXT.append(nxt)
    if not JSON:
        print(f"  \033[31m✗\033[0m {m}")


def soft(m: str) -> None:
    global warn
    warn += 1
    if not JSON:
        print(f"  \033[33m!\033[0m {m}")


def sec(t: str) -> None:
    if not JSON:
        print(f"\n== {t} ==")


def ver(cmd: str) -> str:
    try:
        r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=10)
        return (r.stdout or r.stderr).splitlines()[0][:60]
    except Exception:
        return "?"


def hint(winget: str, brew: str) -> str:
    return f"winget install {winget}" if WIN else f"brew install {brew}"


def need(cmd: str, nxt: str) -> bool:
    p = shutil.which(cmd)
    if p:
        pass_(f"{cmd} → {ver(cmd)}")
        return True
    fail(f"{cmd} 未安装", nxt)
    return False


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


if not JSON:
    print(
        "┌────────────────────────────────────────────────────────────────────┐\n"
        "│ 给 AI 助手：先跑完这个脚本，再决定装什么。                          │\n"
        "│ 不要在本机装 ollama / faster-whisper / GPT-SoVITS / torch / 模型权重 │\n"
        "│ ——那些是 Windows GPU 机的事。步骤见 docs/安装与复现.md。            │\n"
        "└────────────────────────────────────────────────────────────────────┘"
    )
    print(f"平台：{platform.system()} {platform.release()} · Python {platform.python_version()}")

sec("基础二进制")
need("ffmpeg", hint("Gyan.FFmpeg", "ffmpeg"))
need("ffprobe", hint("Gyan.FFmpeg", "ffmpeg"))
need("yt-dlp", hint("yt-dlp.yt-dlp", "yt-dlp"))
node_ok = need("node", hint("OpenJS.NodeJS.LTS", "node（需 >=22.18）"))
need("npm", "随 node 一起装")
if WIN:
    need("git", hint("Git.Git", "git"))
if not need("uv", hint("astral-sh.uv", "uv")) and not WIN:
    NEXT.pop()  # uv 只给 crv 用，没装不算失败
if not shutil.which("uv") and not JSON:
    print("  \033[33m·\033[0m uv 未装不影响剪片（只给 crv 用）")

sec("Node 版本（D剪 要求 >=22.18）")
if node_ok:
    try:
        nv = subprocess.run(["node", "-p", "process.versions.node"], capture_output=True, text=True, timeout=10).stdout.strip()
        major, minor = (int(x) for x in nv.split(".")[:2])
        if major > 22 or (major == 22 and minor >= 18):
            pass_(f"node {nv}")
        else:
            fail(f"node {nv} 太旧（需要 >=22.18）", "升 Node 到 22.18+")
    except Exception:
        soft("读不到 node 版本")

sec("目录与规则")
for d in (MF, LIB, RULES.parent):
    if d.is_dir():
        pass_(str(d))
    else:
        fail(f"{d} 不存在", f'mkdir "{d}"' if WIN else f"mkdir -p '{d}'")
if RULES.is_file():
    pass_(f"规则文件 {RULES}")
    txt = RULES.read_text(encoding="utf-8", errors="ignore")
    if '"lufs"' in txt:
        pass_("§9 机器参数块存在")
    else:
        fail("§9 机器参数块缺失", f'cp docs/剪辑规范.md "{RULES}"' if WIN else f"cp docs/剪辑规范.md '{RULES}'")
else:
    fail(f"规则文件缺失：{RULES}", f'cp docs/剪辑规范.md "{RULES}"')

sec("mf")
mf_bin = shutil.which("mf") or shutil.which("mf.cmd")
if mf_bin:
    pass_(f"mf 在 PATH：{mf_bin}")
else:
    fail("mf 不在 PATH", "Windows：把仓库根目录加进 PATH（里面有 mf.cmd）；macOS：写 ~/.local/bin/mf")
mf_py = MF / "mf.py"
if mf_py.exists():
    pass_(f"{mf_py}")
else:
    fail(f"{mf_py} 缺失", f'复制或软链仓库的 mf.py 到 "{mf_py}"')

sec("D剪 引擎（核心；缺了就剪不了）")
if http_ok(f"{DJIAN}/api/health"):
    pass_(f"引擎在线 {DJIAN}")
else:
    fail(f"引擎不在线 {DJIAN}", "起引擎：mf dj up（日志 ~/.djian/logs/engine.log）")
store = DJ_SRC / "packages" / "webui" / "server" / "store.mjs"
if store.parent.is_dir():
    pass_(f"上游源码 {DJ_SRC}")
    if "bindSessionTo" in store.read_text(encoding="utf-8", errors="ignore"):
        pass_("session-binding 补丁已打")
    else:
        fail("session-binding 补丁未打", "git apply engine/patches/djian-session-binding.patch")
else:
    fail(f"上游源码缺 {DJ_SRC}", "clone DSHL-DeepPack-Jian 到该目录并 checkout e1b6130")
if DSH_PROFILE.is_dir():
    n = len([p for p in DSH_PROFILE.iterdir() if p.is_dir()])
    if n >= 6:
        pass_(f"DSH 已 link @djian（{n} 个）")
    else:
        fail(f"DSH link 不全（{n}/6）", "按安装文档第 3 步在 profile package.json 加 6 条 link: 后 npm install")
else:
    fail("DSH 未接入 D剪", "按安装文档第 3 步 link @djian/* 进 DSH profile")

sec("Multiplane / crv")
mp = MF / "tools" / "multiplane" / "node_modules" / "multiplane"
if mp.is_dir():
    pass_("multiplane 已装")
else:
    fail("multiplane 未装", "npm install multiplane@0.3.13 --legacy-peer-deps + npx playwright install chromium")
if (MF / "tools" / "multiplane" / "node_modules" / "playwright").is_dir():
    pass_("playwright 已装")
else:
    soft("playwright 未装（渲染要 Chromium）")
crv = MF / "tools" / "crv" / ("Scripts/crv.exe" if WIN else "bin/crv")
if crv.exists():
    pass_("crv 已装")
else:
    soft("crv 未装（只影响拆片看图）")

sec("GPU（识别/翻译/配音才需要）")
if WIN:
    gpu_dir = Path("C:/mediagpu")
    if gpu_dir.is_dir():
        pass_("C:/mediagpu 存在")
    else:
        soft("没有 C:/mediagpu（本机只剪片也够用；要识别/配音再配）")
else:
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "l-l", "echo ok"],
                           capture_output=True, text=True, timeout=8)
        if "ok" in r.stdout:
            pass_("ssh l-l 可连")
        else:
            soft("ssh l-l 连不上（不配也能本机出片；识别/配音才需要）")
    except Exception:
        soft("ssh l-l 连不上（不配也能本机出片；识别/配音才需要）")

for p in ("ollama", "whisper", "gpt-sovits", "torch"):
    if shutil.which(p):
        soft(f"本机装了 {p} —— 这些应该只在 GPU 机上跑")

if JSON:
    print(json.dumps({"ok": ok, "fail": bad, "warn": warn, "issues": ISSUES, "next": NEXT}, ensure_ascii=False))
    sys.exit(0)

print(f"\n结果：\033[32m{ok} 通过\033[0m / \033[31m{bad} 失败\033[0m / \033[33m{warn} 提醒\033[0m")
if bad == 0:
    print("→ 可以开始：mf new <名称> -b 品硕 --platform dy")
else:
    print("→ 按顺序补（别乱装）：")
    for i, x in enumerate(NEXT, 1):
        print(f"   {i}) {x}")
    print("   * 不需要装 ollama / faster-whisper / GPT-SoVITS / torch —— 那是 GPU 机的事")
sys.exit(0)
