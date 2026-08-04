# Blender 简中—英文双语工具

为 Blender 4.x / 5.x 生成并启用简中—英文双语界面。支持两种显示顺序：

- `中文 English`
- `English 中文`

英文直接取自 Blender 官方简中 MO 的原始 `msgid`，不使用机器翻译。含 `%s`、`%d`、`{name}` 等动态占位符的文本保留官方中文，避免运行时格式化错误。

## 下载与使用

请从 [GitHub Releases](https://github.com/space4yyy/BlenderBilingual/releases/latest) 下载当前平台的成品：

- macOS：下载 `BlenderBilingual-macOS.dmg`，打开后把 `BlenderBilingual.app` 拖入“应用程序”。
- Windows：直接下载并运行 `BlenderBilingual-Windows.exe`。

macOS 成品目前没有 Developer ID 签名和 Apple 公证。从 DMG 把 App 拖入“应用程序”后，请打开 **终端 App**，执行以下命令清除下载隔离属性，然后再启动：

```bash
xattr -cr "/Applications/BlenderBilingual.app"
```

通常不需要 `sudo`。只应对确定来自本项目官方 Release 的 App 执行这条命令，不要对来源不明的 App 关闭安全检查。

Windows 成品目前没有 Authenticode 代码签名，因此 Microsoft Defender SmartScreen 可能显示“Windows 已保护你的电脑”。确认 EXE 来自本项目官方 Release 后，点击“更多信息”，再点击“仍要运行”即可启动。这是 Windows 对未知发布者和新文件信誉的提示，不是程序运行错误。

使用步骤：

1. 关闭正在运行的 Blender。
2. 启动 Blender 双语工具。
3. 从自动发现的列表选择 Blender；未找到时可手动选择 `Blender.app`、Blender 安装目录或 `blender.exe`。
4. 选择“中 - 英”或“英 - 中”。
5. 点击“注入并启用”，完成后重新打开 Blender。

需要恢复时，关闭 Blender 后点击“还原官方简中”。

macOS 与 Windows 均不需要管理员权限。工具只读取 Blender 安装目录中的官方语言资源，生成结果写入当前账户的 Blender 用户数据目录，不修改 `Blender.app`、`Program Files` 或官方简中 MO。

## 工作方式

工具不会内置特定 Blender 版本的语言包。每次注入时，它会：

1. 检测所选 Blender 的精确版本。
2. 读取该安装自带的官方 `zh_HANS/LC_MESSAGES/blender.mo`。
3. 在临时目录生成并校验所选顺序的双语 MO。
4. 向 Blender 返回的用户 `datafiles` 目录添加独立语言 `zh_HANS@bilingual`。
5. 保存当前用户的 Blender 语言偏好，并删除临时生成文件。

因此 Blender 更新后不需要等待项目发布对应语言包，只需重新运行工具。还原功能只移除本工具管理的用户文件；若旧版工具曾修改 Blender 安装目录，新版会用用户语言列表屏蔽旧菜单项，不再申请权限修改应用包。

## 支持范围

- macOS Blender.app
- Windows 标准安装版与便携版
- Blender 4.x / 5.x 中包含官方简中 MO 的版本

语言代码固定为 `zh_HANS@bilingual`，不会覆盖官方 `zh_HANS`。

## 从源码运行

需要 Python 3.10 或更高版本：

```bash
python3 blender_bilingual_gui.py
```

运行测试：

```bash
python3 -m unittest discover -v
```

## 构建桌面工具

PyInstaller 不能跨平台编译，需要分别在 macOS 和 Windows 上构建：

```bash
python -m pip install -r requirements-build.txt
python packaging/build_app.py
```

推送到 `main` 会触发双平台构建。推送 `v*` 标签时，GitHub Actions 会创建 Release，并直接附加：

- `BlenderBilingual-macOS.dmg`
- `BlenderBilingual-Windows.exe`

默认构建未使用商业代码签名和 Apple 公证。macOS Gatekeeper 与 Windows SmartScreen 的首次运行方式见上方说明。

## 许可证与来源

Blender 及其官方翻译由 Blender Authors 提供。本工具运行时生成的双语目录是官方翻译的派生作品，项目按 `GPL-2.0-or-later` 发布。详见 [LICENSE](LICENSE)。
