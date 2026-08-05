from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from blender_bilingual_gui import blender_process_running, enable_windows_high_dpi, inject, restore
from scripts.bilingual import MOCatalog, MOEntry, ORDER_EN_ZH


class GUIBackendTests(unittest.TestCase):
    def test_inject_builds_selected_order_then_uses_normal_user_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles = root / "5.2" / "datafiles"
            official = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
            official.parent.mkdir(parents=True)
            official.write_bytes(
                MOCatalog(
                    (
                        MOEntry("", "Content-Type: text/plain; charset=UTF-8\n"),
                        MOEntry("File", "文件"),
                    )
                ).to_bytes()
            )
            layout = (root / "blender", datafiles, "5.2.0")

            def inspect_install(_blender, version, _dry_run, packs_root, **kwargs):
                self.assertEqual("5.2.0", version)
                self.assertEqual(ORDER_EN_ZH, kwargs["order"])
                self.assertTrue(kwargs["activate"])
                output = (
                    packs_root
                    / "5.2.0"
                    / "zh_HANS@bilingual"
                    / "LC_MESSAGES"
                    / "blender.mo"
                )
                values = {
                    entry.original: entry.translation
                    for entry in MOCatalog.read(output).entries
                }
                self.assertEqual("File 文件", values["File"])
                return "ok"

            with (
                mock.patch("blender_bilingual_gui.blender_layout", return_value=layout),
                mock.patch("blender_bilingual_gui.install_pack", side_effect=inspect_install) as install,
            ):
                self.assertEqual("ok", inject(root, ORDER_EN_ZH))
            install.assert_called_once()

    def test_restore_uses_user_level_uninstall_and_resets_language(self) -> None:
        blender = Path("/Applications/Blender.app")
        with mock.patch(
            "blender_bilingual_gui.uninstall_pack", return_value="已还原"
        ) as uninstall:
            self.assertEqual("已还原", restore(blender))
        uninstall.assert_called_once_with(blender, False, reset_language=True)

    def test_gui_contains_no_privileged_helper(self) -> None:
        source = Path("blender_bilingual_gui.py").read_text(encoding="utf-8")
        self.assertNotIn("administrator privileges", source)
        self.assertNotIn("--privileged-action", source)
        self.assertNotIn("osascript", source)

    def test_gui_has_no_inline_confirmation_panel(self) -> None:
        source = Path("blender_bilingual_gui.py").read_text(encoding="utf-8")
        self.assertNotIn("askokcancel", source)
        self.assertNotIn("_request_confirmation", source)
        self.assertNotIn("confirm_frame", source)
        self.assertNotIn("ttk.Progressbar", source)
        self.assertIn("winfo_reqheight", source)

    def test_macos_blender_process_detection_uses_exact_process_name(self) -> None:
        completed = mock.Mock(returncode=0, stdout="123\n", stderr="")
        with mock.patch("blender_bilingual_gui.subprocess.run", return_value=completed) as run:
            self.assertTrue(blender_process_running("darwin"))
        self.assertEqual(["pgrep", "-x", "Blender"], run.call_args.args[0])

    def test_windows_blender_process_detection_handles_no_match(self) -> None:
        completed = mock.Mock(returncode=0, stdout="INFO: No tasks are running", stderr="")
        with mock.patch("blender_bilingual_gui.subprocess.run", return_value=completed):
            self.assertFalse(blender_process_running("win32"))

    def test_high_dpi_setup_is_a_noop_outside_windows(self) -> None:
        enable_windows_high_dpi("darwin")


if __name__ == "__main__":
    unittest.main()
