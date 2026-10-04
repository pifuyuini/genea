# 中文血亲称谓词库

本目录从 [mumuy/relationship](https://github.com/mumuy/relationship) 的公开 `relationship.data` 导出年龄中立的纯血亲关系词条，仅用于对已由真实家谱确定的关系命名。应用不得调用原库的文本解析、身份折叠、年龄推测或婚姻推导来代替家谱关系计算。

## 来源和许可

- 官方版本：`relationship.js v1.2.9`。
- 固定上游 Git revision：`35c44427befb6fd59e16f583b5b92a680a7948db`，官方提交日期为 2026-09-21。
- [固定 JavaScript 包](https://raw.githubusercontent.com/mumuy/relationship/35c44427befb6fd59e16f583b5b92a680a7948db/dist/relationship.min.js)、[版本声明](https://github.com/mumuy/relationship/blob/35c44427befb6fd59e16f583b5b92a680a7948db/package.json)、[公开数据接口](https://github.com/mumuy/relationship/blob/35c44427befb6fd59e16f583b5b92a680a7948db/readme.md)。
- MIT 许可；上游完整版权和许可文本保存在同目录 `LICENSE`，发布本词库时须一并保留。

## 数据格式

`terms.json` 是 UTF-8 的单层 JSON 对象：`{ "selector": ["别名", "别名"] }`，共 **7,524 个关系键、811,490 字节**。关系键按字典序稳定排列，别名的文字、原顺序和重复项均保留上游数据。

仅保留下列结构；逗号分隔的符号 `f/m/s/d/xb/xs` 分别表示父亲、母亲、儿子、女儿、兄弟、姐妹：

1. 一次或多次父母上行：`(f|m)+`。
2. 一次或多次儿女下行：`(s|d)+`。
3. 零次或多次父母上行、恰好一个性别确定的手足拐点、零次或多次儿女下行：`(f|m)* (xb|xs) (s|d)*`。

不包含年龄修饰符、具体长幼的 `ob/lb/os/ls`、配偶符号 `h/w`、本人性别前缀、多次手足拐点或父母子女折返。图算法须先利用实际人物身份确定拐点两侧为不同人物，再生成 canonical selector；不能直接将任意原始图路径交给原库化简。`special` 边不属于本词库的血亲输入。

例如 `f,f,f,f,xb,s` 包含 `堂伯叔曾祖父`、`堂曾祖父` 等别名。长幼未知时应保留中立合称，不选择具体伯/叔、兄/弟、姐/妹。词库中第一项并不保证是最适合本应用的正式称谓：有些是口语、地域名称或古称；应用应自行选择已核对的显示名称，并保留明确关系链作为解释。

词库有有限覆盖范围，并不保证所有稀有称谓都经过权威辞典独立认证；上游本身也说明了地域和词义分歧。未命中的关系应使用家谱已经确定的关系描述，不推测缺失的婚姻、人物身份或长幼。

## 重建和更新

导出脚本使用本项目 Python 环境、Python 标准库和 macOS 自带 JavaScriptCore，不需要安装 Node、npm 或第三方依赖。脚本要求显式传入输出路径，不自动覆盖本资源；输出路径的父目录须已存在。

在项目根目录运行以下命令，从固定官方 revision 下载到内存并导出到本任务临时目录：

```sh
.venv/bin/python -B scripts/build_kinship_terms.py \
  --output tmp/20261003-genea-extended-kinship/kinship-terms-online.json
```

已有官方包时可以完全离线重建：

```sh
.venv/bin/python -B scripts/build_kinship_terms.py \
  --source-file tmp/20261003-genea-extended-kinship/relationship-v1.2.9.min.js \
  --output tmp/20261003-genea-extended-kinship/kinship-terms-rebuilt.json
```

首次生成已使用离线重建和直接字节比较确认结果可复现；所有关系键和别名都通过完整 JSON 检查。临时目录属于本次任务，后续任务应使用自己获授权的输出目录。

更新时先确认新的官方版本和不可变 revision，再同步修改脚本的 `VERSION`、`SOURCE_REVISION`、本说明及上游许可文本。先导出到任务临时路径，检查词条变更和正式显示名称，验证同源离线重建可复现后，再替换 `terms.json`。脚本以固定官方 revision 和包头版本声明记录来源，不生成哈希或校验和。
