#!/usr/bin/env python3
"""mf — Mac 端视频流水线命令（素材在 Mac，GPU 任务经 SSH 交给 Windows l-l）。
用法: mf <命令> -h 查看各命令参数。"""
import argparse, asyncio, datetime as dt, json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from huoke_lint import format_violations, lint_text, lint_timeline  # noqa: E402

LIB = Path(os.environ.get("MF_LIB", Path.home() / "媒体库"))  # 素材库根，可用 MF_LIB 指到别的盘
FONTS = LIB / "素材" / "字体"
GPU_HOST = os.environ.get("MF_GPU_HOST", "lt@l-l")
GPU_PY = r"C:\mediagpu\venv\Scripts\python.exe"
GPU_WORKER = r"C:\mediagpu\bin\worker.py"
OLLAMA = os.environ.get("MF_OLLAMA", "http://l-l:11434")
LLM = os.environ.get("MF_LLM", "qwen2.5:14b")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
LANG_NAMES = {"zh": "简体中文", "en": "English", "vi": "Tiếng Việt (Vietnamese)", "ja": "日本語 (Japanese)", "ko": "한국어 (Korean)",
              "es": "Español (Latin America)", "th": "ภาษาไทย (Thai)", "id": "Bahasa Indonesia", "pt": "Português (Brasil)"}
EDGE_VOICES = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-AriaNeural", "vi": "vi-VN-HoaiMyNeural", "ja": "ja-JP-NanamiNeural",
               "ko": "ko-KR-SunHiNeural", "es": "es-MX-DaliaNeural", "th": "th-TH-PremwadeeNeural", "id": "id-ID-GadisNeural", "pt": "pt-BR-FranciscaNeural"}
SUB_FONT = {"zh": "Noto Sans CJK SC", "ja": "Noto Sans CJK JP", "ko": "Noto Sans CJK KR", "th": "Noto Sans Thai"}
# 平台短码与别名（规范 §9 platforms）；统一用 dy/sph/ks/xhs/tk/yt/li
PLATFORM_ALIAS = {"douyin": "dy", "抖音": "dy", "shipinhao": "sph", "视频号": "sph", "weixin": "sph",
                  "kuaishou": "ks", "快手": "ks", "xiaohongshu": "xhs", "小红书": "xhs", "rednote": "xhs",
                  "tiktok": "tk", "youtube": "yt", "linkedin": "li", "shorts": "tk"}

# 唯一规则源：~/获客平台/知识库/剪辑规范.md（§9 机器参数）。改规则只改那个文件。
RULES_MD = Path(os.environ.get("MF_RULES", Path.home() / "获客平台" / "知识库" / "剪辑规范.md"))
DJIAN_API = os.environ.get("MF_DJIAN_API", "http://127.0.0.1:5180")
TOOLS = Path(os.environ.get("MF_TOOLS", Path.home() / "mediaflow" / "tools"))
MULTIPLANE = TOOLS / "multiplane"
CRV_BIN = TOOLS / "crv" / "bin" / "crv"
MP_SHOTS = LIB / "素材" / "模板" / "multiplane"
TPL_DIR = Path(os.environ.get("MF_SHOTS", Path(__file__).resolve().parent / "shots"))
UPLOAD_LIMIT = 512 * 1024 * 1024

_rules_cache = None
def rules():
    """读剪辑规范 §9 的机器参数块。"""
    global _rules_cache
    if _rules_cache is not None: return _rules_cache
    if not RULES_MD.exists(): die(f"找不到剪辑规范 {RULES_MD}")
    blocks = re.findall(r"```json\s*(.*?)```", RULES_MD.read_text(encoding="utf-8"), re.S)
    if not blocks: die(f"{RULES_MD} 里没有 ```json 机器参数块")
    _rules_cache = json.loads(blocks[-1])
    return _rules_cache

def plat(p):
    k = (p or "").strip().lower(); k = PLATFORM_ALIAS.get(k, k)
    if k not in rules()["platforms"]: die(f"平台只能是 {list(rules()['platforms'])}（或别名 douyin/tiktok/youtube…），收到 {p}")
    return k

def canvas_of(platform=None):
    r = rules()
    kind = r["platforms"].get(plat(platform) if platform else "", {}).get("canvas", "vertical")
    w, h, fps = r["canvas"][kind]
    return {"width": w, "height": h, "fps": fps}

def code_ok(brand, code):
    """内容编号：PS/HH-平台-日期-序号（剪辑规范 §8）。"""
    want = "PS" if norm_brand(brand) == "品硕" else "HH"
    return bool(code) and re.fullmatch(rf"{want}-[A-Z]+-\d{{8}}-\d{{2}}", code) is not None

def project_name(raw):
    """工程名 = 日期-<名称>；已经带日期就不再重复加。"""
    raw = (raw or "").strip()
    return raw if re.match(r"^\d{8}-", raw) else f"{dt.date.today():%Y%m%d}-{raw}"

def print_rules(proj=None):
    r = rules()
    d = r["duration"]; s = r["subtitles"]; au = r["audio"]
    print(f"规则 v{r['version']}（{RULES_MD.name}）：竖屏 {r['canvas']['vertical'][0]}×{r['canvas']['vertical'][1]}@{r['canvas']['vertical'][2]}"
          f" · 时长 {d['min']}–{d['max']}s · 镜头 {r['shot_seconds'][0]}–{r['shot_seconds'][1]}s"
          f" · 转场≤{r['transitions']['max_per_film']} · 字幕在最底部 {s['font_size_px'][0]}–{s['font_size_px'][1]}px/留白 {s['bottom_margin_px']}px 不加底框"
          f" · 配乐 {au['music'][0]}–{au['music'][1]} · {au['lufs']} LUFS")
    print(f"合规：品牌隔离 · 无联系方式 · 不报价 · 无绝对化用语 · AI 标识 · CTA「{r['cta']['cn']}」")


def log(*a): print("·", *a, file=sys.stderr, flush=True)
def die(msg): print("✗", msg, file=sys.stderr); sys.exit(1)

def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        die(f"命令失败: {' '.join(map(str, cmd))[:300]}\n{(r.stderr or r.stdout)[-2000:]}")
    return r.stdout

def ffmpeg(*args): run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args])
def probe(p): return json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", p]))
def duration(p): return float(probe(p)["format"]["duration"])

# ---------- 项目 ----------
def project_dir(name=None):
    if name:
        p = Path(name).expanduser()
        if p.is_dir(): return p.resolve()
        hits = sorted(d for d in (LIB / "工程").iterdir() if d.is_dir() and (d.name == name or d.name.endswith("-" + name)))
        if not hits: die(f"找不到工程 {name}，先 mf new {name}")
        return hits[-1]
    cwd = Path.cwd().resolve()
    for p in [cwd, *cwd.parents]:
        if p.parent == (LIB / "工程").resolve(): return p
    die("请用 -p 指定工程，或 cd 到 ~/媒体库/工程/<项目> 下运行")

BRANDS = {"品硕": "品硕", "ps": "品硕", "pinsontec": "品硕", "晖华": "晖华", "hh": "晖华", "huihua": "晖华"}
def norm_brand(b):
    k = (b or "").strip().lower()
    if k not in BRANDS: die(f"品牌只能是 品硕/晖华（或 ps/hh），收到：{b}")
    return BRANDS[k]

def project_brand(proj, override=None):
    if override: return norm_brand(override)
    f = proj / ".brand"
    if f.exists(): return norm_brand(f.read_text().strip())
    die(f"工程 {proj.name} 没有登记品牌，加 --brand 品硕/晖华，或写入 {f}")

# ---------- D剪 引擎（素材与时间线都在这边，mf 只管调用） ----------
def dj_api(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(DJIAN_API.rstrip("/") + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Djian-Client": "mf"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        die(f"D剪 接口 {method} {path} 失败 {e.code}: {e.read().decode()[:500]}")
    except urllib.error.URLError as e:
        die(f"D剪 引擎没响应（{DJIAN_API}）。先打开 D剪 面板再试。\n{e}")

def dj_ready():
    """静默探活：不打印、不退出，只回答"在不在"。"""
    try:
        with urllib.request.urlopen(DJIAN_API.rstrip("/") + "/api/health", timeout=3) as r:
            return json.loads(r.read().decode() or "{}").get("service") == "djian-engine"
    except Exception:
        return False

def dj_create(name, canvas):
    return dj_api("POST", "/api/projects", {"name": name, "meta": canvas})["id"]

def dj_state(proj):
    f = proj / ".djian.json"
    return json.loads(f.read_text()) if f.exists() else None

def dj_pid(proj):
    st = dj_state(proj)
    if not st: die(f"工程 {proj.name} 还没绑定 D剪 项目，跑 mf dj new {proj.name}")
    return st["id"]

def split_big(p, dest, limit=UPLOAD_LIMIT - 8 * 1024 * 1024):
    """D剪 单文件上限 512MB：超了就按时间均匀切段（-c copy，不重编码）。"""
    n = int(p.stat().st_size // limit) + 1
    seg = duration(p) / n + 0.5
    dest.mkdir(parents=True, exist_ok=True); out = []
    for i in range(n):
        q = dest / f"{p.stem}_part{i + 1}{p.suffix}"
        ffmpeg("-ss", f"{i * seg:.3f}", "-t", f"{seg:.3f}", "-i", p, "-c", "copy", "-avoid_negative_ts", "make_zero", q)
        out.append(q)
    log(f"{p.name} {p.stat().st_size / 1e6:.0f}MB 超过上限，按时间切成 {n} 段")
    return out

def check_brand(proj, p):
    """品牌隔离：一个工程只用一个品牌的素材（剪辑规范 §4.1）。"""
    brand = project_brand(proj); other = "晖华" if brand == "品硕" else "品硕"
    if f"/源片/{other}/" in str(p): die(f"品牌隔离：{p.name} 属于 {other}，不能进 {brand} 工程 {proj.name}")
    return p

def dj_import(pid, files, proj=None):
    got = []
    for f in files:
        p = Path(f).expanduser().resolve()
        if not p.is_file(): log("跳过（不是文件）", p); continue
        if proj is not None: check_brand(proj, p)
        for q in (split_big(p, (proj or p.parent) / "剪辑" / "_分段") if p.stat().st_size > UPLOAD_LIMIT else [p]):
            r = dj_api("POST", f"/api/p/{pid}/assets/import", {"path": str(q), "name": q.name})
            name = r.get("name") or r.get("asset") or r
            got.append(name); log("导入", name)
    return got

def auto_bind(proj, pid):
    """建项目后自动把当前会话指过去，并清掉当天空的自动项目。"""
    sid = os.environ.get("DSH_SESSION_ID")
    if not sid:
        return
    try:
        dj_api("POST", "/api/session-project", {"sessionId": sid, "pid": pid})
        print(f"已把当前会话绑定到这个项目（{sid[:18]}…）")
    except SystemExit:
        return
    empty = []
    for item in dj_api("GET", "/api/projects").get("projects", []):
        if item["id"] == pid: continue
        tl = (dj_api("GET", f"/api/p/{item['id']}/timeline") or {}).get("timeline") or {}
        clips = sum(len(t.get("clips") or []) for t in tl.get("videoTracks") or []) + sum(len(t.get("clips") or []) for t in tl.get("audioTracks") or [])
        assets = len(dj_api("GET", f"/api/p/{item['id']}/assets").get("assets", []))
        if not clips and not assets: empty.append(item)
    for item in empty:
        dj_api("DELETE", f"/api/projects/{item['id']}")
    if empty:
        print(f"顺手清掉 {len(empty)} 个空项目（进回收站）")


def cmd_dj(a):
    if a.action in ("up", "down", "status"): return cmd_serve(a)
    proj = project_dir(a.project) if a.project else None
    if proj is None and a.action in ("new", "import", "bind", "check"):
        proj = project_dir(None)      # 没给工程名时按 cwd 推断；推不出来 die 给中文提示
    if a.action == "new":
        st = dj_state(proj)
        if st:
            print(f"已经绑过 D剪 项目 {st['id']}（{st.get('canvas')}），要换项目先删 {proj / '.djian.json'}")
            return
        canvas = canvas_of(a.platform)
        pid = dj_create(proj.name, canvas)
        (proj / ".djian.json").write_text(json.dumps({"id": pid, "name": proj.name, "canvas": canvas}, ensure_ascii=False, indent=1))
        print(f"D剪 项目 {pid}（{canvas['width']}×{canvas['height']}@{canvas['fps']}）")
        auto_bind(proj, pid)
        return
    if a.action == "prune":
        empty = []
        for item in dj_api("GET", "/api/projects").get("projects", []):
            if proj and dj_state(proj) and item["id"] == dj_state(proj)["id"]: continue
            tl = (dj_api("GET", f"/api/p/{item['id']}/timeline") or {}).get("timeline") or {}
            clips = sum(len(t.get("clips") or []) for t in tl.get("videoTracks") or []) + sum(len(t.get("clips") or []) for t in tl.get("audioTracks") or [])
            assets = len(dj_api("GET", f"/api/p/{item['id']}/assets").get("assets", []))
            if not clips and not assets: empty.append(item)
        print(f"空项目 {len(empty)} 个（无片段、无素材）")
        for item in empty: print(" ", item["id"], item.get("name"))
        if a.yes:
            for item in empty: dj_api("DELETE", f"/api/projects/{item['id']}")
            print(f"已移到 D剪 回收站 {len(empty)} 个")
        elif empty: print("加 --yes 才真删（进回收站，可恢复）")
        return
    pid = dj_pid(proj)
    if a.action == "bind":
        sid = a.session or os.environ.get("DSH_SESSION_ID")
        if not sid: die("没有 DSH_SESSION_ID，用 --session 指定会话 id")
        f = Path.home() / ".djian" / "sessions.json"
        m = json.loads(f.read_text()) if f.exists() else {}
        old = m.get(sid)
        if old and old != pid and not a.yes:
            die(f"本会话已绑定 {old}，换绑会丢掉原映射；确认要换加 --yes")
        try:
            dj_api("POST", "/api/session-project", {"sessionId": sid, "pid": pid})
        except SystemExit:
            m[sid] = pid
            tmp = f.with_suffix(".json.tmp"); tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2)); tmp.replace(f)
        print(f"会话 {sid} → {pid}（原 {old or '无'}）")
        return
    if a.action == "import":
        if not a.files: die("给要导入的文件或目录（绝对路径）")
        files = []
        for f in a.files:
            p = Path(f).expanduser()
            files += sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
        for n in dj_import(pid, files, proj): print(n)
        return
    # check：开剪前的确认单
    tl = (dj_api("GET", f"/api/p/{pid}/timeline") or {}).get("timeline") or {}
    assets = dj_api("GET", f"/api/p/{pid}/assets").get("assets", [])
    print(f"工程 {proj.name}（品牌 {project_brand(proj)}）→ D剪 {pid}（{DJIAN_API}）")
    print_rules()
    meta = tl.get("meta") or {}
    clips = sum(len(t.get("clips") or []) for t in tl.get("videoTracks") or [])
    ovl = len(tl.get("overlays") or [])
    print(f"D剪 画布 {meta.get('width')}×{meta.get('height')}@{meta.get('fps')} · 素材 {len(assets)} 个 · 视频片段 {clips} 条 · 字幕/元素 {ovl} 条")
    src = LIB / "素材" / "源片" / project_brand(proj)
    print(f"源片目录 {src}（{'有' if src.exists() else '缺'}）")
    if not assets: print("! 素材库是空的：先 mf dj import 或 mf new --import <目录>")
    print(f"字幕：{rules()['subtitles']['engine']} 内做，不用 mf burn")
    vs = lint_timeline(tl, rules())
    if vs:
        print(f"\n✗ 合规检查不通过 {len(vs)} 处（剪辑规范 §4）：")
        print(format_violations(vs))
        sys.exit(1)
    print("合规检查：通过（无联系方式/报价/绝对化/禁用词）")

def cmd_lint(a):
    """文案/时间线合规检查：mf lint 文案.txt / -t "文本" / -p <工程>"""
    r = rules(); vs = []
    if a.project:
        tl = (dj_api("GET", f"/api/p/{dj_pid(project_dir(a.project))}/timeline") or {}).get("timeline") or {}
        vs = lint_timeline(tl, r)
    else:
        if a.text: vs += lint_text(a.text, r, "参数")
        for f in a.files or []:
            vs += lint_text(Path(f).expanduser().read_text(encoding="utf-8"), r, f)
    if not vs: print("合规检查：通过"); return
    print(f"✗ {len(vs)} 处问题："); print(format_violations(vs)); sys.exit(1)

# ---------- 引擎生命周期（谁起的、怎么收） ----------
DJ_ROOT = Path(os.environ.get("MF_DJIAN_ROOT", Path.home() / "mediaflow" / "djian"))
DJ_ENTRY = Path(os.environ.get("MF_DJIAN_ENTRY", "")) if os.environ.get("MF_DJIAN_ENTRY") else None

def dj_entry():
    """引擎入口：优先用 DSH 里装的那份，回落到开发态仓库。"""
    if DJ_ENTRY: return DJ_ENTRY
    for c in (Path.home() / ".dsh" / "profiles" / "desktop" / "node_modules" / "@djian" / "webui" / "server" / "index.mjs",
              DJ_ROOT / "packages" / "webui" / "server" / "index.mjs"):
        if c.exists(): return c
    die("找不到 D剪 引擎入口（D剪 面板没装好？）")

def dj_pidfile():
    f = Path.home() / ".djian" / "engine-port.json"
    try: return json.loads(f.read_text())
    except Exception: return {}

def cmd_serve(a):
    info = dj_pidfile()
    if a.action == "status" or (a.action == "up" and dj_ready()):
        ok = dj_ready()
        print(f"D剪 引擎 {'✔ 在跑' if ok else '✗ 没起'}  {DJIAN_API}")
        if info: print(f"  pid {info.get('pid')} · 端口 {info.get('port')} · 起于 {info.get('startedAt')} · v{info.get('version')}")
        if a.action == "status": sys.exit(0 if ok else 1)
        return
    if a.action == "down":
        pid = info.get("pid")
        if not pid: print("没有记录 pid（~/.djian/engine-port.json）；可能本来就没起"); return
        if os.name == "nt":
            tl = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
            if str(pid) not in tl:
                print(f"pid {pid} 已经不在（可能本来就没起）"); return
        else:
            try:
                ps = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
            except Exception:
                ps = ""
            if "webui/server/index.mjs" not in ps:
                print(f"pid {pid} 已经不是 D剪 引擎（{ps.strip()[:60]}），不动它"); return
        os.kill(int(pid), 15)
        for _ in range(40):
            time.sleep(0.25)
            if not dj_ready(): print(f"已停 pid {pid}"); return
        die(f"pid {pid} 15 秒还没退，手动 kill -9 {pid}")
    # up：起一个脱离终端的引擎，日志进 ~/.djian/logs/engine.log
    entry = dj_entry()
    logdir = Path.home() / ".djian" / "logs"; logdir.mkdir(parents=True, exist_ok=True)
    logf = logdir / "engine.log"
    log(f"启动引擎 {entry}")
    with logf.open("ab") as fh:
        kw = dict(stdout=fh, stderr=subprocess.STDOUT)
        if os.name == "nt":
            kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        subprocess.Popen(["node", str(entry)],
                         cwd=str(DJ_ROOT if (DJ_ROOT / "package.json").exists() else entry.parent), **kw)
    for _ in range(60):
        time.sleep(0.25)
        if dj_ready():
            info = dj_pidfile()
            print(f"D剪 引擎已起 pid {info.get('pid')} → {DJIAN_API}\n日志 {logf}")
            return
    die(f"引擎 15 秒内没响应，看日志：{logf}")

def cmd_new(a):
    kind = a.kind
    brand = norm_brand(a.brand)
    name = project_name(a.name)
    proj = LIB / "工程" / name
    for sub in ["识别", "配音", "剪辑", "包装"]: (proj / sub).mkdir(parents=True, exist_ok=True)
    (proj / ".brand").write_text(brand)
    (proj / ".kind").write_text(kind)
    (proj / "README.md").write_text(
        f"# {name}\n\n"
        f"判定：{'成片（只加字幕 + TTS 配音，保持原片风格，不重剪）' if kind == 'film' else '素材（按剪辑规范 §1–§3 成品风格剪）'}"
        f"（剪辑规范 §0）\n品牌：{brand}\n平台：{a.platform}\n\n"
        "剪完按 §10 复验：语音回读 / 字幕覆盖 / 单音轨 / QC / 抽帧 / 合规 / 编号一致。\n",
        encoding="utf-8")
    out = LIB / "成品" / brand / name; out.mkdir(parents=True, exist_ok=True)
    canvas = canvas_of(a.platform)
    print(f"{proj}\n成品 → {out}\n素材 → {LIB / '素材' / '源片' / brand}\n判定 → {'成片：只加字幕+TTS，保持原片风格' if kind == 'film' else '素材：按成品风格剪'}（规范 §0）")
    try:
        pid = dj_create(name, canvas)
        (proj / ".djian.json").write_text(json.dumps({"id": pid, "name": name, "canvas": canvas}, ensure_ascii=False, indent=1))
        print(f"D剪 → 项目 {pid}（{canvas['width']}×{canvas['height']}@{canvas['fps']}，{a.platform or '竖屏'}）")
        if a.import_from:
            p = Path(a.import_from).expanduser()
            files = sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
            for n in dj_import(pid, files, proj): print("素材", n)
        auto_bind(proj, pid)
    except SystemExit:
        print("! D剪 引擎没开，工程目录已建好；打开 D剪 面板后跑 mf dj new " + name)
    print_rules(proj)


# ---------- GPU 远程 ----------
def gpu(sub, inputs, args, outputs, dest):
    """上传 inputs → 运行 worker → 下载 outputs 到 dest。inputs: {远端名: 本地路径}"""
    jid = f"{dt.datetime.now():%m%d%H%M%S}-{uuid.uuid4().hex[:4]}"
    rdir = f"C:/mediagpu/jobs/{jid}"; wdir = rdir.replace("/", "\\")
    run(SSH + [GPU_HOST, f'mkdir "{wdir}"'])
    for rn, lp in inputs.items():
        log(f"上传 {Path(lp).name} ({Path(lp).stat().st_size/1e6:.1f} MB)")
        run(["scp", "-q", lp, f"{GPU_HOST}:{rdir}/{rn}"])
    rargs = " ".join(f'"{x}"' for x in args)
    log(f"GPU 运行 {sub} …"); t0 = time.time()
    r = subprocess.run(SSH + [GPU_HOST, f'cd /d "{wdir}" && "{GPU_PY}" "{GPU_WORKER}" {sub} {rargs}'], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode: die(f"GPU 任务失败 ({jid}):\n{r.stderr[-3000:]}")
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    log(f"完成 {time.time()-t0:.1f}s {last}")
    dest.mkdir(parents=True, exist_ok=True); got = []
    for rn, ln in outputs.items():
        run(["scp", "-q", f"{GPU_HOST}:{rdir}/{rn}", dest / ln]); got.append(dest / ln)
    if not os.environ.get("MF_KEEP_JOBS"): subprocess.run(SSH + [GPU_HOST, f'rmdir /s /q "{wdir}"'], capture_output=True)
    return got

def cmd_health(a):
    out = subprocess.run(SSH + [GPU_HOST, f'"{GPU_PY}" "{GPU_WORKER}" health'], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("GPU:", out.stdout.strip() or out.stderr.strip()[-500:])
    try:
        tags = json.load(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5))
        print("Ollama:", [m["name"] for m in tags["models"]])
    except Exception as e: print("Ollama: 不可用", e)
    for t in ["ffmpeg", "ffprobe", "yt-dlp", "node", "npx"]:
        print(t, "OK" if subprocess.run(["which", t], capture_output=True).returncode == 0 else "缺失")
    print("D剪:", "OK " + DJIAN_API if dj_ready() else f"未响应（打开 D剪 面板，或设 MF_DJIAN_API，当前 {DJIAN_API}）")
    print("Multiplane:", "OK " + str(MULTIPLANE) if MULTIPLANE.exists() else "缺失 " + str(MULTIPLANE))
    print("crv:", "OK " + str(CRV_BIN) if CRV_BIN.exists() else "缺失 " + str(CRV_BIN))
    print("规则:", RULES_MD if RULES_MD.exists() else "缺失 " + str(RULES_MD))

def cmd_verify(a):
    """剪后复验（规范 §10）：QC 指标、音轨数、抽帧看片，可选语音回读。"""
    vid = Path(a.input).resolve()
    if not vid.exists(): die(f"找不到成片 {vid}")
    rep = qc(str(vid))
    print("技术指标:", json.dumps(rep, ensure_ascii=False))
    ok = rep.get("ok")
    streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(vid)],
                                        capture_output=True, text=True).stdout or "{}").get("streams", [])
    audible = [x for x in streams if x.get("codec_type") == "audio" and float(x.get("duration") or 0) > 0.5]
    print(f"音轨: {len(audible)} 条", "✅" if len(audible) == 1 else "❌ 应为 1 条（多版本叠音是典型事故）")
    proj = project_dir(a.project) if a.project else vid.parent
    out = Path(a.out) if a.out else proj / "复验"
    out.mkdir(parents=True, exist_ok=True)
    dur = float(rep.get("duration") or 0)
    n = max(4, min(12, a.frames)); step = dur / n
    files = []
    for i in range(n):
        f = out / f"f{i+1:02d}.jpg"
        ffmpeg("-ss", f"{i*step + step/2:.2f}", "-i", vid, "-frames:v", "1", "-vf", "scale=270:-1", f)
        files.append(f)
    sheet = out / f"{vid.stem}_复验抽帧.jpg"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-pattern_type", "glob",
                    "-i", str(out / "f*.jpg"), "-filter_complex", f"tile={min(6, n)}x{(n + min(6, n) - 1)//min(6, n)}",
                    "-frames:v", "1", str(sheet)], check=False)
    print("抽帧:", sheet)
    if a.lang:
        wav = out / "verify.wav"
        ffmpeg("-i", vid, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav)
        ns = argparse.Namespace(input=str(wav), project=str(proj / "识别"), lang=a.lang, model=None, prompt=None)
        print("语音回读（ASR）…"); cmd_asr(ns)
        srt = proj / "识别" / "verify.srt"
        if srt.exists():
            txt = " ".join(r["text"] for r in read_srt(srt))
            (out / "回读.txt").write_text(txt, encoding="utf-8")
            print("回读文本:", txt[:400])
    print("结论:", "通过" if ok and len(audible) == 1 else "要修（看上面 ❌）")

def cmd_asr(a):
    proj = project_dir(a.project); src = Path(a.input).resolve()
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "in.wav"
        ffmpeg("-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav)
        extra = (["--language", a.lang] if a.lang else []) + (["--model", a.model] if a.model else []) + (["--prompt", a.prompt] if a.prompt else [])
        got = gpu("asr", {"in.wav": wav}, ["in.wav", "out.json", *extra], {"out.json": f"{src.stem}.json", "out.srt": f"{src.stem}.srt"}, proj / "识别")
    print(got[1])

def cmd_sep(a):
    proj = project_dir(a.project); src = Path(a.input).resolve()
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "in.wav"
        ffmpeg("-i", src, "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", wav)
        got = gpu("sep", {"in.wav": wav}, ["in.wav", "."], {"vocals.wav": f"{src.stem}_人声.wav", "no_vocals.wav": f"{src.stem}_伴奏.wav"}, proj / "识别")
    for g in got: print(g)

# ---------- SRT ----------
def tsec(t):
    h, m, s = t.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(s)
def fmt(s):
    ms = max(0, round(s * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
def read_srt(p):
    rows = []
    for blk in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8-sig").replace("\r", "").strip()):
        lines = blk.split("\n")
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None: continue
        s, e = [x.strip() for x in lines[i].split("-->")]
        rows.append({"start": tsec(s), "end": tsec(e.split()[0]), "text": "\n".join(lines[i + 1:]).strip()})
    return rows
def write_srt(rows, p):
    Path(p).write_text("".join(f"{i}\n{fmt(r['start'])} --> {fmt(r['end'])}\n{r['text']}\n\n" for i, r in enumerate(rows, 1)), encoding="utf-8")
def lang_of(p, default="zh"):
    parts = Path(p).name.split(".")
    for x in reversed(parts[1:-1]):
        if x in LANG_NAMES: return x
    return default

# ---------- 翻译 (Windows ollama) ----------
TR_SYS = """你是短视频本地化译者，不是文学翻译。把用户给的口播字幕逐条译成{lang}。
铁律：
1. 口语化，像本地人在镜头前说话，不要书面语、不要新闻腔
2. 译文长度尽量贴近原文——这是口播，太长来不及念，太短对不上画面
3. 品牌名、人名、地名、产品型号保留原文，不音译
4. 不改写意思、不补充信息、不删减
5. 语气词按目标语言习惯自然处理，不要逐字翻
{note}
只返回 JSON，形如 {{"items":[{{"i":1,"t":"译文"}}]}}，i 必须原样回传。"""

def llm_json(system, user):
    body = {"model": LLM, "stream": False, "format": "json", "options": {"temperature": 0.3, "num_ctx": 8192, "num_predict": 4096},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Djian-Client": "mf"})
    raw = json.load(urllib.request.urlopen(req, timeout=600))["message"]["content"].strip()
    raw = re.sub(r"^```(json)?|```$", "", raw).strip()
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])

def translate_lines(lines, to, note="", batch=10):
    system = TR_SYS.format(lang=LANG_NAMES.get(to, to), note=("补充要求：" + note) if note else "")
    out = list(lines)
    for i in range(0, len(lines), batch):
        chunk = [{"i": k + 1, "t": t} for k, t in enumerate(lines[i:i + batch])]
        got = {}
        for _ in range(2):
            try:
                got = {int(x["i"]): str(x["t"]).strip() for x in llm_json(system, json.dumps({"items": chunk}, ensure_ascii=False)).get("items", [])}
                if len(got) >= len(chunk): break
            except Exception as ex: log("重试翻译", ex)
        for it in chunk:  # 缺的逐条补
            if it["i"] not in got:
                try: got[it["i"]] = str(llm_json(system, json.dumps({"items": [{"i": 1, "t": it["t"]}]}, ensure_ascii=False))["items"][0]["t"]).strip()
                except Exception as ex: log("单条失败，保留原文", it["t"], ex); got[it["i"]] = it["t"]
            out[i + it["i"] - 1] = got[it["i"]]
        if to not in ("zh", "ja"):  # 小模型偶尔夹带中文：逐条重译，仍夹带则告警
            for it in chunk:
                k = i + it["i"] - 1
                for _ in range(2):
                    if not re.search(r"[\u4e00-\u9fff]", out[k]): break
                    try:
                        out[k] = str(llm_json(system + f"\n注意：译文中绝对不能出现任何汉字，所有词都必须用{LANG_NAMES.get(to, to)}表达。",
                                              json.dumps({"items": [{"i": 1, "t": it["t"]}]}, ensure_ascii=False))["items"][0]["t"]).strip()
                    except Exception as ex: log("重译失败", ex)
                if re.search(r"[\u4e00-\u9fff]", out[k]): log(f"⚠ 第 {k+1} 条仍含汉字，请人工校对: {out[k]}")
        log(f"翻译 {min(i+batch, len(lines))}/{len(lines)}（{LLM}）")
    return out

def cmd_translate(a):
    src = Path(a.input); rows = read_srt(src)
    for r, t in zip(rows, translate_lines([r["text"].replace("\n", " ") for r in rows], a.to, a.note or "")): r["text"] = t
    out = Path(a.output) if a.output else src.with_name(f"{src.name.split('.')[0]}.{a.to}.srt")
    write_srt(rows, out); print(out)

# ---------- 配音 ----------
def decode(p, sr=48000):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)

async def edge_say(text, voice, rate, out):
    import edge_tts
    for k in range(4):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(out)); return
        except Exception:
            if k == 3: raise
            await asyncio.sleep(2 + k * 2)

def cmd_tts(a):
    """srt → 按时间轴对齐的整轨配音；txt → 单段配音"""
    import numpy as np
    src = Path(a.input); lang = a.lang or lang_of(src)
    voice = a.voice or EDGE_VOICES.get(lang, EDGE_VOICES["zh"])
    out = Path(a.output) if a.output else src.with_name(src.name.split(".")[0] + f".{lang}.dub.wav")
    sr = 48000
    with tempfile.TemporaryDirectory() as td:
        if src.suffix.lower() != ".srt":
            mp3 = Path(td) / "a.mp3"; asyncio.run(edge_say(src.read_text(encoding="utf-8"), voice, a.rate, mp3))
            ffmpeg("-i", mp3, "-ar", sr, "-ac", 1, out); print(out); return
        rows = read_srt(src)
        async def all_():
            sem = asyncio.Semaphore(6)
            async def one(i, r):
                async with sem: await edge_say(r["text"].replace("\n", " "), voice, a.rate, Path(td) / f"{i}.mp3")
            await asyncio.gather(*(one(i, r) for i, r in enumerate(rows) if r["text"].strip()))
        asyncio.run(all_())
        total = a.length or rows[-1]["end"] + 2
        track = np.zeros(int(total * sr) + sr, dtype=np.float32); fixed = 0
        for i, r in enumerate(rows):
            f = Path(td) / f"{i}.mp3"
            if not f.exists(): continue
            nxt = rows[i + 1]["start"] if i + 1 < len(rows) else total
            slot = max(0.3, nxt - r["start"] - 0.05)
            seg = decode(f, sr); d = len(seg) / sr
            if d > slot:  # 超时则加速（最多 1.6x），仍超出就截尾淡出
                tempo = min(1.6, d / slot); fixed += 1
                g = Path(td) / f"{i}f.wav"; ffmpeg("-i", f, "-filter:a", f"atempo={tempo:.3f}", g); seg = decode(g, sr)
            n = min(len(seg), int(slot * sr)); seg = seg[:n].copy()
            fade = min(n, int(0.03 * sr))
            if fade: seg[n - fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
            s = int(r["start"] * sr); m = min(n, len(track) - s); track[s:s + m] += seg[:m]
        peak = float(np.abs(track).max() or 1); track *= min(1.0, 0.95 / peak)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", str(out)], input=track.tobytes(), check=True)
    log(f"{len(rows)} 条，{fixed} 条加速对齐，音色 {voice}"); print(out)

def cmd_sovits(a):
    proj = project_dir(a.project); txt = Path(a.input).resolve(); ref = Path(a.ref).resolve()
    out = Path(a.output) if a.output else proj / "配音" / f"{txt.stem}.sovits.wav"
    got = gpu("sovits", {"in.txt": txt, "ref" + ref.suffix: ref},
              ["in.txt", "out.wav", "--lang", a.lang, "--ref", "ref" + ref.suffix, "--ref-text", a.ref_text or "", "--speed", a.speed],
              {"out.wav": out.name}, out.parent)
    print(got[0])

# ---------- 剪辑 ----------
def cmd_scenes(a):
    from scenedetect import detect, ContentDetector
    src = Path(a.input); scenes = detect(str(src), ContentDetector(threshold=a.threshold))
    rows = [{"i": i + 1, "start": round(s.get_seconds(), 3), "end": round(e.get_seconds(), 3)} for i, (s, e) in enumerate(scenes)]
    out = Path(a.output) if a.output else (project_dir(a.project) / "识别" / f"{src.stem}.scenes.json" if a.project else src.with_suffix(".scenes.json"))
    out.write_text(json.dumps(rows, indent=1)); log(f"{len(rows)} 个镜头"); print(out)

def cmd_cut_silence(a):
    src = Path(a.input)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", f"silencedetect=noise={a.noise}dB:d={a.min}", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]; ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
    total = duration(src); keep = []; cur = 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s + a.pad > cur + 0.05: keep.append((cur, min(total, s + a.pad)))
        cur = max(cur, e - a.pad)
    if total - cur > 0.05: keep.append((cur, total))
    out = Path(a.output) if a.output else src.with_name(src.stem + "_去静音" + src.suffix)
    sel = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keep)
    ffmpeg("-i", src, "-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB", "-af", f"aselect='{sel}',asetpts=N/SR/TB",
           "-c:v", "h264_videotoolbox", "-b:v", "12M", "-c:a", "aac", "-b:a", "192k", out)
    log(f"保留 {len(keep)} 段，{total:.1f}s → {sum(e-s for s,e in keep):.1f}s"); print(out)

def srt_to_ass(srt, ass, lang, W, H, size, margin):
    """生成像素坐标的 ASS（PlayRes=视频分辨率），字号/边距按真实像素算，避免 libass 默认 384x288 缩放导致位置跑偏"""
    font = SUB_FONT.get(lang, "Noto Sans")
    def t(x):
        cs = round(x * 100); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{max(2, size//14)},1,2,{W//12},{W//12},{margin},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev = "".join(f"Dialogue: 0,{t(r['start'])},{t(r['end'])},Default,,0,0,0,,{r['text'].replace(chr(10), chr(92)+'N')}\n" for r in read_srt(srt))
    Path(ass).write_text(head + ev, encoding="utf-8")
def cmd_mix(a):
    """把配音和背景音（伴奏或原音）混合并替换视频音轨"""
    src = Path(a.video); out = Path(a.output) if a.output else src.with_name(src.stem + "_配音" + src.suffix)
    ins = ["-i", src, "-i", a.voice]; fc = f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={a.voice_gain}dB,asplit=2[v][vk];"
    if a.bgm:
        ins += ["-i", a.bgm]
        fc += (f"[2:a]aresample=48000,aformat=channel_layouts=stereo,volume={a.bgm_gain}dB[b];"
               f"[b][vk]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[bd];[bd][v]amix=inputs=2:normalize=0:duration=longest[a]")
    else: fc += "[vk]anullsink;[v]anull[a]"
    ffmpeg(*ins, "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out)
    print(out)

def lint_gate(proj, force=False):
    """导出前的硬闸门：时间线里的对外文案有违规就不许出片。"""
    try:
        tl = (dj_api("GET", f"/api/p/{dj_pid(proj)}/timeline") or {}).get("timeline") or {}
    except SystemExit:
        return  # 引擎不在（如纯转码），交给 mf dj check
    vs = lint_timeline(tl, rules())
    if not vs: return
    print(f"✗ 合规检查不通过 {len(vs)} 处，不出片：\n{format_violations(vs)}", file=sys.stderr)
    if not force: die("改掉上面的问题再导出；确认要强出加 --force")
    print("! --force：带着违规继续导出（发布前必须修）", file=sys.stderr)

def last_json_block(text):
    """ffmpeg 的 loudnorm 会打印 JSON；偶发前后夹带其它大括号内容，取最后一个能解析且含 input_i 的块。"""
    end = text.rfind("}")
    while end != -1:
        start = text.rfind("{", 0, end)
        if start == -1:
            break
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict) and "input_i" in obj:
                return obj
        except Exception:
            pass
        end = text.rfind("}", 0, end)
    return None


def cmd_export(a):
    src = Path(a.input); proj = project_dir(a.project); a.platform = plat(a.platform)
    r = rules(); canvas = canvas_of(a.platform); W, H = canvas["width"], canvas["height"]
    lint_gate(proj, getattr(a, "force", False))
    fps = str(a.fps or canvas["fps"])
    scale = getattr(a, "scale", 1) or 1
    W, H = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
    bitrate = a.bitrate or {"draft": "4M", "standard": "10M", "high": "16M"}[(a.quality or "standard")]
    lufs, tp = r["audio"]["lufs"], r["audio"]["true_peak_max"]
    d = LIB / "成品" / project_brand(proj, getattr(a, "brand", None)) / proj.name / a.platform; d.mkdir(parents=True, exist_ok=True)
    base = proj.name.split("-", 1)[-1]
    vs = [int(m.group(1)) for f in d.glob(f"{base}_{a.platform}_v*.mp4") if (m := re.search(r"_v(\d+)\.mp4$", f.name))]
    v = a.version or 1 + max(vs or [0])
    code = getattr(a, "code", None)
    if code:
        brand_now = project_brand(proj, getattr(a, "brand", None))
        want = "PS" if brand_now == "品硕" else "HH"
        if not code_ok(brand_now, code):
            die(f"内容编号应为 {want}-平台-日期-序号（如 {want}-DY-20261111-01），收到 {code}")
    out = d / (f"{code}_{a.platform}_v{v}.mp4" if code else f"{base}_{a.platform}_v{v}.mp4")
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps}"
    if not re.search(r"(PS|HH)-", base): log("提醒：文件名不带内容编号（PS-/HH-平台-日期-序号），发布前补上")
    log("响度测量 …")
    m = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    j = last_json_block(m)
    if not j:
        die("响度测量失败：ffmpeg 没给出 loudnorm JSON（源片可能没有音轨）")
    ln = (f"loudnorm=I={lufs}:TP={tp}:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
          f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,aresample=48000")
    ffmpeg("-i", src, "-vf", vf, "-af", ln, "-c:v", "h264_videotoolbox", "-b:v", bitrate, "-maxrate", str(int(bitrate[:-1]) * 2) + "M", "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", 48000, "-movflags", "+faststart", out)
    cover = d / "封面.png"
    if not cover.exists(): ffmpeg("-ss", a.cover_at, "-i", out, "-frames:v", 1, cover)
    txt = d / "文案.txt"
    if not txt.exists(): txt.write_text("标题：\n\n正文：\n\n话题：\n", encoding="utf-8")
    rep = qc(out); (d / "审片").mkdir(exist_ok=True)
    (d / "审片" / f"{out.stem}.qc.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out)

def qc(p):
    info = probe(p)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if v is None:  # 纯音频（配音稿、音乐）也能审
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
        v = {"width": None, "height": None, "r_frame_rate": None, "codec_name": a.get("codec_name")}
    m = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", m); P = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", m)
    size = f"{v['width']}x{v['height']}" if v.get("width") else "audio-only"
    rep = {"file": Path(p).name, "size": size, "fps": v.get("r_frame_rate"), "codec": v["codec_name"],
           "duration": round(float(info["format"]["duration"]), 2), "MB": round(int(info["format"]["size"]) / 1e6, 1),
           "LUFS": float(I[-1]) if I else None, "truePeak": float(P[-1]) if P else None}
    a_ = rules()["audio"]
    rep["ok"] = bool(rep["LUFS"] is not None and abs(rep["LUFS"] - a_["lufs"]) <= a_["lufs_tolerance"]
                     and (rep["truePeak"] if rep["truePeak"] is not None else -99) <= -0.5)
    log("QC", json.dumps(rep, ensure_ascii=False)); return rep

def cmd_qc(a): print(json.dumps(qc(a.input), ensure_ascii=False))

REMOTION = LIB / "素材" / "模板" / "remotion-竖屏包装"

def cmd_pack(a):
    """【弃用】旧 Remotion 包装模板，仅留作对照；新片头/参数卡用 mf shot。"""
    import shutil
    src = Path(a.input).resolve(); pub = REMOTION / "public"; pub.mkdir(exist_ok=True)
    tmp = pub / f"in_{uuid.uuid4().hex[:6]}{src.suffix}"; shutil.copy(src, tmp)
    props = {"video": tmp.name, "durationSec": round(duration(src), 2), "title": a.title, "subtitle": a.subtitle,
             "price": "", "priceAt": 0, "cta": a.cta, "accent": a.accent}
    out = (Path(a.output) if a.output else src.with_name(src.stem + "_包装" + src.suffix)).resolve()
    try:
        log("Remotion 渲染 …"); t0 = time.time()
        run(["pnpm", "exec", "remotion", "render", "src/index.ts", "Vertical", out, "--props", json.dumps(props, ensure_ascii=False),
             "--codec", "h264", "--crf", "18", "--log", "error"], cwd=REMOTION)
        log(f"完成 {time.time()-t0:.1f}s")
    finally:
        tmp.unlink(missing_ok=True)
    print(out)

def cmd_dub(a):
    """一键：识别 → 翻译 → 配音 → 分离伴奏 → 混音 → 导出（字幕留 D剪 做）"""
    proj = project_dir(a.project); src = Path(a.input).resolve(); s = src.stem
    me = [sys.executable, __file__]
    def step(*args):
        log("▶ mf", *[str(x) if len(str(x)) < 60 else Path(str(x)).name for x in args[:2]])
        out = subprocess.run(me + [str(x) for x in args], text=True, stdout=subprocess.PIPE)
        if out.returncode: sys.exit(out.returncode)
        return out.stdout.strip().splitlines()[-1]
    srt = proj / "识别" / f"{s}.srt"
    if not srt.exists() or a.force: srt = Path(step("asr", src, "-p", proj, *(["--lang", a.src_lang] if a.src_lang else [])))
    tsrt = proj / "识别" / f"{s}.{a.to}.srt"
    if not tsrt.exists() or a.force: tsrt = Path(step("translate", srt, "--to", a.to, "-o", tsrt))
    dub = proj / "配音" / f"{s}.{a.to}.dub.wav"
    step("tts", tsrt, "--lang", a.to, "-o", dub, "--length", duration(src), *(["--voice", a.voice] if a.voice else []))
    bgm = proj / "识别" / f"{s}_伴奏.wav"
    if not a.no_bgm and (not bgm.exists() or a.force): step("sep", src, "-p", proj)
    mixed = proj / "剪辑" / f"{s}.{a.to}.配音.mp4"
    step("mix", src, dub, *(["--bgm", bgm] if not a.no_bgm else []), "-o", mixed)
    # 字幕只在 D剪 做（剪辑规范 §3）：翻译稿留在 识别/，去 D剪 导入校对，不烧录
    if not a.no_subs: log(f"字幕稿 {tsrt.name} 已就绪 → 在 D剪 里导入校对（mf 不烧字幕）")
    print(step("export", mixed, "-p", proj, "--platform", plat(a.platform)))

# ---------- 拆片（crv）：看片用，转录仍走 mf asr ----------
def cmd_watch(a):
    """抽帧看片（crv → frames + 九宫格）。转录不在 Mac 上跑。"""
    if not CRV_BIN.exists(): die(f"crv 没装好：{CRV_BIN}")
    out = Path(a.out).expanduser() if a.out else (project_dir(a.project) / "拆片" if a.project else Path.cwd() / "拆片")
    out.mkdir(parents=True, exist_ok=True)
    cmd = [CRV_BIN, a.src, "--grid"]
    if not a.transcribe: cmd.append("--no-transcribe")
    if a.from_sec is not None: cmd += ["--from", str(a.from_sec)]
    if a.to_sec is not None: cmd += ["--to", str(a.to_sec)]
    if a.adaptive: cmd.append("--adaptive")
    log("crv 抽帧 …"); t0 = time.time()
    r = subprocess.run(cmd, cwd=out, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode: die(f"crv 失败：{(r.stderr or r.stdout)[-1500:]}")
    d = out / "crv-out"
    frames = sorted((d / "frames").glob("*")) if (d / "frames").exists() else []
    grids = sorted((d / "grids").glob("*.jpg")) if (d / "grids").exists() else []
    log(f"完成 {time.time() - t0:.1f}s")
    print(f"拆片 → {d}\n帧 {len(frames)} 张 · 九宫格 {len(grids)} 张（read_image 直读九宫格最快）")
    for g in grids: print(g)
    print("要文字稿跑 mf asr（Windows 4080），不在本机 whisper")

# ---------- 片头/参数卡/封面（Multiplane）----------
def mp_render(a, shot, root, extra):
    cmd = ["npx", "multiplane"] + extra
    r = subprocess.run(cmd, cwd=MULTIPLANE, capture_output=True, text=True)
    if r.returncode: die(f"Multiplane 失败：{(r.stderr or r.stdout)[-1500:]}")
    return r

def _chars(text):
    """把 CTA 文案包成逐字 span（方便打字机）；<br>/换行分段，*星号* 裹的是强调色。"""
    lines = re.split(r"<br\s*/?>|\n", text or "")
    out = []
    for ln in lines:
        buf, accent = [], False
        for ch in ln:
            if ch == "*": accent = not accent; continue
            esc = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}.get(ch, ch)
            style = ' style="color:var(--accent)"' if accent else ""
            buf.append(f'<span class="ch"{style}>{esc}</span>')
        out.append('<div class="line">' + "".join(buf) + "</div>")
    return "".join(out)

def tpl_html(name, sets):
    """读模板并替换 {{KEY}}；endcard 的 CTA 自动拆成逐字动画。"""
    src = TPL_DIR / f"{name}.html"
    if not src.exists():
        have = ", ".join(sorted(x.stem for x in TPL_DIR.glob("*.html"))) or "无"
        die(f"没有模板 {name}（有：{have}）")
    r = rules(); cta = r["cta"]["cn"]
    ctx = {"BRAND": sets.get("BRAND", ""), "KICKER": sets.get("KICKER", ""), "TITLE": sets.get("TITLE", ""),
           "SUB": sets.get("SUB", ""), "FOOT": sets.get("FOOT", ""),
           "K1": sets.get("K1", ""), "V1": sets.get("V1", "0"), "U1": sets.get("U1", ""),
           "K2": sets.get("K2", ""), "V2": sets.get("V2", "0"), "U2": sets.get("U2", ""),
           "K3": sets.get("K3", ""), "V3": sets.get("V3", "0"), "U3": sets.get("U3", ""),
           "NOTE": sets.get("NOTE", "样品寄到厂里，工程师看过再给方案"),
           "CTA": cta if name != "endcard" else _chars(sets.get("CTA", cta))}
    for k, v in sets.items(): ctx.setdefault(k, v)
    html = src.read_text(encoding="utf-8")
    # 未替换的占位符一律清空，避免画面上出现 {{X}}
    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: ctx.get(m.group(1), ""), html)

def cmd_shot(a):
    """Multiplane 出片头/结尾/参数卡几秒画面，再作为素材进 D剪。"""
    if not MULTIPLANE.exists(): die(f"Multiplane 没装好：{MULTIPLANE}")
    if getattr(a, "template", None):
        sets = dict(kv.split("=", 1) for kv in (getattr(a, "sets", None) or []) if "=" in kv)
        gen = MP_SHOTS / "_gen"; gen.mkdir(parents=True, exist_ok=True)
        shot = gen / f"{a.template}-{dt.datetime.now():%Y%m%d-%H%M%S}.html"
        shot.write_text(tpl_html(a.template, sets), encoding="utf-8")
        a.shot, a.root = str(shot), str(MP_SHOTS)
        if not a.output: a.output = str(MP_SHOTS / "_out" / (shot.stem + ".mp4"))
    shot = Path(a.shot).expanduser()
    root = Path(a.root).expanduser() if a.root else (MP_SHOTS if shot.exists() and MP_SHOTS in shot.parents else shot.parent)
    if not shot.exists():
        cand = (root if root.is_absolute() else Path.cwd() / root) / a.shot
        if cand.exists(): shot = cand
        else: die(f"找不到画面文件 {a.shot}（根目录 {root}）")
    root = root if root.is_dir() else shot.parent
    rel = os.path.relpath(shot.resolve(), root.resolve())
    out = Path(a.output).expanduser() if a.output else shot.with_name(shot.stem + ".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    extra = ["render", rel, "--root", str(root), "--out", str(out), "--quality", a.quality]
    if a.motion_blur: extra.append("--motion-blur")
    if a.scale: extra += ["--scale", str(a.scale)]
    if a.fps: extra += ["--fps", str(a.fps)]
    log("Multiplane 渲染 …"); t0 = time.time()
    mp_render(a, shot, root, extra)
    log(f"完成 {time.time() - t0:.1f}s")
    if a.project: print(dj_import(dj_pid(project_dir(a.project)), [out]))
    print(out)

def cmd_cover(a):
    """封面静帧：Multiplane stills → 封面尺寸（小红书 3:4 1080×1440）。"""
    if not MULTIPLANE.exists(): die(f"Multiplane 没装好：{MULTIPLANE}")
    r = rules(); kind = {"xhs": "cover_34", "douyin": "vertical", "tiktok": "vertical"}.get(a.platform, "vertical")
    cw, ch = r["canvas"][kind][:2]
    shot = Path(a.shot).expanduser()
    root = Path(a.root).expanduser() if a.root else (shot.parent if shot.exists() else MP_SHOTS)
    if not shot.exists():
        cand = root / a.shot
        if not cand.exists(): die(f"找不到画面文件 {a.shot}")
        shot = cand
    rel = os.path.relpath(shot.resolve(), root.resolve())
    tmp = Path(tempfile.mkdtemp()) / "stills"
    mp_render(a, shot, root, ["stills", rel, "--root", str(root), "--at", str(a.at), "--out", str(tmp)])
    pngs = sorted(tmp.glob("t-*.png"))
    if not pngs: die("Multiplane 没产出静帧")
    out = Path(a.output).expanduser() if a.output else shot.with_name(f"{shot.stem}-封面{cw}x{ch}.png")
    ffmpeg("-i", pngs[0], "-vf", f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch}", out)
    print(out)


def main():
    p = argparse.ArgumentParser(prog="mf", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    def add(name, fn, help_):
        x = sp.add_parser(name, help=help_); x.set_defaults(fn=fn); return x
    x = add("new", cmd_new, "新建工程（建目录 + D剪 项目 + 设画布 + 可选导入素材）"); x.add_argument("name"); x.add_argument("-b", "--brand", required=True, help="品硕/晖华（ps/hh）"); x.add_argument("--platform", default="dy", help="平台短码：dy/sph/ks/xhs/tk/yt/li（也认 douyin/tiktok…），默认 dy 竖屏"); x.add_argument("--import", dest="import_from", help="建完直接把这个文件/目录导入 D剪（>512MB 自动切段）"); x.add_argument("--kind", required=True, choices=["film", "raw"], help="剪前判定：film=成片（只加字幕+TTS，保持原片风格）/ raw=素材（按成品风格剪）——规范 §0")
    x = add("verify", cmd_verify, "剪后复验（规范 §10）：QC/音轨数/抽帧，--lang 时做语音回读"); x.add_argument("input"); x.add_argument("-p", "--project"); x.add_argument("--lang", help='回读语言全名：Chinese/Thai/Hindi/Indonesian/Vietnamese…'); x.add_argument("--frames", type=int, default=10); x.add_argument("-o", "--out")
    x = add("lint", cmd_lint, "文案合规检查：绝对化/联系方式/报价/禁用词（也可 -p 查整个工程时间线）"); x.add_argument("files", nargs="*"); x.add_argument("-t", "--text"); x.add_argument("-p", "--project")
    add("health", cmd_health, "检查 GPU / ollama / D剪 / Multiplane / crv / 规则")
    x = add("dj", cmd_dj, "D剪：check 确认单 / new 建项目 / import 导入素材 / bind 绑定当前会话 / prune 清空项目"); x.add_argument("action", choices=["check", "new", "import", "bind", "prune", "up", "down", "status"]); x.add_argument("project", nargs="?"); x.add_argument("files", nargs="*"); x.add_argument("--session", help="会话 id，默认取 DSH_SESSION_ID"); x.add_argument("--yes", action="store_true"); x.add_argument("--platform", default="dy")
    x = add("watch", cmd_watch, "拆片看图（crv 抽帧+九宫格，转录走 mf asr）"); x.add_argument("src"); x.add_argument("-p", "--project"); x.add_argument("-o", "--out"); x.add_argument("--from", dest="from_sec", type=float); x.add_argument("--to", dest="to_sec", type=float); x.add_argument("--adaptive", action="store_true"); x.add_argument("--transcribe", action="store_true", help="也转录（Mac CPU，很慢，一般不要）")
    x = add("shot", cmd_shot, "Multiplane 出片头/参数卡/结尾几秒画面（竖屏）；--template title|params|endcard 直接用模板"); x.add_argument("shot", nargs="?"); x.add_argument("-t", "--template", choices=["title", "params", "endcard"], help="用 shots/ 里的模板"); x.add_argument("--set", dest="sets", action="append", metavar="K=V", help="模板变量，如 --set TITLE=视觉检测机"); x.add_argument("--root"); x.add_argument("--quality", default="high"); x.add_argument("--motion-blur", action="store_true"); x.add_argument("--scale", type=float); x.add_argument("--fps", type=int); x.add_argument("-p", "--project"); x.add_argument("-o", "--output")
    x = add("cover", cmd_cover, "封面静帧（小红书 3:4 1080×1440）"); x.add_argument("shot"); x.add_argument("--root"); x.add_argument("--at", type=float, default=0); x.add_argument("--platform", default="xhs"); x.add_argument("--quality", default="high"); x.add_argument("--motion-blur", action="store_true"); x.add_argument("--scale", type=float); x.add_argument("--fps", type=int); x.add_argument("-o", "--output")
    x = add("asr", cmd_asr, "GPU 语音识别 → 识别/<名>.srt/.json"); x.add_argument("input"); x.add_argument("-p", "--project"); x.add_argument("--lang"); x.add_argument("--model"); x.add_argument("--prompt")
    x = add("sep", cmd_sep, "GPU 人声/伴奏分离 → 识别/<名>_人声.wav _伴奏.wav"); x.add_argument("input"); x.add_argument("-p", "--project")
    x = add("translate", cmd_translate, "字幕翻译（Windows ollama）"); x.add_argument("input"); x.add_argument("--to", required=True); x.add_argument("-o", "--output"); x.add_argument("--note", help="额外要求，如术语表")
    x = add("tts", cmd_tts, "Edge TTS 配音（srt 自动按时间轴对齐）"); x.add_argument("input"); x.add_argument("--lang"); x.add_argument("--voice"); x.add_argument("--rate", default="+0%"); x.add_argument("--length", type=float); x.add_argument("-o", "--output")
    x = add("sovits", cmd_sovits, "GPT-SoVITS 克隆音色配音（GPU）"); x.add_argument("input", help="文本 txt"); x.add_argument("--ref", required=True, help="参考音频 3-10s"); x.add_argument("--ref-text"); x.add_argument("--lang", default="zh"); x.add_argument("--speed", type=float, default=1.0); x.add_argument("-p", "--project"); x.add_argument("-o", "--output")
    x = add("scenes", cmd_scenes, "镜头切分点检测"); x.add_argument("input"); x.add_argument("--threshold", type=float, default=27); x.add_argument("-p", "--project"); x.add_argument("-o", "--output")
    x = add("cut-silence", cmd_cut_silence, "去掉静音段（口播粗剪）"); x.add_argument("input"); x.add_argument("--noise", type=int, default=-35); x.add_argument("--min", type=float, default=0.6); x.add_argument("--pad", type=float, default=0.12); x.add_argument("-o", "--output")
    x = add("mix", cmd_mix, "配音 + 背景音混合替换音轨"); x.add_argument("video"); x.add_argument("voice"); x.add_argument("--bgm"); x.add_argument("--voice-gain", type=float, default=0); x.add_argument("--bgm-gain", type=float, default=-4); x.add_argument("-o", "--output")
    x = add("export", cmd_export, "导出到 成品/<品牌>/<工程>/<平台>/（-14 LUFS、封面、文案模板、QC）"); x.add_argument("input"); x.add_argument("-p", "--project"); x.add_argument("-b", "--brand"); x.add_argument("--platform", default="dy", help="dy/sph/ks/xhs/tk/yt/li（也认 douyin/tiktok…）"); x.add_argument("--version", type=int); x.add_argument("--fps"); x.add_argument("--bitrate"); x.add_argument("--quality", choices=["draft", "standard", "high"], default="standard", help="bitrate 档位 4M/10M/16M"); x.add_argument("--scale", type=float, default=1, help="尺寸缩放，0.5=半幅"); x.add_argument("--code", help="内容编号 PS/HH-平台-日期-序号，写进去就按它命名"); x.add_argument("--cover-at", default="1"); x.add_argument("--force", action="store_true", help="带着合规违规也导出（不推荐）")
    x = add("pack", cmd_pack, "【弃用】旧 Remotion 包装模板（改用 mf shot；片头/参数卡走剪辑规范 §7）"); x.add_argument("input"); x.add_argument("--title", default=""); x.add_argument("--subtitle", default=""); x.add_argument("--cta", default="发样品照片/图纸，免费评估方案"); x.add_argument("--accent", default="#FF3B5C"); x.add_argument("-o", "--output")
    x = add("qc", cmd_qc, "审片检查：分辨率/时长/响度/峰值"); x.add_argument("input")
    x = add("dub", cmd_dub, "一键多语种翻配：识别→翻译→配音→伴奏→混音→字幕→导出"); x.add_argument("input"); x.add_argument("--to", required=True); x.add_argument("-p", "--project"); x.add_argument("--src-lang"); x.add_argument("--voice"); x.add_argument("--platform", default="tk", help="dy/sph/ks/xhs/tk/yt/li（也认 douyin/tiktok…）"); x.add_argument("--no-bgm", action="store_true"); x.add_argument("--no-subs", action="store_true"); x.add_argument("--force", action="store_true")
    a = p.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
