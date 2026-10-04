# Genea

Genea 是在自己电脑上运行的家谱画布，提供人物资料、代际排布、照片、亲属跳转和两人关系路径。

**当前公开版本：0.2.0-preview.1。** 新版加入 macOS App、跨行亲子关系、增强亲属称谓、家谱检查与受限语法的高级查询，功能与数据模型仍会调整。

[新版 Demo2：《百年孤独》](https://pifuyuini.github.io/genea/demo2/) · [原版 Demo1：《红楼梦》](https://pifuyuini.github.io/genea/) · [下载浏览器源码 ZIP](https://github.com/pifuyuini/genea/releases/download/v0.2.0-preview.1/genea-v0.2.0-preview.1-source.zip) · [下载 macOS App](https://github.com/pifuyuini/genea/releases/download/v0.2.0-preview.1/genea-v0.2.0-preview.1-macos-arm64.zip) · [版本说明](https://github.com/pifuyuini/genea/releases/tag/v0.2.0-preview.1)

在线演示均为只读文学样例；Demo1 保留原版页面，Demo2 展示新版功能。下载到本机后可以编辑，自己的家谱和照片保存在本机。公开发行不包含任何个人家谱。

## macOS App

支持 **Apple Silicon（arm64）、macOS 13 或更高版本**。下载并解压 macOS ZIP，将 `Genea.app` 拖到应用程序目录后打开；App 自带完整 Python 运行时，无需安装 Python 或第三方库。内置两份文学 Demo，可用于体验；新家谱从空白开始。

此下载包未使用 Developer ID 签名，也未经过 Apple 公证。若 macOS 阻止打开，先确认下载来自上方官方版本链接，再遵循 [Apple 的安全打开 App 说明](https://support.apple.com/102445)，在“系统设置 → 隐私与安全性”中使用系统提供的打开选项。

人物数据与照片保存于所选家谱目录。备份时先退出 App，再复制整个目录。首次公开的原生 App 尚为预览版，重要数据请保留备份。Intel Mac 可使用下述浏览器源码版。

## 浏览器源码版

需要 **Python 3.12 或更高版本**，没有第三方 Python 运行时依赖。下载源码 ZIP，解压后进入含 `server.py` 的目录。

建立空白家谱：

```sh
python3 -B server.py --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>。首次运行创建空白工作区，数据保存于 `data/`、照片位于 `data/photos/`；停止服务后复制整个 `data/` 即可备份。按 `Ctrl+C` 停止。

体验新版《百年孤独》Demo2：

```sh
python3 -B demo2/run_demo.py
```

打开 <http://127.0.0.1:8767>。每次默认启动创建独立的工作副本，并在终端显示其 `data` 目录；退出后仍保留编辑结果。继续已有副本时明确传入 `--data-dir`，详见 [Demo2 说明](demo2/README.md)。

体验《红楼梦》数据：

```sh
python3 -B demo/run_demo.py
```

打开 <http://127.0.0.1:8766>。该启动器每次重置独立的演示副本；加 `--keep` 保留上一次演示编辑。本地两份文学样例都使用新版界面，在线 Demo1 保留原版界面。

Windows 将上述 `python3` 替换为 `py -3`。端口被占用时传入其他 `--port` 并使用对应地址。Python 安装程序见 [python.org](https://www.python.org/downloads/)；无需运行 pip 或 npm。

## 常用操作

- 滚轮缩放，按空格拖动画布，点击“全览”查看完整家谱。
- 搜索人物并打开资料；选择 A、B 两人查看登记路径与亲属结果，支持浅色与深色主题。
- 本地版可编辑人物和代际、连线、上传照片、撤销与重做。
- 实验功能总开关控制跨行编辑、增强称谓、家谱检查和高级查询；关闭时保留已登记的跨行数据，相关工作区会暂为只读。在线 Demo2 始终只读。
- 模型以亲子登记为依据，未单独登记夫妻边；未收录的关系不能由软件补成真实家族关系。

## 本地重建 macOS App

在 Apple Silicon Mac 上使用已有的 Xcode 命令行工具。以下流程只把官方独立 CPython 解压到当前源码目录的 `tmp/`，不安装产品依赖：

```sh
BUILD_DIR="tmp/$(date +%Y%m%d-%H%M%S)-macos-build"
mkdir -p "$BUILD_DIR"
touch "$BUILD_DIR/.codex-tmp"
curl --fail --location \
  'https://github.com/astral-sh/python-build-standalone/releases/download/20250708/cpython-3.12.11%2B20250708-aarch64-apple-darwin-install_only.tar.gz' \
  --output "$BUILD_DIR/cpython.tar.gz"
tar -xzf "$BUILD_DIR/cpython.tar.gz" -C "$BUILD_DIR"
"$BUILD_DIR/python/bin/python3.12" -B desktop/macos/build_app.py \
  --runtime "$BUILD_DIR/python" --output "$BUILD_DIR/Genea.app"
open "$BUILD_DIR/Genea.app"
```

也可通过 `--runtime` 指向已有的完整 uv standalone CPython 3.12.11 arm64 目录。构建保留完整运行时和许可文件；详见 [macOS 构建说明](desktop/macos/README.md)与[运行时许可](desktop/macos/RUNTIME-LICENSES.md)。

## 源码、静态站点与验证

`scripts/build_source.py` 按固定白名单构建下载包，只收录应用源码、测试、词库许可和两份文学样例。公开包包含 38＋46 张独立头像、Demo1 既有截图，以及 Demo2 头像的提示词和映射；不包含原始生成矩阵。精简源码包保留旧 Demo1 回归所需的 8 个冻结文件，不包含完整预构建站点；新版静态页由源码重建。GitHub 自带的标签源码包则包含整个公开仓库。

```sh
python3 -B scripts/build_source.py --version v0.2.0-preview.1
python3 -B demo2/build_pages.py
```

Demo2 构建器写入 `docs/demo2/` 和新增的 `docs/demos/` 演示选择页。**旧 `docs/` 已冻结。** Demo1 生成器使用包内原字节冻结的 HTML/CSS/JS，仅支持通过 `--output-dir` 指定独立预览目录；它拒绝写入 `docs/` 及其子目录。新版构建不会覆盖旧 Demo1，旧版预览构建也不会覆盖 Demo2。

精简源码包不含预构建页面，先运行 `python3 -B demo2/build_pages.py`，再运行 Python 测试：

```sh
TEST_DIR="tmp/$(date +%Y%m%d-%H%M%S)-tests"
mkdir -p "$TEST_DIR"
touch "$TEST_DIR/.codex-tmp"
GENEA_QA_DIR="$PWD/$TEST_DIR" GENEA_TEST_TMP="$PWD/$TEST_DIR" TMPDIR="$PWD/$TEST_DIR" \
  python3 -B -m unittest discover -s tests -p 'test_*.py'
```

macOS 的 JavaScript 测试使用系统 JavaScriptCore。`test_demo2_query.js` 的期望响应由 `test_pages_demo2.py` 提供，不单独执行；`test_motion.js` 需预载 `static/motion.js`。发布工作流提供完整执行命令。发布工作流分别测试和构建源码包、macOS App；两项成功后才创建新的预览 Release，不会覆盖既有 Release。

中文亲属词库来源及完整 MIT 许可保存在 `resources/kinship/`。Genea 自身目前未指定开源许可证。发布范围与本次验证记录见 [PUBLICATION.md](PUBLICATION.md)。
