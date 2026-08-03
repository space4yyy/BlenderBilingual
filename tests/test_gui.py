from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

from blender_bilingual_gui import inject, prepare_macos_backup, privileged_main, restore
from scripts.bilingual import BilingualError, LANGUAGE_CODE, MOCatalog, MOEntry, ORDER_EN_ZH


class GUIBackendTests(unittest.TestCase):
    def test_inject_builds_selected_order_from_local_official_mo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles = root / "5.2" / "datafiles"
            official = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
            official.parent.mkdir(parents=True)
            official.write_bytes(
                MOCatalog((MOEntry("", "Content-Type: text/plain; charset=UTF-8\n"), MOEntry("File", "文件"))).to_bytes()
            )
            layout = (root / "blender", datafiles, "5.2.0")

            def inspect_install(_blender, version, _dry_run, packs_root, **kwargs):
                self.assertEqual("5.2.0", version)
                self.assertEqual(ORDER_EN_ZH, kwargs["order"])
                output = packs_root / "5.2.0" / "zh_HANS@bilingual" / "LC_MESSAGES" / "blender.mo"
                values = {entry.original: entry.translation for entry in MOCatalog.read(output).entries}
                self.assertEqual("File 文件", values["File"])
                return "ok"

            with (
                mock.patch("blender_bilingual_gui.blender_layout", return_value=layout),
                mock.patch("blender_bilingual_gui.prepare_macos_backup", return_value=None),
                mock.patch("blender_bilingual_gui.install_pack", side_effect=inspect_install),
            ):
                self.assertEqual("ok", inject(root, ORDER_EN_ZH))

    def test_protected_macos_install_elevates_only_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles = root / "5.2" / "datafiles"
            official = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
            official.parent.mkdir(parents=True)
            official.write_bytes(
                MOCatalog((MOEntry("", "Content-Type: text/plain; charset=UTF-8\n"),)).to_bytes()
            )
            executable = root / "Blender"
            layout = (executable, datafiles, "5.2.0")
            with (
                mock.patch("blender_bilingual_gui.blender_layout", return_value=layout),
                mock.patch("blender_bilingual_gui.prepare_macos_backup", return_value=None),
                mock.patch("blender_bilingual_gui.requires_macos_admin", return_value=True),
                mock.patch(
                    "blender_bilingual_gui.run_macos_privileged", return_value="已安装文件"
                ) as privileged,
                mock.patch("blender_bilingual_gui.set_blender_language") as activate,
                mock.patch("blender_bilingual_gui.install_pack") as direct_install,
            ):
                result = inject(root, ORDER_EN_ZH)
            self.assertIn("已设为当前用户语言", result)
            privileged.assert_called_once()
            direct_install.assert_not_called()
            activate.assert_called_once_with(executable, LANGUAGE_CODE)

    def test_protected_macos_restore_resets_user_before_elevated_removal(self) -> None:
        blender = Path("/Applications/Blender.app")
        executable = blender / "Contents" / "MacOS" / "Blender"
        datafiles = blender / "Contents" / "Resources" / "5.2" / "datafiles"
        calls: list[str] = []
        with (
            mock.patch(
                "blender_bilingual_gui.blender_layout",
                return_value=(executable, datafiles, "5.2.0"),
            ),
            mock.patch("blender_bilingual_gui.requires_macos_admin", return_value=True),
            mock.patch(
                "blender_bilingual_gui.set_blender_language",
                side_effect=lambda *_args: calls.append("preference"),
            ),
            mock.patch(
                "blender_bilingual_gui.run_macos_privileged",
                side_effect=lambda *_args: calls.append("files") or "已移除文件",
            ),
            mock.patch("blender_bilingual_gui.uninstall_pack") as direct_uninstall,
        ):
            result = restore(blender)
        self.assertEqual(["preference", "files"], calls)
        self.assertIn("官方简中", result)
        direct_uninstall.assert_not_called()

    def test_activation_failure_rolls_back_privileged_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles = root / "5.2" / "datafiles"
            official = datafiles / "locale" / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
            official.parent.mkdir(parents=True)
            official.write_bytes(
                MOCatalog((MOEntry("", "Content-Type: text/plain; charset=UTF-8\n"),)).to_bytes()
            )
            layout = (root / "Blender", datafiles, "5.2.0")
            with (
                mock.patch("blender_bilingual_gui.blender_layout", return_value=layout),
                mock.patch("blender_bilingual_gui.prepare_macos_backup", return_value=None),
                mock.patch("blender_bilingual_gui.requires_macos_admin", return_value=True),
                mock.patch(
                    "blender_bilingual_gui.run_macos_privileged",
                    side_effect=("已安装文件", "已回滚文件"),
                ) as privileged,
                mock.patch(
                    "blender_bilingual_gui.set_blender_language",
                    side_effect=RuntimeError("activation failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "activation failed"):
                    inject(root, ORDER_EN_ZH)
            self.assertEqual(2, privileged.call_count)
            self.assertEqual("uninstall", privileged.call_args_list[1].args[0][1])

    def test_macos_backup_migrates_legacy_backup_outside_app(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles = root / "Blender.app" / "Contents" / "Resources" / "5.2" / "datafiles"
            locale = datafiles / "locale"
            locale.mkdir(parents=True)
            (locale / "languages").write_text("current", encoding="utf-8")
            (locale / "languages.zh_HANS_Bilingual.backup").write_text(
                "official", encoding="utf-8"
            )
            with (
                mock.patch("blender_bilingual_gui.sys.platform", "darwin"),
                mock.patch("blender_bilingual_gui.Path.home", return_value=root / "home"),
            ):
                backup = prepare_macos_backup(datafiles, "5.2.0")
            self.assertIsNotNone(backup)
            self.assertEqual("official", backup.read_text(encoding="utf-8"))
            self.assertNotIn("Blender.app", str(backup))

    def test_privileged_helper_never_activates_root_user_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result_file = Path(temporary) / "result.json"
            with mock.patch("blender_bilingual_gui.install_pack", return_value="已安装") as install:
                exit_code = privileged_main(
                    [
                        "install",
                        "--blender",
                        "/Applications/Blender.app",
                        "--version",
                        "5.2.0",
                        "--packs-root",
                        temporary,
                        "--order",
                        ORDER_EN_ZH,
                        "--result-file",
                        str(result_file),
                    ]
                )
            self.assertEqual(0, exit_code)
            self.assertTrue(json.loads(result_file.read_text(encoding="utf-8"))["ok"])
            self.assertFalse(install.call_args.kwargs["activate"])

    def test_privileged_helper_returns_backend_error_to_gui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result_file = Path(temporary) / "result.json"
            with mock.patch(
                "blender_bilingual_gui.uninstall_pack",
                side_effect=BilingualError("无法修改测试目录"),
            ):
                exit_code = privileged_main(
                    [
                        "uninstall",
                        "--blender",
                        "/Applications/Blender.app",
                        "--result-file",
                        str(result_file),
                    ]
                )
            payload = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(2, exit_code)
            self.assertFalse(payload["ok"])
            self.assertEqual("无法修改测试目录", payload["error"])


if __name__ == "__main__":
    unittest.main()
