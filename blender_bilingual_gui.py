#!/usr/bin/env python3
"""Desktop GUI for managing Blender bilingual translations."""

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
            self.path = tk.StringVar()
            self.order = tk.StringVar(value=ORDER_ZH_EN)
            self.status = tk.StringVar(value="正在查找本机 Blender…")
            self.busy = False
            self._configure_style()
            self._build_ui()
            self.path.trace_add("write", self._path_changed)
            self._set_controls(False)
            self.root.update_idletasks()
            self.root.minsize(520, self.root.winfo_reqheight())
            self.root.after_idle(self._discover)

        def _configure_style(self) -> None:
            style = ttk.Style(self.root)
            style.theme_use("clam")

            body = "#f3f5f7"
            surface = "#ffffff"
            ink = "#202731"
            border = "#abb6c2"
            header = "#293541"
            footer = "#e8edf2"
            accent = "#a44220"
            focus = "#284f7a"

            default_font = tkfont.nametofont("TkDefaultFont")
            if sys.platform == "win32":
                default_font.configure(family="Segoe UI", size=10)
                tkfont.nametofont("TkTextFont").configure(family="Segoe UI", size=10)
            family = default_font.cget("family")
            title_font = (family, 22, "bold")
            section_font = (family, default_font.cget("size"), "bold")
            example_font = (family, 15, "bold")

            style.configure("TFrame", background=body)
            style.configure("TLabel", background=body, foreground=ink)
            style.configure("Header.TFrame", background=header)
            style.configure("Title.TLabel", background=header, foreground=surface, font=title_font)
            style.configure("Subtitle.TLabel", background=header, foreground="#d3dce5")
            style.configure("Section.TLabel", font=section_font)
            style.configure("Footer.TFrame", background=footer)
            style.configure("Status.TLabel", background=footer, foreground="#3c4e60")
            style.configure("Success.Status.TLabel", foreground="#1c6247")
            style.configure("Warning.Status.TLabel", foreground="#785019")
            style.configure("Error.Status.TLabel", foreground="#a32a22")

            style.configure("TCombobox", padding=(8, 6), fieldbackground=surface,
                            background=surface, foreground=ink, arrowcolor=ink,
                            bordercolor=border, lightcolor=surface, darkcolor=surface)
            style.map("TCombobox", bordercolor=[("focus", focus)],
                      fieldbackground=[("disabled", footer)],
                      foreground=[("disabled", "#566575")],
                      background=[("active", footer), ("pressed", footer)])

            style.configure("Preview.TFrame", background=surface, relief="solid", borderwidth=1,
                            bordercolor=border, lightcolor=surface, darkcolor=surface)
            style.configure("Preview.TLabel", background=surface, font=example_font)
            style.configure("TRadiobutton", background=surface, foreground=ink,
                            indicatorforeground=accent, indicatorbackground=surface,
                            upperbordercolor=border, lowerbordercolor=border,
                            focuscolor=focus, padding=(0, 2))

            style.configure("TButton", padding=(13, 8), foreground=ink, background=surface,
                            bordercolor=border, lightcolor=surface, darkcolor=surface,
                            focuscolor=focus)
            style.map("TButton", background=[("disabled", footer), ("pressed", "#d8e0e8"),
                                             ("active", body)],
                      foreground=[("disabled", "#566575")], bordercolor=[("focus", focus)],
                      lightcolor=[], darkcolor=[])
            style.configure("Primary.TButton", padding=(18, 8), font=section_font,
                            foreground=surface, background=accent, bordercolor=accent,
                            lightcolor=accent, darkcolor=accent, focuscolor=surface)
            style.map("Primary.TButton", background=[("disabled", "#d8e0e8"),
                                                     ("pressed", "#773016"), ("active", "#8b371b")],
                      foreground=[("disabled", "#566575")],
                      bordercolor=[("disabled", border), ("focus", focus)])

        def _build_ui(self) -> None:
            header = ttk.Frame(self.root, padding=(24, 18), style="Header.TFrame")
            header.grid(row=0, column=0, sticky="ew")
            ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(sticky="w")
            ttk.Label(header, text="为 Blender 界面添加简中和英文。", style="Subtitle.TLabel").grid(
                sticky="w", pady=(4, 0)
            )

            body = ttk.Frame(self.root, padding=(24, 20))
            body.grid(row=1, column=0, sticky="nsew")
            body.columnconfigure(0, weight=1)
            self.root.rowconfigure(1, weight=1)

            location_label = ttk.Label(body, text="Blender 安装位置", style="Section.TLabel")
            location_label.grid(sticky="w")
            location_row = ttk.Frame(body)
            location_row.grid(sticky="ew", pady=(8, 0))
            location_row.columnconfigure(0, weight=1)
            self.location = ttk.Combobox(location_row, textvariable=self.path, width=44)
            self.location.grid(row=0, column=0, sticky="ew")
            self.location.bind("<<ComboboxSelected>>", self._check_selection)
            self.location.bind("<Return>", self._check_selection)
            self.browse_button = ttk.Button(location_row, text="手动选择…", command=self._browse)
            self.browse_button.grid(row=0, column=1, padx=(10, 0), sticky="ns")

            ttk.Label(body, text="显示顺序", style="Section.TLabel").grid(sticky="w", pady=(20, 8))
            options = ttk.Frame(body)
            options.grid(sticky="ew")
            options.columnconfigure((0, 1), weight=1, uniform="order")
            self.order_buttons = (
                self._order_option(options, 0, "中 - 英", "文件 File", ORDER_ZH_EN),
                self._order_option(options, 1, "英 - 中", "File 文件", ORDER_EN_ZH),
            )

            footer = ttk.Frame(self.root, padding=(24, 14), style="Footer.TFrame")
            footer.grid(row=2, column=0, sticky="ew")
            footer.columnconfigure(0, weight=1)
            footer.rowconfigure(0, minsize=40)
            self.status_label = ttk.Label(footer, textvariable=self.status, style="Status.TLabel",
                                          wraplength=472)
            self.status_label.grid(row=0, column=0, columnspan=2, sticky="nw")
            footer.bind("<Configure>", lambda event: self.status_label.configure(
                wraplength=max(1, event.width - 48)
            ))
            self.restore_button = ttk.Button(footer, text="还原", width=7, command=self._restore)
            self.restore_button.grid(row=1, column=0, sticky="e", padx=(0, 8))
            self.inject_button = ttk.Button(
                footer, text="注入并启用", style="Primary.TButton", command=self._inject
            )
            self.inject_button.grid(row=1, column=1, sticky="e")

        def _order_option(self, parent, column: int, label: str, example: str, order: str):
            panel = ttk.Frame(parent, padding=(12, 8), style="Preview.TFrame")
            panel.grid(row=0, column=column, sticky="ew", padx=(0, 5) if column == 0 else (5, 0))
            button = ttk.Radiobutton(panel, text=label, variable=self.order, value=order)
            button.grid(sticky="w")
            preview = ttk.Label(panel, text=example, style="Preview.TLabel")
            preview.grid(sticky="w", padx=(18, 0), pady=(4, 0))

            def select(_event) -> None:
                if not button.instate(("disabled",)):
                    button.focus_set()
                    button.invoke()

            panel.bind("<Button-1>", select)
            preview.bind("<Button-1>", select)
            return button

        def _discover(self) -> None:
            self._run(discover_blender_installations, self._set_discovered, quiet=True)

        def _set_discovered(self, paths: list[Path]) -> None:
            values = [str(path) for path in paths]
            self.location.configure(values=values)
            if values:
                self.path.set(values[0])
                self._check_selection()
            else:
                self._set_status("未找到 Blender。请选择安装位置，或粘贴路径。")

        def _browse(self) -> None:
            if sys.platform == "darwin":
                selected = filedialog.askopenfilename(
                    title="选择 Blender.app",
                    initialdir="/Applications",
                    filetypes=(("Blender 应用", "*.app"), ("所有文件", "*.*")),
                    parent=self.root,
                )
            elif sys.platform == "win32":
                selected = filedialog.askopenfilename(
                    title="选择 blender.exe",
                    filetypes=(("Blender", "blender.exe"), ("所有文件", "*.*")),
                    parent=self.root,
                )
            else:
                selected = filedialog.askopenfilename(
                    title="选择 Blender 可执行文件", parent=self.root
                )
            if selected:
                self.path.set(selected)
                self._check_selection()

        def _selected_path(self) -> Path | None:
            value = self.path.get().strip().strip('"')
            return Path(value) if value.strip() else None

        def _path_changed(self, *_args) -> None:
            if self.busy:
                return
            self._set_controls(True)
            if self._selected_path() is None:
                self._set_status("请选择 Blender 安装位置，或粘贴路径。")
            else:
                self._set_status("按 Enter 检查 Blender 版本。")

        def _check_selection(self, _event=None) -> None:
            blender = self._selected_path()
            if self.busy or blender is None:
                return
            self._set_status("正在检查 Blender 版本…")
            self._run(
                lambda: blender_layout(blender),
                lambda result: self._set_status(f"已找到 Blender {result[2]}"),
                quiet=True,
            )

        def _inject(self) -> None:
            order = self.order.get()
            self._run_action(
                lambda blender: inject(blender, order),
                "正在生成并启用双语语言…",
                "双语语言已启用。重新打开 Blender 即可使用。",
            )

        def _restore(self) -> None:
            self._run_action(
                restore,
                "正在切回官方简中…",
                "已切回官方简中。重新打开 Blender 即可使用。",
            )

        def _run_action(self, action, pending: str, done: str) -> None:
            blender = self._selected_path()
            if self.busy or blender is None:
                return
            self._set_status(pending)

            def work() -> bool:
                if blender_process_running():
                    return False
                action(blender)
                return True

            def finish(applied: bool) -> None:
                if applied:
                    self._set_status(done, "success")
                else:
                    warning = "检测到 Blender 正在运行。请退出 Blender 后重试。"
                    self._set_status(warning, "warning")
                    messagebox.showwarning(APP_NAME, warning, parent=self.root)

            self._run(work, finish)

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
            self._set_status(details, "error")
            if not quiet:
                messagebox.showerror(APP_NAME, details, parent=self.root)

        def _set_status(self, details: str, kind: str = "info") -> None:
            self.status.set(details)
            style = "Status.TLabel" if kind == "info" else f"{kind.title()}.Status.TLabel"
            self.status_label.configure(style=style)

        def _set_controls(self, enabled: bool) -> None:
            state = "normal" if enabled else "disabled"
            action_state = state if self._selected_path() is not None else "disabled"
            self.inject_button.configure(state=action_state)
            self.restore_button.configure(state=action_state)
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
