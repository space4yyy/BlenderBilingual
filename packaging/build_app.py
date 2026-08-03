#!/usr/bin/env python3
"""Build the small desktop application with the current platform's PyInstaller."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "blender_bilingual_gui.py"
NAME = "BlenderBilingual"


def configure_macos_bundle() -> None:
    app = ROOT / "dist" / f"{NAME}.app"
    info_plist = app / "Contents" / "Info.plist"
    with info_plist.open("rb") as handle:
        values = plistlib.load(handle)
    values["NSAppBundlesUsageDescription"] = (
        "用于向用户选择的 Blender 应用注入或移除双语语言文件。"
    )
    with info_plist.open("wb") as handle:
        plistlib.dump(values, handle, sort_keys=False)
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app)],
        check=True,
    )


def main() -> int:
    arguments = [
        str(ENTRYPOINT),
        "--name",
        NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--paths",
        str(ROOT),
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
    ]
    if sys.platform == "darwin":
        arguments.extend(
            [
                "--onedir",
                "--osx-bundle-identifier",
                "com.space4.blender-bilingual",
            ]
        )
    elif sys.platform == "win32":
        arguments.extend(["--onefile", "--uac-admin"])
    else:
        raise SystemExit("桌面安装包目前只支持在 macOS 或 Windows 上构建")
    PyInstaller.__main__.run(arguments)
    if sys.platform == "darwin":
        configure_macos_bundle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
