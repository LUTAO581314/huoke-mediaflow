# Windows 安装与复现

> AI 助手请先读仓库根的 [`AGENTS.md`](../AGENTS.md)。第一步永远是体检，不要先装东西。

这套东西在 Windows 上和 macOS 是**同一份代码**，差别只有三处：启动器（`mf.cmd` 代替 `~/.local/bin/mf`）、
体检脚本（`python scripts/check-env.py` 代替 `bash scripts/check-env.sh`）、以及素材库放在哪个盘（用 `MF_LIB` 指）。

---

## 第 0 步 · 先体检

```bat
python scripts\check-env.py --json
```

输出 `{"ok","fail","warn","issues","next"}`。**只补 `next` 里列的**，按顺序补。

### 绝对不要在这台机器上装这些（除非它就是 GPU 机）

| 不要装 | 说明 |
|---|---|
| 模型权重（ASR/LLM/TTS） | 只有 GPU 机才需要，见本节末尾「GPU 部分」 |
| `node_modules` 手动拷来拷去 | 一律用 `npm install`，版本差异会炸 Remotion |

---

## 1. 基础软件

用 winget（Win11 自带）：

```bat
winget install Gyan.FFmpeg
winget install yt-dlp.yt-dlp
winget install OpenJS.NodeJS.LTS
winget install Git.Git
winget install Python.Python.3.12
```

装完**关掉并重开**终端，然后确认：

```bat
ffmpeg -version
node -v            :: 需要 >= 22.18
npm -v
python --version   :: 需要 >= 3.10（本仓库只用标准库）
git --version
```

> `ffmpeg` 建议直接放 `C:\ffmpeg\bin` 并加进 PATH，避免 winget 装的版本路径漂移。

## 2. 放好目录

默认约定（可用环境变量改）：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MF_LIB` | `%USERPROFILE%\媒体库` | 素材库/工程/成品根目录，**建议指到空间大的盘**，如 `D:\媒体库` |
| `MF_HOME` | `%USERPROFILE%\mediaflow` | 运行时目录（`mf.py`、D剪 源码、tools） |
| `MF_RULES` | `%USERPROFILE%\获客平台\知识库\剪辑规范.md` | 唯一规则文件 |
| `MF_SHOTS` | `%MF_LIB%\素材\模板\multiplane` | 画面模板目录 |
| `DJIAN_API` | `http://127.0.0.1:5180` | 引擎地址 |

设一个长期变量（PowerShell，管理员不必要）：

```powershell
[Environment]::SetEnvironmentVariable("MF_LIB", "D:\媒体库", "User")
[Environment]::SetEnvironmentVariable("MF_HOME", "D:\mediaflow", "User")
```

建目录并放规则：

```bat
mkdir "%USERPROFILE%\获客平台\知识库"
copy docs\剪辑规范.md "%USERPROFILE%\获客平台\知识库\剪辑规范.md"
```

## 3. 拿 D剪 源码并打补丁

D剪 上游没有 LICENSE，**不能随包分发**，必须自己 clone：

```bat
mkdir "%MF_HOME%"
git clone https://github.com/Loliyer520/DSHL-DeepPack-Jian.git "%MF_HOME%\djian"
git -C "%MF_HOME%\djian" checkout e1b6130
git -C "%MF_HOME%\djian" apply engine\patches\djian-session-binding.patch
git -C "%MF_HOME%\djian" apply engine\patches\djian-desktop-shell.patch
cd /d "%MF_HOME%\djian" && npm install
```

`npm install` 会拉 Remotion，约 300MB，第一次要几分钟。

## 4. 把 D剪 接进 DSH

Windows 上没有软链习惯，**用绝对路径写在 profile 的 package.json 里**（和 macOS 一致的 6 条 `link:`），
具体 JSON 片段见 [`安装与复现.md`](安装与复现.md) 第 3 步；只是把 `/Users/xxx/...` 换成 `D:/mediaflow/...`（**正斜杠**）。

然后：

```bat
cd %USERPROFILE%\.dsh\profiles\desktop
npm install
```

## 5. mf 启动器

两种都可以：

```bat
:: A. 直接用仓库里的 mf.cmd（把仓库根加进 PATH 后，命令行里就能 mf new ...）
setx PATH "%PATH%;<仓库路径>"

:: B. 复制到自己的工具目录
copy mf.cmd "%USERPROFILE%\bin\mf.cmd"
```

`mf.cmd` 找 Python 的顺序：仓库同级 `.venv` → `%MF_HOME%\.venv` → `py -3` → `python`。

`%MF_HOME%\mf.py` 要指向仓库那份（用 `mklink` 或直接 copy）：

```bat
mklink "%MF_HOME%\mf.py" "<仓库路径>\mf.py"        :: 需要开发者模式或管理员
:: 或者
copy "<仓库路径>\mf.py" "%MF_HOME%\mf.py"
```

## 6. 画面模板与拆片工具

```bat
:: Multiplane（片头卡/参数卡/封面）
mkdir "%MF_HOME%\tools\multiplane"
cd /d "%MF_HOME%\tools\multiplane"
npm init -y
npm install multiplane@0.3.13 --legacy-peer-deps
npx playwright install chromium

:: crv（拆片看图，可选）
cd /d "%MF_HOME%"
python -m venv .venv
.venv\Scripts\pip install "claude-real-video[whisper]"
```

## 7. 起引擎、跑第一条

```bat
mf dj up                 :: 起 D剪 引擎（日志 %USERPROFILE%\.djian\logs\engine.log）
mf health                :: 全绿就可以剪
mf new 20261112-试片 -b 品硕 --platform dy
mf dj check              :: 开剪前合规体检
```

---

## GPU 部分（识别 / 翻译 / 配音 / 人声分离）

**只在 GPU 机上做**，剪辑机不装：

| 能力 | 引擎 | 命令 |
|---|---|---|
| 语音识别 | faster-whisper large-v3 | `mf asr` |
| 翻译 | ollama + qwen2.5:14b（需先手动起） | `mf translate` |
| 配音 | Edge TTS（在线，不装模型）/ GPT-SoVITS | `mf tts` / `mf sovits` |
| 人声分离 | demucs | `mf sep` |

`mf health` 会显示 GPU 机与 ollama 状态。ollama **不会开机自启**（用户规定），要翻译前手动运行 `C:\mediagpu\bin\ollama-serve.cmd`。

---

## 与 macOS 的差异清单

| 项目 | macOS | Windows |
|---|---|---|
| 体检 | `bash scripts/check-env.sh --json` | `python scripts\check-env.py --json` |
| 半自动安装 | `bash scripts/bootstrap.sh` | 目前按本文手装（脚本未提供） |
| mf 启动 | `~/.local/bin/mf`（bash） | `mf.cmd`（找 4 处 Python） |
| mf.py 位置 | 软链到仓库 | 软链（mklink）或 copy |
| 引擎拉起 | `start_new_session` | `DETACHED_PROCESS`（已在 mf.py 里分支） |
| 引擎停止 | `ps -p` 校验命令 | `tasklist /FI "PID eq"` |
| 素材库 | `~/媒体库` | `MF_LIB`，建议 `D:\媒体库` |

## 常见错误

| 现象 | 原因 / 处理 |
|---|---|
| `mf` 不是内部或外部命令 | `mf.cmd` 不在 PATH；用 `.\mf.cmd` 试，或 `setx PATH` 后重开终端 |
| `node -v` 版本低于 22.18 | 引擎起不来；用 `winget install OpenJS.NodeJS.LTS` 升级 |
| 引擎 15 秒没响应 | 看 `%USERPROFILE%\.djian\logs\engine.log`；多半是 `npm install` 没跑完 |
| `npm install` 报 ERESOLVE | `--legacy-peer-deps`（multiplane 的 three.js 依赖需要） |
| 中文路径报错 | 素材库与仓库路径尽量纯 ASCII，或确保系统区域设置为 UTF-8 |
| 长路径报错 | 启用 `LongPathsEnabled=1`（注册表 `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem`） |
| 导出时被合规闸门拦 | 改文案，不要用 `--force` 绕过 |
