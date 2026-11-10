# D剪 ↔ DSH NEXT 适配与接法

上游 D剪（[Loliyer520/DSHL-DeepPack-Jian](https://github.com/Loliyer520/DSHL-DeepPack-Jian)）以 submodule 挂在 `djian/`，**锁定提交，不 fork**。我们只在上面打两个补丁，补丁存在 `engine/patches/`。

## 补丁

| 补丁 | 文件 | 作用 |
|---|---|---|
| `djian-session-binding.patch` | `packages/webui/server/store.mjs`、`routes.mjs`、`packages/host-bridge/lib/engine-client.js` | 同名空项目复用、`bindSessionTo(sessionId, projectId)`、会话→项目缓存 2 秒 |
| `djian-desktop-shell.patch` | `packages/webui/server/http.mjs`、`packages/client-timeline/{src,lib}`、`packages/client-library/lib` | 桌面端渲染页是 `dsh-app://app`（非 http）：放开 origin 白名单，并把引擎基址指回 `127.0.0.1` |

**钉住的版本**：`ENGINE_REF=e1b6130`（D剪 2.1.3，本机实际在跑的）。两个补丁都在这个提交上 `git apply --check` 通过；CI 的 `engine` job 会按这个 ref 复现，另跑一个**不拦截**的漂移探测，在上游 HEAD 上失配就打 ⚠️。

## 安装（新机器）

```sh
git clone https://github.com/Loliyer520/DSHL-DeepPack-Jian.git ~/mediaflow/djian
cd ~/mediaflow/djian && git checkout e1b6130
git apply /path/to/huoke-mediaflow/engine/patches/djian-session-binding.patch
git apply /path/to/huoke-mediaflow/engine/patches/djian-desktop-shell.patch

# 把 bundle 放进 profile（link: 方式安装）
mkdir -p ~/mediaflow/djian/packages/dsh-bundle
cp /path/to/huoke-mediaflow/djian-bundle/* ~/mediaflow/djian/packages/dsh-bundle/
```

`~/.dsh/profiles/desktop/node_modules/@djian/*` 全部是指向 `~/mediaflow/djian/packages/*` 的软链，所以改完本地源码即生效，不需要重新打包。

## 起停

```bash
mf dj status     # 谁在跑、端口多少
mf dj up         # 起一个（日志 ~/.djian/logs/engine.log）
mf dj down       # 收掉（杀前校验进程确实是引擎）
```

## 升级上游时

1. 改 `.github/workflows/ci.yml` 的 `ENGINE_REF`（或先看漂移探测的 ⚠️）；
2. 在新 ref 上重新 `git apply`，冲突就按上游新代码改补丁；
3. 两个补丁都过之后，再 `mf dj down && mf dj up` 验收面板。

## D剪 预设里我们加了什么

`djian-bundle/cordis.patch.yml` 的【剪辑审美】第 3–6 条：

- 工作目录在 `~/媒体库/工程/` 下时，**先读 `~/获客平台/知识库/剪辑规范.md`，冲突以它为准**；
- MG 动效只允许用于字幕条、参数卡、结尾引导；
- 获客合规四条（品牌隔离 / 无联系方式 / 不报价不承诺 / 无绝对化 + AI 标识 + 固定 CTA）在 D剪 侧也写着，但**它只是提示，硬拦截在 `huoke_lint.py`**（`mf dj check` 与 `mf export` 两处闸门）。
