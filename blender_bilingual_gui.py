#!/usr/bin/env python3
"""Small native-style GUI for injecting Blender bilingual translations."""

from __future__ import annotations

import os
import sys
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
        return install_pack(blender, version, False, packs_root, activate=True, order=order)


def restore(blender: Path) -> str:
    return uninstall_pack(blender, False, reset_language=True)


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        print("当前 Python 未包含 Tk 图形界面支持。请使用已打包的应用。", file=sys.stderr)
        return 2

    class Application:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title(APP_NAME)
            self.root.resizable(False, False)
            self.path = tk.StringVar()
            self.order = tk.StringVar(value=ORDER_ZH_EN)
            self.status = tk.StringVar(value="正在查找本机 Blender…")
            self.busy = False
            self._build_ui()
            self.root.after(80, self._discover)

        def _build_ui(self) -> None:
            frame = ttk.Frame(self.root, padding=20)
            frame.grid(sticky="nsew")

            ttk.Label(frame, text="Blender 双语工具", font=("TkDefaultFont", 18, "bold")).grid(
                row=0, column=0, columnspan=3, sticky="w"
            )
            ttk.Label(frame, text="从 Blender 自带语言生成双语界面，不覆盖官方简中。", foreground="#666666").grid(
                row=1, column=0, columnspan=3, sticky="w", pady=(4, 18)
            )

            ttk.Label(frame, text="Blender 位置").grid(row=2, column=0, columnspan=3, sticky="w")
            self.location = ttk.Combobox(frame, textvariable=self.path, width=58)
            self.location.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
            self.location.bind("<<ComboboxSelected>>", lambda _event: self._check_selection())
            self.location.bind("<FocusOut>", lambda _event: self._check_selection())
            ttk.Button(frame, text="手动选择…", command=self._browse).grid(
                row=3, column=2, padx=(8, 0), pady=(5, 0)
            )

            options = ttk.LabelFrame(frame, text="显示顺序", padding=12)
            options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(18, 0))
            ttk.Radiobutton(options, text="中 - 英", variable=self.order, value=ORDER_ZH_EN).grid(
                row=0, column=0, padx=(2, 30), sticky="w"
            )
            ttk.Radiobutton(options, text="英 - 中", variable=self.order, value=ORDER_EN_ZH).grid(
                row=0, column=1, sticky="w"
            )

            self.progress = ttk.Progressbar(frame, mode="indeterminate", length=460)
            self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(18, 5))
            ttk.Label(frame, textvariable=self.status, foreground="#555555", wraplength=530).grid(
                row=6, column=0, columnspan=3, sticky="w"
            )

            actions = ttk.Frame(frame)
            actions.grid(row=7, column=0, columnspan=3, sticky="e", pady=(20, 0))
            self.restore_button = ttk.Button(actions, text="还原官方简中", command=self._restore)
            self.restore_button.grid(row=0, column=0, padx=(0, 8))
            self.inject_button = ttk.Button(actions, text="注入并启用", command=self._inject)
            self.inject_button.grid(row=0, column=1)

        def _discover(self) -> None:
            paths = discover_blender_installations()
            values = [str(path) for path in paths]
            self.location.configure(values=values)
            if values:
                self.path.set(values[0])
                self._check_selection()
            else:
                self.status.set("未自动找到 Blender，请手动选择安装目录或可执行文件。")

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
                lambda result: self.status.set(f"已找到 Blender {result[2]}"),
                quiet=True,
            )

        def _inject(self) -> None:
            try:
                blender = self._selected_path()
            except BilingualError as exc:
                messagebox.showerror(APP_NAME, str(exc))
                return
            label = "中 - 英" if self.order.get() == ORDER_ZH_EN else "英 - 中"
            if not messagebox.askokcancel(
                "确认注入",
                f"请先关闭 Blender。\n\n将注入“{label}”语言并设为当前语言，是否继续？",
                icon="warning",
            ):
                return
            self.status.set("正在生成、校验并注入双语语言…")
            self._run(
                lambda: inject(blender, self.order.get()),
                lambda result: self._succeeded("注入完成", result + "\n\n重新打开 Blender 即可使用。"),
            )

        def _restore(self) -> None:
            try:
                blender = self._selected_path()
            except BilingualError as exc:
                messagebox.showerror(APP_NAME, str(exc))
                return
            if not messagebox.askokcancel(
                "确认还原",
                "请先关闭 Blender。\n\n将切回官方简中并移除本工具注入的语言，是否继续？",
                icon="warning",
            ):
                return
            self.status.set("正在还原官方简中…")
            self._run(lambda: restore(blender), lambda result: self._succeeded("还原完成", result))

        def _run(self, work, success, quiet: bool = False) -> None:
            if self.busy:
                return
            self.busy = True
            self._set_controls(False)
            self.progress.start(12)

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
            self.status.set(details)
            if not quiet:
                hint = "\n\n若安装在受保护目录，请以管理员身份运行本工具。" if os.name == "nt" else ""
                messagebox.showerror(APP_NAME, details + hint)

        def _succeeded(self, title: str, details: str) -> None:
            self.status.set(details.splitlines()[0])
            messagebox.showinfo(title, details)

        def _set_controls(self, enabled: bool) -> None:
            state = "normal" if enabled else "disabled"
            self.inject_button.configure(state=state)
            self.restore_button.configure(state=state)
            self.location.configure(state=state)

        def _set_idle(self) -> None:
            self.busy = False
            self.progress.stop()
            self._set_controls(True)

    root = tk.Tk()
    Application(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
