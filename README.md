# Blender 简中—英文双语语言包

从 Blender 官方简体中文 `blender.mo` 直接生成 `中文 English` 双语界面，以一个空格分隔，不添加括号。英文来自同一 MO 中的原始 `msgid`，不使用机器翻译，也不需要英语语言包。

项目只保存最终双语 MO 与 JSON 元数据，不生成或归档 PO。含 `%s`、`%d`、`{name}` 等运行时占位符的消息会保留官方中文，避免重复占位符引发格式化错误。

## 已有语言包

- Blender 5.1.2，来源为官方 macOS Blender 5.1.2（构建哈希 `ec6e62d40fa9`）。

语言代码为 `zh_HANS@bilingual`，安装后会作为独立语言出现，不覆盖官方 `zh_HANS` 简体中文。Blender 5.1 会将它解析为简体中文脚本的 `bilingual` 变体，并搜索同名语言目录。

## 环境

- Python 3.10 或更高版本。
- 生成、校验和远程提取只使用 Python 标准库。
- 自动安装/卸载首版支持 macOS Blender.app；生成的 MO 本身不受操作系统限制。

## 生成语言包

从本机 Blender 生成：

```bash
python3 scripts/bilingual.py build --blender /Applications/Blender.app
```

本机未安装目标版本时，指定精确版本。脚本会从 Blender 官方目录下载 Linux `tar.xz`，校验官方 SHA-256，只读取其中的简中 MO，并在完成后删除整个临时目录：

```bash
python3 scripts/bilingual.py build --version 4.4.3
```

发行包通常有数百 MB。Linux 包仅作为跨平台、易解压的语言资源容器，不会安装或运行其中的 Blender。

也可使用已有的官方简中 MO 离线生成：

```bash
python3 scripts/bilingual.py build \
  --version 4.4.3 \
  --source-mo /path/to/zh_HANS/LC_MESSAGES/blender.mo
```

必须使用 `4.4.3` 这样的完整版本，不能只写 `4.4`。输出位于：

```text
packs/4.4.3/
├── manifest.json
└── zh_HANS@bilingual/LC_MESSAGES/blender.mo
```

## 校验

```bash
python3 scripts/bilingual.py verify --version 5.1.2
python3 -m unittest discover -v
```

校验包括 MO 结构、版本、消息键摘要、消息统计和文件 SHA-256。

## macOS 安装与卸载

先预览操作：

```bash
python3 scripts/bilingual.py install --dry-run
```

安装到默认 `/Applications/Blender.app`：

```bash
python3 scripts/bilingual.py install
```

也可以指定 Blender.app，并二次确认版本：

```bash
python3 scripts/bilingual.py install \
  --blender /Applications/Blender.app \
  --version 5.1.2
```

若终端没有修改应用包的权限，请按 macOS 提示授予权限或使用具备相应权限的终端。安装器会：

1. 备份原始 `languages` 文件；
2. 动态选择未占用的语言 ID；
3. 添加带托管标记的独立语言项；
4. 原子写入双语 MO。

安装器会使用 Blender 自身的后台模式加载现有用户偏好，只把当前语言改为 `zh_HANS@bilingual` 并保存；其他偏好保持不变。安装完成后再次打开 Blender 即为双语界面。若只想安装而不自动启用，可添加 `--no-activate`。

卸载：

```bash
python3 scripts/bilingual.py uninstall --dry-run
python3 scripts/bilingual.py uninstall
```

卸载前会把当前用户语言切回官方简中，然后只移除本项目管理的菜单区块和 `zh_HANS@bilingual` 目录，不覆盖其他语言修改。可用 `--no-reset-language` 跳过偏好修改。Blender 更新可能清除自定义语言，更新后重新运行安装命令即可。

## 添加其他 4.x / 5.x 版本

对每个精确补丁版本分别运行 `build` 和 `verify`。不同补丁版本可能包含不同消息，因此不应把一个 MO 重命名后用于其他版本。

`manifest.json` 会记录官方源 MO、最终 MO、消息键的 SHA-256，以及普通双语、动态消息、上下文和复数条目的数量，便于以后重复生成和审计。

## 许可证与来源

Blender 及其官方翻译由 Blender Authors 提供。本项目生成的双语目录是该翻译的派生作品，按 `GPL-2.0-or-later` 发布。详见 [LICENSE](LICENSE)。
