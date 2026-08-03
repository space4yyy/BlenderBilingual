#!/usr/bin/env python3
"""Small native-style GUI for injecting Blender bilingual translations."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from scripts.bilingual import (
    BilingualError,
    LANGUAGE_CODE,
    ORDER_EN_ZH,
    ORDER_ZH_EN,
    blender_layout,
    build_from_source,
    discover_blender_installations,
    install_pack,
    parse_version,
    set_blender_language,
    uninstall_pack,
    verify_pack,
)


APP_NAME = "Blender 双语工具"


def requires_macos_admin(_blender: Path, datafiles: Path) -> bool:
    if sys.platform != "darwin":
        return False
    locale_root = datafiles / "locale"
    languages = locale_root / "languages"
    languages_target = languages if languages.exists() else locale_root
    return not os.access(locale_root, os.W_OK) or not os.access(languages_target, os.W_OK)


def prepare_macos_backup(datafiles: Path, version: str) -> Path | None:
    if sys.platform != "darwin":
        return None
    destination = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Blender Bilingual"
        / "backups"
        / version
        / "languages"
    )
    if not destination.exists():
        locale_root = datafiles / "locale"
        legacy = locale_root / "languages.zh_HANS_Bilingual.backup"
        source = legacy if legacy.is_file() else locale_root / "languages"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return destination


def application_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


def run_macos_privileged(arguments: list[str]) -> str:
    """Run only the Blender installation-directory mutation as an administrator."""
    if sys.platform != "darwin":
        raise BilingualError("管理员授权流程仅适用于 macOS")
    fd, result_name = tempfile.mkstemp(prefix="blender-bilingual-result-", suffix=".json")
    os.close(fd)
    result_path = Path(result_name)
    try:
        command = [*application_command(), *arguments, "--result-file", str(result_path)]
        shell_command = shlex.join(command)
        escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
        script = f'do shell script "{escaped}" with administrator privileges'
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if completed.returncode != 0:
            try:
                failed_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                failed_payload = None
            if failed_payload and not failed_payload.get("ok"):
                raise BilingualError(str(failed_payload.get("error", "管理员辅助进程执行失败")))
            details = (completed.stderr or completed.stdout).strip()
            if "User canceled" in details or "(-128)" in details:
                raise BilingualError("已取消管理员授权")
            raise BilingualError(f"管理员授权操作失败：{details or completed.returncode}")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BilingualError("管理员辅助进程没有返回有效结果") from exc
        if not payload.get("ok"):
            raise BilingualError(str(payload.get("error", "管理员辅助进程执行失败")))
        return str(payload.get("result", "操作完成"))
    finally:
        result_path.unlink(missing_ok=True)


def privileged_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--version")
    parser.add_argument("--packs-root", type=Path)
    parser.add_argument("--order", default=ORDER_ZH_EN)
    parser.add_argument("--backup-path", type=Path)
    parser.add_argument("--result-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "install":
            if args.version is None or args.packs_root is None:
                raise BilingualError("管理员安装缺少版本或临时语言包路径")
            result = install_pack(
                args.blender,
                args.version,
                False,
                args.packs_root,
                activate=False,
                order=args.order,
                backup_path=args.backup_path,
            )
        else:
            result = uninstall_pack(args.blender, False, reset_language=False)
        payload = {"ok": True, "result": result}
        exit_code = 0
    except (BilingualError, OSError) as exc:
        payload = {"ok": False, "error": str(exc)}
        exit_code = 2
    args.result_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return exit_code


def inject(blender: Path, order: str) -> str:
    """Build from the selected installation, inject it, and discard temporary files."""
    executable, datafiles, version = blender_layout(blender)
    official_mo = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
    if not official_mo.is_file():
        raise BilingualError(f"找不到 Blender 自带的官方简中语言包：{official_mo}")
    _version, resource_version = parse_version(version)
    backup_path = prepare_macos_backup(datafiles, version)
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
        if requires_macos_admin(blender, datafiles):
            privileged_arguments = [
                "--privileged-action",
                "install",
                "--blender",
                str(blender),
                "--version",
                version,
                "--packs-root",
                str(packs_root),
                "--order",
                order,
            ]
            if backup_path is not None:
                privileged_arguments.extend(["--backup-path", str(backup_path)])
            result = run_macos_privileged(privileged_arguments)
            try:
                set_blender_language(executable, LANGUAGE_CODE)
            except Exception:
                try:
                    run_macos_privileged(
                        ["--privileged-action", "uninstall", "--blender", str(blender)]
                    )
                except BilingualError:
                    pass
                raise
            return f"{result}，已设为当前用户语言"
        return install_pack(
            blender,
            version,
            False,
            packs_root,
            activate=True,
            order=order,
            backup_path=backup_path,
        )


def restore(blender: Path) -> str:
    executable, datafiles, version = blender_layout(blender)
    if requires_macos_admin(blender, datafiles):
        set_blender_language(executable, "zh_HANS")
        result = run_macos_privileged(
            ["--privileged-action", "uninstall", "--blender", str(blender)]
        )
        return f"{result}；Blender {version} 已切回官方简中"
    return uninstall_pack(blender, False, reset_language=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--privileged-action"]:
        return privileged_main(argv[1:])
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
                if sys.platform == "darwin" and "Operation not permitted" in details:
                    hint = (
                        "\n\nmacOS 已阻止本工具修改 Blender。请打开“系统设置 → 隐私与安全性 → "
                        "应用管理”，允许 BlenderBilingual，然后重试。"
                    )
                elif os.name == "nt":
                    hint = "\n\n若安装在受保护目录，请以管理员身份运行本工具。"
                else:
                    hint = ""
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
