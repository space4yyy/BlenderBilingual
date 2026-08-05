#!/usr/bin/env python3
"""Small native-style GUI for injecting Blender bilingual translations."""

from __future__ import annotations

import sys
import subprocess
import tempfile
import threading
from pathlib import Path

from scripts.bilingual import (
    BilingualError,
    ORDER_EN_ZH,
    ORDER_ZH_EN,
    blender_layout,
    build_from_source,
    discover_blender_installations,
    install_pack,
    parse_version,
    uninstall_pack,
    verify_pack,
)


APP_NAME = "Blender 双语工具"


def inject(blender: Path, order: str) -> str:
    """Build from the selected installation, inject it, and discard temporary files."""
    _executable, datafiles, version = blender_layout(blender)
    official_mo = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
    if not official_mo.is_file():
        raise BilingualError(f"找不到 Blender 自带的官方简中语言包：{official_mo}")
    _version, resource_version = parse_version(version)
    with tempfile.TemporaryDirectory(prefix="blender-bilingual-gui-") as temporary:
        packs_root = Path(temporary) / "packs"
        build_from_source(
            official_mo,
            version,
            resource_version,
            {"type": "local_blender", "blender": str(blender.expanduser().resolve())},
            packs_root,
            order,
        )
        verify_pack(version, packs_root, order)
        return install_pack(
            blender,
            version,
            False,
            packs_root,
            activate=True,
            order=order,
        )


def restore(blender: Path) -> str:
    return uninstall_pack(blender, False, reset_language=True)


def blender_process_running(platform_name: str | None = None) -> bool:
    """Return whether an interactive Blender process is currently running."""
    platform_name = platform_name or sys.platform
    command = (
        ["tasklist", "/FI", "IMAGENAME eq blender.exe", "/NH"]
        if platform_name == "win32"
        else ["pgrep", "-x", "Blender" if platform_name == "darwin" else "blender"]
    )
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if platform_name == "win32":
        return "blender.exe" in result.stdout.casefold()
    return result.returncode == 0


def enable_windows_high_dpi(platform_name: str | None = None) -> None:
    """Ask Windows to render Tk at the monitor's native scale."""
    if (platform_name or sys.platform) != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, font as tkfont, messagebox, ttk
    except ImportError as exc:
        print("当前 Python 未包含 Tk 图形界面支持。请使用已打包的应用。", file=sys.stderr)
        return 2

    class Application:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title(APP_NAME)
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=1)
            self.path = tk.StringVar()
            self.order = tk.StringVar(value=ORDER_ZH_EN)
            self.status = tk.StringVar(value="正在查找本机 Blender…")
            self.busy = False
            self._configure_style()
            self._build_ui()
            self.root.update_idletasks()
            width = max(620, self.root.winfo_reqwidth())
            self.root.geometry(f"{width}x{self.root.winfo_reqheight()}")
            self.root.resizable(False, False)
            self.root.after(80, self._discover)

        def _configure_style(self) -> None:
            style = ttk.Style(self.root)
            available = style.theme_names()
            preferred = "aqua" if sys.platform == "darwin" else "vista"
            if preferred in available:
                style.theme_use(preferred)

            default_font = tkfont.nametofont("TkDefaultFont")
            if sys.platform == "win32":
                default_font.configure(family="Segoe UI", size=10)
                tkfont.nametofont("TkTextFont").configure(family="Segoe UI", size=10)
            title_font = default_font.copy()
            title_font.configure(size=20 if sys.platform == "darwin" else 18, weight="bold")
            section_font = default_font.copy()
            section_font.configure(weight="bold")

            style.configure("App.TFrame", padding=0)
            style.configure("Title.TLabel", font=title_font)
            style.configure("Section.TLabel", font=section_font)
            style.configure("Subtitle.TLabel", foreground="#666666")
            style.configure("Info.Status.TLabel", foreground="#4b5563")
            style.configure("Success.Status.TLabel", foreground="#16803c")
            style.configure("Error.Status.TLabel", foreground="#b42318")
            style.configure("Primary.TButton", padding=(16, 7))
            style.configure("Secondary.TButton", padding=(12, 7))

        def _build_ui(self) -> None:
            frame = ttk.Frame(self.root, padding=(24, 22), style="App.TFrame")
            frame.grid(sticky="nsew")
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=1)

            ttk.Label(frame, text="Blender 双语工具", style="Title.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w"
            )
            ttk.Label(
                frame,
                text="从 Blender 自带语言生成双语界面，不覆盖官方简中。",
                style="Subtitle.TLabel",
            ).grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(4, 22)
            )

            ttk.Label(frame, text="Blender 位置", style="Section.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )
            location_row = ttk.Frame(frame)
            location_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(7, 0))
            location_row.columnconfigure(0, weight=1)
            self.location = ttk.Combobox(location_row, textvariable=self.path, width=57)
            self.location.grid(row=0, column=0, sticky="ew")
            self.location.bind("<<ComboboxSelected>>", lambda _event: self._check_selection())
            self.location.bind("<FocusOut>", lambda _event: self._check_selection())
            self.browse_button = ttk.Button(location_row, text="手动选择…", command=self._browse)
            self.browse_button.grid(
                row=0, column=1, padx=(8, 0)
            )

            ttk.Separator(frame).grid(row=4, column=0, columnspan=2, sticky="ew", pady=20)
            ttk.Label(frame, text="显示顺序", style="Section.TLabel").grid(
                row=5, column=0, columnspan=2, sticky="w"
            )
            options = ttk.Frame(frame)
            options.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
            self.order_buttons = (
                ttk.Radiobutton(options, text="中 - 英", variable=self.order, value=ORDER_ZH_EN),
                ttk.Radiobutton(options, text="英 - 中", variable=self.order, value=ORDER_EN_ZH),
            )
            self.order_buttons[0].grid(row=0, column=0, padx=(0, 32), sticky="w")
            self.order_buttons[1].grid(row=0, column=1, sticky="w")

            status_row = ttk.Frame(frame)
            status_row.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(18, 0))
            status_row.columnconfigure(0, weight=1)
            self.status_label = ttk.Label(
                status_row,
                textvariable=self.status,
                style="Info.Status.TLabel",
                wraplength=550,
            )
            self.status_label.grid(row=1, column=0, sticky="w")

            actions = ttk.Frame(frame)
            actions.grid(row=8, column=0, columnspan=2, sticky="e", pady=(20, 0))
            self.restore_button = ttk.Button(
                actions,
                text="还原官方简中",
                style="Secondary.TButton",
                command=self._restore,
            )
            self.restore_button.grid(row=0, column=0, padx=(0, 8))
            self.inject_button = ttk.Button(
                actions,
                text="注入并启用",
                style="Primary.TButton",
                command=self._inject,
            )
            self.inject_button.grid(row=0, column=1)

        def _discover(self) -> None:
            paths = discover_blender_installations()
            values = [str(path) for path in paths]
            self.location.configure(values=values)
            if values:
                self.path.set(values[0])
                self._check_selection()
            else:
                self._set_status("未自动找到 Blender，请手动选择安装目录或可执行文件。")

        def _browse(self) -> None:
            if sys.platform == "darwin":
                selected = filedialog.askopenfilename(
                    title="选择 Blender.app",
                    initialdir="/Applications",
                    filetypes=(("Blender 应用", "*.app"), ("所有文件", "*.*")),
                )
            elif sys.platform == "win32":
                selected = filedialog.askopenfilename(
                    title="选择 blender.exe", filetypes=(("Blender", "blender.exe"), ("所有文件", "*.*"))
                )
            else:
                selected = filedialog.askopenfilename(title="选择 Blender 可执行文件")
            if selected:
                self.path.set(selected)
                self._check_selection()

        def _selected_path(self) -> Path:
            value = self.path.get().strip().strip('"')
            if not value:
                raise BilingualError("请先选择 Blender 安装位置")
            return Path(value)

        def _check_selection(self) -> None:
            if self.busy or not self.path.get().strip():
                return
            self._run(
                lambda: blender_layout(self._selected_path()),
                lambda result: self._set_status(f"已找到 Blender {result[2]}"),
                quiet=True,
            )

        def _inject(self) -> None:
            try:
                blender = self._selected_path()
            except BilingualError as exc:
                self._set_status(str(exc), "error")
                messagebox.showerror(APP_NAME, str(exc), parent=self.root)
                return
            if blender_process_running():
                messagebox.showwarning(
                    APP_NAME,
                    "检测到 Blender 正在运行。请先退出 Blender，再重新执行注入。",
                    parent=self.root,
                )
                return
            self._start_inject(blender)

        def _start_inject(self, blender: Path) -> None:
            self._set_status("正在生成、校验并注入双语语言…")
            self._run(
                lambda: inject(blender, self.order.get()),
                lambda result: self._succeeded(
                    "注入完成", result + "。\n\n重新打开 Blender 即可使用。"
                ),
            )

        def _restore(self) -> None:
            try:
                blender = self._selected_path()
            except BilingualError as exc:
                self._set_status(str(exc), "error")
                messagebox.showerror(APP_NAME, str(exc), parent=self.root)
                return
            if blender_process_running():
                messagebox.showwarning(
                    APP_NAME,
                    "检测到 Blender 正在运行。请先退出 Blender，再重新执行还原。",
                    parent=self.root,
                )
                return
            self._start_restore(blender)

        def _start_restore(self, blender: Path) -> None:
            self._set_status("正在还原官方简中…")
            self._run(lambda: restore(blender), lambda result: self._succeeded("还原完成", result))

        def _run(self, work, success, quiet: bool = False) -> None:
            if self.busy:
                return
            self.busy = True
            self._set_controls(False)

            def worker() -> None:
                try:
                    result = work()
                except (BilingualError, OSError) as exc:
                    message = str(exc)
                    self.root.after(0, lambda message=message: self._failed(message, quiet))
                except Exception as exc:  # Keep packaged GUI failures user-visible.
                    message = f"发生未预期错误：{exc}"
                    self.root.after(0, lambda message=message: self._failed(message, quiet))
                else:
                    self.root.after(0, lambda: self._finished(success, result))

            threading.Thread(target=worker, daemon=True).start()

        def _finished(self, success, result) -> None:
            self._set_idle()
            success(result)

        def _failed(self, details: str, quiet: bool) -> None:
            self._set_idle()
            self._set_status(details, "error" if not quiet else "info")
            if not quiet:
                messagebox.showerror(APP_NAME, details, parent=self.root)

        def _succeeded(self, _title: str, details: str) -> None:
            self._set_status(details.splitlines()[0], "success")

        def _set_status(self, details: str, kind: str = "info") -> None:
            self.status.set(details)
            style = {
                "success": "Success.Status.TLabel",
                "error": "Error.Status.TLabel",
            }.get(kind, "Info.Status.TLabel")
            self.status_label.configure(style=style)

        def _set_controls(self, enabled: bool) -> None:
            state = "normal" if enabled else "disabled"
            self.inject_button.configure(state=state)
            self.restore_button.configure(state=state)
            self.location.configure(state=state)
            self.browse_button.configure(state=state)
            for button in self.order_buttons:
                button.configure(state=state)

        def _set_idle(self) -> None:
            self.busy = False
            self._set_controls(True)

    enable_windows_high_dpi()
    root = tk.Tk()
    Application(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
