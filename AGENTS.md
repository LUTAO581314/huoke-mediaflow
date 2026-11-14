# AGENTS.md — 给 AI 助手的铁律

这份文件写给**任何要在这台机器上复现或维护这套剪辑环境的 AI**（DSH / Claude / Codex / Cursor 都算）。
人类读者请直接看 [`docs/安装与复现.md`](docs/安装与复现.md)。

## 第 0 条：先体检，再动手

```bash
bash scripts/check-env.sh --json        # macOS / Linux
python scripts/check-env.py --json      # Windows（同一套检查）
```

- 返回 `{"ok":..,"fail":..,"issues":[..],"next":[..]}`；
- **按 `next` 数组的顺序一项一项补**，`issues` 为空就说明环境齐了、可以干活；
- 不允许跳过体检直接 `npm install` / `brew install` / `pip install`；
- 缺的是 Mac 侧工具（ffmpeg/node/引擎/multiplane/crv）时，可以跑 `bash scripts/bootstrap.sh --yes` 补；
  这个脚本**只装 Mac 工具，不装任何模型**。

## 第 1 条：不要在 Mac 上装这些

| 不要装 / 不要跑 | 它该在哪 | 为什么 |
|---|---|---|
| `ollama`、任何 LLM 权重 | Windows `C:\mediagpu`（ssh `l-l`） | Mac 上跑不了 14B 模型，白下几十 GB |
| `faster-whisper` / `whisper.cpp` / `openai-whisper` | 同上 | Mac 无 CUDA，转录慢到不可用 |
| `GPT-SoVITS`、TTS 模型权重 | 同上 | 需要 GPU |
| `torch` / CUDA 相关包 | 同上 | 本仓库 `mf.py` 只用标准库 |
| 示例视频、示例音频、测试素材包 | 不需要 | 用户有自己的素材，别下载 |

`mf asr / translate / tts / sep / sovits` 这些命令**本身就是远程调用**，本机不需要装任何模型。

## 第 2 条：装任何东西都要先说明

装之前必须告诉用户三件事：**装什么、为什么需要、多大体积**，得到同意再装。
不要"我先把依赖装上再说"。

## 第 3 条：判断"能不能剪片"的唯一标准

```
check-env.sh 里这几项全绿：
  引擎在线 http://127.0.0.1:5180
  上游源码 ~/mediaflow/djian
  session-binding 补丁已打
  DSH 已 link @djian（6 个）
```

少任何一项，面板里就是"没有剪辑能力"。这时**唯一该做的事**是把 D剪 装好，而不是去找别的剪辑方案替代。

## 第 4 条：不要碰的东西

- **`~/.djian/projects/` 是用户的时间线**。要清空项目只能用 `mf dj prune`（进回收站可恢复），不要直接删目录。
- **`~/mediaflow/` 是引擎与工具链本体**。删改前先 `tar czf ~/获客平台/归档/mediaflow-$(date +%Y%m%d).tar.gz -C ~ mediaflow`；丢了先看归档，别急着重装（见 `docs/安装与复现.md` 末节）。
- **`~/媒体库/` 是用户的素材库**（3.4G 真实素材）。不要删、不要移、"整理"前先问。
- **`engine/patches/` 钉在上游 `e1b6130`**。不要顺手把上游升到新版本——补丁会失配，CI 会红。
- **规则只有一份**：`~/获客平台/知识库/剪辑规范.md`。不要在代码里硬编码画布/字号/响度，也不要自己另建一份规则。

## 第 5 条：每条片先判定「成片 / 素材」，剪完必须复验

- 开工第一件事：`mf new <名称> -b 品牌 --kind film|raw`（必填，写进工程 README）。
  `film` = 成片：**不重剪、不改画面、不加特效**，只加目标语字幕 + TTS 配音，保持原片风格；
  `raw` = 素材：按 `剪辑规范.md` §1–§3 的成品风格剪。
- 剪完跑 `mf verify <成片> [--lang Thai|Indonesian|Vietnamese|Chinese]`：QC 指标、音轨数必须 1、
  抽帧看片、可选语音回读（ASR 与稿子比对）。规范 §10 的六项没全过，不算交付。

## 第 6 条：改动流程

- 不要直接推 `main`：开分支 → PR → 等 CI 三个 job 绿 → 合并；
- 改剪辑规则（`剪辑规范.md`）先给用户看 diff；
- 改 `mf.py` 要让 `MF_RULES=$PWD/docs/剪辑规范.md python -m pytest -q` 通过（52 条）；
- 动 `engine/patches/` 要同时跑 `node --import ./tests/engine/loader.mjs --test tests/engine/store.test.mjs`。

## 第 7 条：报错先查表

`docs/安装与复现.md` 的「常见错误」有 11 条对照（`403 CLIENT_HEADER_REQUIRED`、`shot_not_found`、`找不到剪辑规范`、引擎连不上、空项目堆积、peer 冲突、Node 太旧、CPU 转录慢、ollama 超时、512MB 上限、导出被拦）。
先对表，再决定要不要改代码。

## 第 8 条：合规是硬约束，不是建议

出片前必过 `mf dj check`（开剪前）和 `mf export`（成片前）两道闸。四条红线：品牌隔离、画面无联系方式、不报价不承诺交期、不用绝对化用语。
闸门拦住时**改文案**，不要用 `--force` 绕过（除非用户明确要求）。
