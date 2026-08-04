#!/usr/bin/env python3
"""Build the small desktop application with the current platform's PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "blender_bilingual_gui.py"
NAME = "BlenderBilingual"


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
        arguments.append("--onefile")
    else:
        raise SystemExit("桌面安装包目前只支持在 macOS 或 Windows 上构建")
    PyInstaller.__main__.run(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
