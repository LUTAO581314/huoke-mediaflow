# huoke-mediaflow

品硕 / 晖华获客的**内容生产 + AI 剪辑**仓库：`mf` 命令行、剪辑规则、模板、引擎补丁、Windows 端脚本。

素材在 Mac，重活（识别、配音、抠图）经 SSH 交给 Windows `l-l` 的 4080 跑。

## 先说清楚：这套东西由三个部分组成

| 组成 | 是什么 | 装在哪 |
|---|---|---|
| **`mf`** | 本仓库的 `mf.py`，Python **单文件**（只用标准库）：预处理、质检、导出、片卡、拆片看图 | Mac，`~/mediaflow/mf.py` |
| **D剪 引擎** | 开源项目 `DSHL-DeepPack-Jian` + 本仓库两个补丁：时间线、字幕、原生元素、Remotion 渲染 | Mac，`~/mediaflow/djian`，端口 **5180** |
| **DSH** | 宿主应用：右侧剪辑面板和 `djian_*` 工具由它提供 | Mac，官方桌面端 |

> **AI 助手先读 [`AGENTS.md`](AGENTS.md)：第一步是 `bash scripts/check-env.sh --json`，不许在本机装 ollama / whisper / TTS 模型。**
>
> **只 clone 这个仓库是跑不起来的**：仓库里没有剪辑内核。必须按 [`docs/安装与复现.md`](docs/安装与复现.md) 把 D剪 上游 clone 下来、打补丁、并把 6 个 `@djian/*` 包 `link:` 进 DSH profile。
> 想看每个引擎具体是什么、版本、能不能替换，看 [`docs/架构与引擎.md`](docs/架构与引擎.md)。

## 环境要求（实测版本，别用更低的）

| 依赖 | 版本 | 说明 |
|---|---|---|
| macOS | 13+（Apple Silicon） | 实测 26.6.2 / arm64 |
| Node.js | **≥ 22.18**（实测 24.21.0） | D剪 引擎硬要求 |
| Python | **≥ 3.12**（实测 3.12.16） | 系统自带 3.9 不够 |
| ffmpeg / ffprobe | 9.0.2 | 必须在 PATH |
| yt-dlp | 2025.10.14 | 下源片 |
| D剪 上游 | `e1b6130`（2.1.3）+ 两个补丁 | Remotion 4.0.526 |
| @djian/* 6 个包 | 0.2.0 | **不在 npm**，本地 link |
| Multiplane | 0.3.13 + Chromium | 片头卡/参数卡/封面 |
| crv | pip（venv） | 拆片看图（可选） |
| GPU 从机 | Windows + NVIDIA，faster-whisper / demucs / ollama | 识别、配音（可选） |

## 先跑环境体检

```bash
bash scripts/check-env.sh     # 缺什么、版本够不够，一条命令看完；不改任何东西
mf health                     # 装好之后再用这个（检查 GPU / D剪 / Multiplane / crv / 规则）
```

`check-env.sh` 会逐个验证：二进制与版本、三个目录、规则文件与 §9 参数块、`mf` 是否在 PATH、**引擎是否在线**、上游源码是否存在、`session-binding` 补丁是否已打、DSH 的 6 个 link 是否齐全、Multiplane/Playwright/crv、SSH 从机。全绿再动手。

## 常用命令

```bash
mf health                                   # 环境体检（GPU / ollama / D剪 / Multiplane / crv / 规则）
mf new 视觉检测-三班倒 -b 品硕 --platform dy  # 建工程 + D剪 项目 + 把当前会话绑上去
mf dj check 视觉检测-三班倒                  # 开剪前确认单
mf dj import <工程> <文件…>                  # 追加素材（>512MB 自动切段）
mf asr / translate / tts / sep / mix        # 预处理（走 Windows GPU）
mf watch <链接|文件>                         # 拆片看图（crv，出九宫格）
mf shot -t title  --set TITLE=三个质检员三班倒 --set KICKER=机器视觉检测   # 模板出片头
mf shot -t params --set K1=检测精度 --set V1=0.05 --set U1=mm              # 参数卡（数字滚动）
mf shot -t endcard --set CTA="发图纸<br>*免费评估*"                          # 结尾引导（打字机）
mf shot <shot.html>                         # 也可以直接给现写的 shot.html
mf cover <shot.html> --at 0.5               # 封面 3:4 1080×1440
mf export <母版> -p <工程> --platform dy --code PS-DY-20261111-01 --quality high
mf qc <文件>                                # 分辨率 / 时长 / 响度 / 峰值
mf dj bind <工程>                            # 手动把当前会话指到某个 D剪 项目
mf dj prune [--yes]                         # 清空项目（进回收站，可恢复）
mf dj status | up | down                    # 引擎谁在跑、起一个、收掉一个（日志 ~/.djian/logs/engine.log）
mf lint -t "文案…"  / mf lint 文案.txt / mf lint -p <工程>   # 合规硬拦截（违规退 1）
```

规则全部读 `剪辑规范.md` 的 §9 机器参数块：画布、时长、镜头长度、转场上限、字幕字号与留白、配乐音量、响度、编号格式、禁用词。**改规则只改那个文件**，`mf` 和 D剪 的下一次调用就生效。

## 合规（写死在规则里，改代码前先读）

- 品牌隔离：一个工程只用一个品牌的素材，两品牌不互相导流；
- 画面不留电话 / 微信 / 二维码 / 邮箱 / 网址；
- 不报价、不承诺交期和参数；不用绝对化用语；
- AI 生成画面或配音，结尾加小字标识并提醒发布时勾选平台 AI 声明；
- 字幕只在 D剪 做，不在 `mf` 里烧。

## 硬拦截（不是提醒，是拦住）

`huoke_lint.py` 查四类：联系方式、报价/交期、绝对化用语、规范里的禁用词。两处闸门：

- `mf dj check <工程>`：开剪前体检，有问题直接退 1；
- `mf export …`：成片前最后一道闸，不合规不出片（确需强出加 `--force`，会告警）。

## 测试

```bash
MF_RULES=$PWD/docs/剪辑规范.md python -m pytest -q        # 52 条
DJIAN_SRC=~/mediaflow/djian node --import ./tests/engine/loader.mjs \
  --test tests/engine/store.test.mjs                     # 引擎集成（本地跑真引擎源码）
```

CI（`.github/workflows/ci.yml`）三个 job：

| job | 跑什么 |
|---|---|
| `unit` | CLI 冒烟 + 规则/别名/画布/编号/品牌隔离 + 合规拦截 + 模板占位符 |
| `engine` | clone 上游 D剪 → 打 `engine/patches/djian-session-binding.patch` → 跑真 `store.mjs` 的会话绑定测试（同名空项目复用 / 显式绑定 / 空项目判定） |
| `audio` | 真 ffmpeg：正弦音 → loudnorm 到 -14 LUFS → `mf qc` 读数校验 |

引擎补丁测试用 `tests/engine/stubs/` 顶替 `engine/dist/*`（CI 不装 remotion，也能测我们改的那段逻辑）。

## 内容生产（`content/`）

选题与文案不走代码，走模板 + 知识库：

```
content/brands/pinsontec/     品硕素材清单与口径（图片/视频/参数只放清单，不放原始大文件）
content/brands/smarthuihua/   晖华同上
content/calendar/             选题日历（一条选题一行：品牌/平台/角度/状态/编号）
content/scripts/              脚本与分镜模板
content/knowledge/            指向 ~/获客平台/知识库/ 的索引，不复制正文
```

素材本体和成片不进 git（在 `~/媒体库`，3.4G）；这里只存清单、日历、脚本。

## 引擎补丁（`engine/patches/`）

| 补丁 | 改什么 | 为什么 |
|---|---|---|
| `djian-session-binding.patch` | `store.mjs` / `routes.mjs` / `engine-client.js` | 同名空项目复用、显式 `bindSessionTo`、会话缓存 —— 治「每个新会话多一个空 D剪 项目」 |
| `djian-desktop-shell.patch` | `http.mjs` / `client-timeline` | 桌面端渲染页是 `dsh-app://`（非 http），放开 origin 白名单并把引擎指回本机回环 |

两个补丁都钉在 `ENGINE_REF=e1b6130`（D剪 2.1.3）。CI 的 `engine` job 按这个 ref 拉上游、打两个补丁、跑真 `store.mjs`；另有一个**不拦截**的漂移探测：上游 HEAD 上失配会打印 ⚠️，升级 D剪 前先看它。

## 目录约定

```
~/媒体库/工程/<日期>-<名称>/{识别,配音,剪辑,包装}   # 一选题一个工程（mf new 建）
~/媒体库/成品/<品牌>/<工程>/<平台>/                  # 成片与封面
~/获客平台/知识库/剪辑规范.md                        # 唯一规则源
~/.djian/projects/<pid>/                            # D剪 项目（时间线 JSON + 素材副本）
```

## 其他文件

- `AGENTS.md` — 给 AI 助手的铁律（先体检、禁止本机装 GPU 模型、改动流程）；
- `docs/安装与复现.md` — **从零安装到出第一条片**（含 DSH 接入、常见错误排查）；
- `docs/架构与引擎.md` — 三层架构、每个引擎的版本/端口/产物/可替换性、已知边界；
- `scripts/check-env.sh` — 环境体检脚本；
- `djian-bundle/` — D剪 预设（`cordis.patch.yml`，含「获客项目先读剪辑规范」的人设）与插件入口；
- `windows/` — GPU 端：`worker.py`（识别/分离/合成）与两个安装脚本；
- `docs/djian-adapter.md` — D剪 与 `mf` 怎么接的；`docs/剪辑规范.md` — 规则副本（CI 用）。
