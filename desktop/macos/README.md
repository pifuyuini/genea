# Genea macOS App

Genea 的原生 AppKit 窗口通过 WKWebView 显示共享网页界面。公开预览包内含完整独立 CPython 3.12.11 arm64、后端、前端、称谓资源和两份文学 Demo，双击即可离线运行。支持 Apple Silicon、macOS 13 或更高版本；Intel 和通用二进制尚未提供。

每份家谱使用独立原生窗口。“家谱 → 打开所有家谱窗口”可同时打开已有家谱；“窗口”菜单用于切换。Control＋Command＋F 切换全屏，Command＋W 关闭当前窗口，Command＋Q 退出 App。关闭最后一个窗口后 App 继续运行，点击 Dock 图标可恢复最近窗口。未保存草稿会提示继续编辑或放弃。

## 构建

需要设备已有的 Xcode 命令行工具，以及完整独立 CPython 3.12.11 arm64。运行时必须包含解释器、标准库、扩展、动态库和许可文件；只提供一个可执行文件不足以构建。

根 [README](../../README.md#本地重建-macos-app) 给出官方运行时下载及完整命令。使用已有运行时时：

```sh
GENEA_BUILD_DIR="tmp/$(date +%Y%m%d-%H%M%S)-macos-build"
mkdir -p "$GENEA_BUILD_DIR"
touch "$GENEA_BUILD_DIR/.codex-tmp"
python3.12 -B desktop/macos/build_app.py \
  --runtime '<完整 standalone CPython 目录>' \
  --output "$GENEA_BUILD_DIR/Genea.app"
```

输出位于源码目录 `tmp/` 的任务标记目录中，已有 App 不会被覆盖。构建复制完整运行时，调整包内动态库引用，生成图标和 arm64 原生宿主，再验证内置后端启动、退出及本地 ad hoc 签名。构建不读取根 `data/`。

## 数据与备份

公开文学样例在 App 的 `Contents/Resources/seeds/`。首次运行复制为独立持久工作目录，之后保留编辑、照片、历史和实验设置。默认资料库位于用户的 `Application Support/Genea`；“家谱 → 导入家谱副本…”复制所选家谱的资料和照片。

每份家谱使用独立的本地后端进程，动态端口只绑定到 `127.0.0.1`。关闭窗口或退出 App 会有序停止对应后端。备份时退出 App，再复制所选家谱的完整目录。

## 验证与分发

```sh
GENEA_QA_DIR="$PWD/$GENEA_BUILD_DIR" python3.12 -B -m unittest discover \
  -s tests -p 'test_desktop_*.py'
/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_desktop_bridge.js
python3.12 -B tests/test_desktop_launch.py \
  --app "$GENEA_BUILD_DIR/Genea.app" --qa-dir "$GENEA_BUILD_DIR"
```

原生测试验证动态端口、隔离编辑、实验设置、后端退出、公开资源、实际 WKWebView 的资料和照片加载，以及截图、剪贴板和重启。测试只使用合成数据或文学 Demo。

下载包未使用 Developer ID 签名，也未经过 Apple 公证。首次打开可能被系统阻止；确认官方下载来源后，遵循 [Apple 的安全打开 App 说明](https://support.apple.com/102445)使用系统的“隐私与安全性”打开选项。

完整运行时的版权与许可文件保留在 App 内，见 [RUNTIME-LICENSES.md](RUNTIME-LICENSES.md)。
