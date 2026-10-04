# Genea 0.2 公开发布说明

版本：`v0.2.0-preview.1`；App 内部版本为 `0.2.0`，构建号为 `2`。此版本继续作为预览发行。

## 发布内容

- 可本地编辑的浏览器源码 ZIP，要求 Python 3.12+，没有第三方 Python 运行时依赖。
- Apple Silicon（arm64）、macOS 13+ 的 `Genea.app` ZIP，自带完整独立 CPython 3.12.11；源码包同时提供本地 App 构建入口。
- 跨行亲子关系、增强亲属称谓、家谱检查和受限语法高级查询，由实验功能总开关控制。
- 新的只读 [Demo2：《百年孤独》](https://pifuyuini.github.io/genea/demo2/)，七代、46 人、53 条关系、46 张原创文学头像。
- 原 [Demo1：《红楼梦》](https://pifuyuini.github.io/genea/) 的既有站点文件保留原样；其公开文学数据仍随本地版发行。

预定下载文件：

- `genea-v0.2.0-preview.1-source.zip`
- `genea-v0.2.0-preview.1-macos-arm64.zip`

## 公开边界与许可

公开仓库延续独立 Git 历史，只同步明确选定的源码、测试、公开词库和文学样例。根目录个人家谱、个人照片、私人 Git 历史、内部材料、私人验收截图、缓存、临时工作副本及本地构建产物均不进入公开提交。

源码打包白名单只允许 `demo/data/photos/` 和 `demo2/data/photos/` 的文学人物照片。Demo2 保留独立 JPG、提示词和人物映射，不包含原始生成矩阵或裁切脚本。静态 Demo2 只从公开文学样例构建，不读取个人服务或本机目录。

中文称谓词库随包保留 `resources/kinship/LICENSE` 的完整上游 MIT 版权和许可。macOS App 保留独立 CPython 的完整运行时及其许可文本，说明见 `desktop/macos/RUNTIME-LICENSES.md`。Genea 自身仍未指定开源许可证。

## 发布流程

Ubuntu 作业运行 Python 测试并生成精简源码 ZIP；macOS arm64 作业以公开源码和完整官方独立 CPython 构建 App、运行原生和 JavaScript 检查，再生成 macOS ZIP。产物经 Actions artifact 传给最终 Ubuntu 作业，只有两项构建完全成功时才创建对应新标签的 prerelease，并上传两件明确命名的产物。

标签推送触发发布。手动执行需要明确输入已存在的标签；主分支上的发布工作流更新只触发验证，不会自动创建 Release。既有 Release 不覆盖、不删除，旧预览标签保持不变。

## 验证记录

本地验证已完成：

- 下载源码 ZIP 解压后重建 Demo2，Python 整套回归 305 项通过；修正 Demo1 生成入口后，另执行 9 项旧站构建定向检查通过。旧生成器使用原字节冻结的界面，并拒绝写入已发布的 docs 树。
- 原有 9 份 JavaScript 脚本通过，共 664 项断言、9 项动效测试及桥接检查；冻结 Demo1 只读回归新增范围定位后 100 项断言通过。Demo2 的 7,383 个 Python/浏览器查询用例、16,213 项断言及 2,174 项静态适配断言通过。
- 从解压源码构建公开 arm64 App，完整 CPython 3.12.11、包内后端启动、资源访问和 EOF 退出通过；实际双文学家谱窗口、资料及照片计数、剪贴板、截图和重启验收通过。
- 旧 Demo1 站点文件保留原样。精简包保留旧站生成与回归需要的 8 个冻结 HTML/CSS/JS/JSON 文件，而不包含完整预构建站点。

GitHub Actions、下载链接和线上站点的最终发布验收由本次统一上线流程记录；本地验证不视为线上验证。

## 当前限制

此下载 App 未使用 Developer ID 签名，也未经过 Apple 公证；系统可能要求按 [Apple 的安全打开 App 说明](https://support.apple.com/102445)确认来源并通过“隐私与安全性”中的系统选项打开。Intel Mac 使用浏览器源码版。

关系模型依赖已登记的亲子结构，未单独建模夫妻关系。文学演示不作为考据依据；实验结果与数据模型仍可能变化，重要数据请保留备份。
