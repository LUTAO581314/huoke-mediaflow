# huoke-mediaflow

品硕 / 晖华获客的**内容生产 + AI 剪辑**仓库：`mf` 命令行、剪辑规则、模板、引擎补丁、Windows 端脚本。

素材在 Mac，重活（识别、配音、抠图）经 SSH 交给 Windows `l-l` 的 4080 跑。

- 时间线剪辑、字幕、原生元素在 **D剪** 面板里做（`djian_*` 工具）；
- `mf` 负责预处理、质检、导出、片头片卡、拆片看图；
- 两边共用同一份规则：`~/获客平台/知识库/剪辑规范.md`（本仓库 `docs/剪辑规范.md` 是副本，只用于测试与对照）。

## 常用命令

```bash
mf health                                   # 环境体检（GPU / D剪 / Multiplane / crv / 规则）
mf new 视觉检测-三班倒 -b 品硕 --platform dy  # 建工程 + D剪 项目 + 把当前会话绑上去
mf dj check 视觉检测-三班倒                  # 开剪前确认单
mf dj import <工程> <文件…>                  # 追加素材（>512MB 自动切段）
mf asr / translate / tts / sep / mix        # 预处理
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
```

## 其他文件

- `djian-bundle/` — D剪 预设（`cordis.patch.yml`，含「获客项目先读剪辑规范」的人设）与插件入口；
- `windows/` — GPU 端：`worker.py`（识别/分离/合成）与两个安装脚本；
- `docs/djian-adapter.md` — D剪 与 `mf` 怎么接的；`docs/剪辑规范.md` — 规则副本（CI 用）。
