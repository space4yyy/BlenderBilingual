# Blender 简中—英文双语语言包

从 Blender 官方简体中文 `blender.mo` 直接生成双语界面，可选择 `中文 English` 或 `English 中文`，以一个空格分隔，不添加括号。英文来自同一 MO 中的原始 `msgid`，不使用机器翻译，也不需要英语语言包。

项目只保存最终双语 MO 与 JSON 元数据，不生成或归档 PO。含 `%s`、`%d`、`{name}` 等运行时占位符的消息会保留官方中文，避免重复占位符引发格式化错误。

## 快速开始

### 图形工具（macOS / Windows）

从项目的 GitHub Actions 下载对应平台产物并解压：

- macOS：打开 `BlenderBilingual.app`；
- Windows：运行 `BlenderBilingual.exe`，系统会请求管理员权限。

工具启动后会自动查找本机 Blender，也可以点“手动选择…”指定 `Blender.app`、安装目录或 `blender.exe`。选择“中 - 英”或“英 - 中”，关闭正在运行的 Blender，然后点“注入并启用”。工具会直接读取所选 Blender 自带的官方简中 MO，临时生成对应顺序、校验、注入并保存语言偏好；不会下载发行包，也不会在电脑上长期保存生成缓存。

点“还原官方简中”会先把用户语言切回 `zh_HANS`，再移除本工具管理的菜单项和语言目录。工具不会修改官方简中 MO。

> macOS 若提示无法修改应用，请确认当前账户对该 `Blender.app` 有写入权限。Windows 标准安装通常位于受保护目录，因此打包的 EXE 会自动请求管理员权限。

脚本会读取本地 Blender 的精确版本。若 `packs/` 中没有对应版本，会自动使用该 Blender 自带的官方简中 MO 生成并校验双语包，然后继续安装。

### 1. 脚本安装

脚本会备份 `languages` 文件、安装 MO、添加独立语言项，并把当前用户语言设为 `zh_HANS@bilingual`。先关闭 Blender，再执行安装。

macOS：

```bash
python3 scripts/bilingual.py install \
  --dry-run \
  --blender /Applications/Blender.app

python3 scripts/bilingual.py install \
  --blender /Applications/Blender.app
```

Windows：请在“以管理员身份运行”的 PowerShell 或 Windows Terminal 中执行，并把路径改为实际安装位置。

```powershell
py scripts\bilingual.py install `
  --dry-run `
  --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"

py scripts\bilingual.py install `
  --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

`--version 5.2.0` 是可选的二次校验；省略时以检测到的本地版本为准。`--dry-run` 只报告将自动生成，不写入 pack 或 Blender。安装成功后，再次打开 Blender 即为双语界面。若只安装文件、不修改当前用户语言，请添加 `--no-activate`。

### 2. 手动安装

1. 关闭 Blender，并备份安装目录内的 `datafiles/locale/languages`。
2. 在 `datafiles/locale/` 下创建 `zh_HANS@bilingual/LC_MESSAGES/`。
3. 将对应版本的 `packs/<版本>/zh_HANS@bilingual/LC_MESSAGES/blender.mo` 复制到新目录。
4. 打开 `datafiles/locale/languages`，选择一个未占用的数字 ID，并添加：

   ```text
   60:Chinese (Simplified, Bilingual) - 简中 English:zh_HANS@bilingual:100%
   ```

   如果 ID 60 已存在，请换成其他未占用数字；同一文件中的 ID 必须唯一。

5. 启动 Blender，进入 `Edit > Preferences > Interface > Translation > Language`，选择 `Chinese (Simplified, Bilingual) - 简中 English`，然后保存偏好。

macOS 目标目录：

```text
/Applications/Blender.app/Contents/Resources/5.1/datafiles/locale/
```

Windows 默认目标目录：

```text
C:\Program Files\Blender Foundation\Blender 5.1\5.1\datafiles\locale\
```

Windows 若使用便携版，目标目录位于 `blender.exe` 同级的 `5.1\datafiles\locale\`。手动安装不会自动修改用户偏好，必须完成第 5 步。

## 已有语言包

- Blender 5.1.2，来源为官方 macOS Blender 5.1.2（构建哈希 `ec6e62d40fa9`）。
- Blender 5.2.0 LTS，来源为官方 macOS Blender 5.2.0（构建哈希 `fbe6228777e7`）。

语言代码为 `zh_HANS@bilingual`，安装后会作为独立语言出现，不覆盖官方 `zh_HANS` 简体中文。Blender 5.1 会将它解析为简体中文脚本的 `bilingual` 变体，并搜索同名语言目录。

## 环境

- Python 3.10 或更高版本。
- 生成、校验和远程提取只使用 Python 标准库。
- 自动安装/卸载支持 macOS Blender.app 和 Windows 标准/便携目录；生成的 MO 本身不受操作系统限制。

## 生成语言包

从本机 Blender 生成：

```bash
python3 scripts/bilingual.py build --blender /Applications/Blender.app
```

生成“英 - 中”顺序：

```bash
python3 scripts/bilingual.py build \
  --blender /Applications/Blender.app \
  --order en-zh
```

默认顺序为 `--order zh-en`。动态占位符消息在两种顺序下都保留官方中文，以避免运行时重复格式化参数。

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

## 安装与卸载详解

先预览操作：

```bash
python3 scripts/bilingual.py install --dry-run
```

macOS 安装到默认 `/Applications/Blender.app`：

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

如果当前 Blender 已升级且仓库没有对应版本，`install` 会先从本地官方简中 MO 自动生成 pack。已有 pack 必须通过完整校验；文件缺失或损坏时安装器会停止，不会静默覆盖。

卸载：

```bash
python3 scripts/bilingual.py uninstall --dry-run
python3 scripts/bilingual.py uninstall
```

Windows 卸载时必须显式指定 `blender.exe`，并使用管理员终端：

```powershell
py scripts\bilingual.py uninstall `
  --dry-run `
  --blender "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"

py scripts\bilingual.py uninstall `
  --blender "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
```

卸载前会把当前用户语言切回官方简中，然后只移除本项目管理的菜单区块和 `zh_HANS@bilingual` 目录，不覆盖其他语言修改。可用 `--no-reset-language` 跳过偏好修改。Blender 更新可能清除自定义语言，更新后重新运行安装命令即可。

## 添加其他 4.x / 5.x 版本

对每个精确补丁版本分别运行 `build` 和 `verify`。不同补丁版本可能包含不同消息，因此不应把一个 MO 重命名后用于其他版本。

`manifest.json` 会记录官方源 MO、最终 MO、消息键的 SHA-256，以及普通双语、动态消息、上下文和复数条目的数量，便于以后重复生成和审计。

## 构建桌面工具

桌面工具只包含 Python、Tk 图形界面和项目脚本，不内置仓库中的语言包。macOS 与 Windows 需要在各自系统上分别构建：

```bash
python -m pip install -r requirements-build.txt
python packaging/build_app.py
```

产物位于 `dist/`：macOS 为 `BlenderBilingual.app`，Windows 为单文件 `BlenderBilingual.exe`。推送到 `main` 或在 GitHub Actions 页面手动运行 `Build desktop apps`，会在该次 Actions 运行中上传两个 ZIP；推送 `v*` 标签时，还会自动创建对应 GitHub Release，并把 macOS、Windows ZIP 附加为 Release 下载文件。

默认构建没有开发者证书与公证。首次打开下载的 macOS 应用时可在 Finder 中右键选择“打开”；Windows 可能显示 SmartScreen 提示。正式公开分发时建议在 CI 中另行配置 Apple Developer ID、公证和 Windows 代码签名证书。

## 许可证与来源

Blender 及其官方翻译由 Blender Authors 提供。本项目生成的双语目录是该翻译的派生作品，按 `GPL-2.0-or-later` 发布。详见 [LICENSE](LICENSE)。
