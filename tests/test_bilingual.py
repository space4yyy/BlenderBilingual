from __future__ import annotations

import gettext
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.bilingual import (
    BilingualError,
    LANGUAGE_CODE,
    MANAGED_BEGIN,
    MANAGED_END,
    MOCatalog,
    MOEntry,
    bilingual_translation,
    build_from_source,
    expected_checksum,
    extract_official_mo,
    has_dynamic_placeholder,
    install_pack,
    output_entry_is_dynamic,
    pack_paths,
    set_blender_language,
    transform_catalog,
    uninstall_pack,
    verify_pack,
)


HEADER = (
    "Project-Id-Version: test\n"
    "Content-Type: text/plain; charset=UTF-8\n"
    "Plural-Forms: nplurals=2; plural=(n != 1);\n"
)


def fixture_catalog() -> MOCatalog:
    return MOCatalog(
        (
            MOEntry("", HEADER),
            MOEntry("File", "文件"),
            MOEntry("Same", "Same"),
            MOEntry("Fallback", ""),
            MOEntry("Action\x04Play", "播放"),
            MOEntry("Line one\nLine two", "第一行\n第二行"),
            MOEntry("%d item\0%d items", "%d 项\0%d 项"),
            MOEntry("Value {name}", "值 {name}"),
        )
    )


class MOTests(unittest.TestCase):
    def test_roundtrip_preserves_context_plural_and_unicode(self) -> None:
        source = fixture_catalog()
        data = source.to_bytes()
        parsed = MOCatalog.read(data)
        self.assertEqual(
            {entry.original: entry.translation for entry in source.entries},
            {entry.original: entry.translation for entry in parsed.entries},
        )

        translations = gettext.GNUTranslations(fp=io.BytesIO(data))
        self.assertEqual("文件", translations.gettext("File"))
        self.assertEqual("播放", translations.pgettext("Action", "Play"))
        self.assertEqual("%d 项", translations.ngettext("%d item", "%d items", 2))

    def test_invalid_mo_is_rejected(self) -> None:
        with self.assertRaises(BilingualError):
            MOCatalog.read(b"not-an-mo")

    def test_transform_rules(self) -> None:
        transformed, stats = transform_catalog(fixture_catalog())
        values = {entry.original: entry.translation for entry in transformed.entries}
        self.assertEqual("文件 File", values["File"])
        self.assertEqual("Same", values["Same"])
        self.assertEqual("Fallback", values["Fallback"])
        self.assertEqual("播放 Play", values["Action\x04Play"])
        self.assertEqual("第一行\n第二行 Line one\nLine two", values["Line one\nLine two"])
        self.assertEqual("%d 项\0%d 项", values["%d item\0%d items"])
        self.assertEqual("值 {name}", values["Value {name}"])
        self.assertEqual(1, stats["contexts"])
        self.assertEqual(1, stats["plurals"])
        self.assertEqual(2, stats["dynamic"])

    def test_placeholder_detection_and_escapes(self) -> None:
        dynamic = ("%s", "%03d", "%(name)s", "%2$.*3$f", "%zu", "{}", "{name}", "{0:.2f}")
        static = ("100%%", "{{name}}", "plain text", "百分比 100%")
        for value in dynamic:
            with self.subTest(value=value):
                self.assertTrue(has_dynamic_placeholder(value))
        for value in static:
            with self.subTest(value=value):
                self.assertFalse(has_dynamic_placeholder(value))

    def test_header_is_never_transformed(self) -> None:
        translated, rule = bilingual_translation("", HEADER)
        self.assertEqual(HEADER, translated)
        self.assertEqual("header", rule)

    def test_output_dynamic_check_ignores_appended_percentage_prose(self) -> None:
        entry = MOEntry(
            "Locale code: ab. Translation progress: 0%",
            "区域代码: ab. 翻译进度: 0% Locale code: ab. Translation progress: 0%",
        )
        self.assertFalse(output_entry_is_dynamic(entry))
        self.assertTrue(output_entry_is_dynamic(MOEntry("Value: %s", "值：%s")))


class BuildTests(unittest.TestCase):
    def test_build_and_verify_without_po(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "official.mo"
            source.write_bytes(fixture_catalog().to_bytes())
            packs = root / "packs"
            output, manifest_path = build_from_source(
                source,
                "5.1.2",
                "5.1",
                {"type": "provided_mo"},
                packs,
            )
            self.assertTrue(output.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertFalse(any(root.rglob("*.po")))
            manifest = verify_pack("5.1.2", packs)
            self.assertEqual("5.1.2", manifest["blender_version"])
            self.assertEqual(7, manifest["output"]["messages"])

    def test_verify_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "official.mo"
            source.write_bytes(fixture_catalog().to_bytes())
            packs = root / "packs"
            output, _manifest = build_from_source(
                source, "4.4.3", "4.4", {"type": "provided_mo"}, packs
            )
            output.write_bytes(output.read_bytes() + b"x")
            with self.assertRaises(BilingualError):
                verify_pack("4.4.3", packs)


class ArchiveTests(unittest.TestCase):
    def test_extracts_only_expected_mo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "blender.tar.xz"
            payload = fixture_catalog().to_bytes()
            with tarfile.open(archive, "w:xz") as bundle:
                member = tarfile.TarInfo(
                    "blender-4.4.3-linux-x64/4.4/datafiles/locale/zh_HANS/LC_MESSAGES/blender.mo"
                )
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))
                hostile = tarfile.TarInfo("../../outside")
                hostile.size = 4
                bundle.addfile(hostile, io.BytesIO(b"nope"))
            destination = root / "result" / "blender.mo"
            extract_official_mo(archive, "4.4.3", destination)
            self.assertEqual(payload, destination.read_bytes())
            self.assertFalse((root.parent / "outside").exists())

    def test_rejects_missing_expected_mo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "empty.tar.xz"
            with tarfile.open(archive, "w:xz"):
                pass
            with self.assertRaises(BilingualError):
                extract_official_mo(archive, "4.4.3", Path(temporary) / "out.mo")

    def test_checksum_file_parsing(self) -> None:
        digest = "a" * 64
        self.assertEqual(digest, expected_checksum(f"{digest}  blender.tar.xz\n", "blender.tar.xz"))


class InstallTests(unittest.TestCase):
    def prepare(self, root: Path) -> tuple[Path, Path]:
        datafiles = root / "app-data" / "5.1" / "datafiles"
        locale = datafiles / "locale"
        locale.mkdir(parents=True)
        (locale / "languages").write_text(
            "# languages\n1:English (US):en_US:100%\n60:Occupied:test:100%\n", encoding="utf-8"
        )
        source = root / "official.mo"
        source.write_bytes(fixture_catalog().to_bytes())
        packs = root / "packs"
        build_from_source(source, "5.1.2", "5.1", {"type": "provided_mo"}, packs)
        return datafiles, packs

    def prepare_without_pack(self, root: Path) -> tuple[Path, Path]:
        datafiles = root / "app-data" / "5.2" / "datafiles"
        locale = datafiles / "locale"
        official = locale / "zh_HANS" / "LC_MESSAGES" / "blender.mo"
        official.parent.mkdir(parents=True)
        official.write_bytes(fixture_catalog().to_bytes())
        (locale / "languages").write_text(
            "# languages\n1:English (US):en_US:100%\n", encoding="utf-8"
        )
        return datafiles, root / "packs"

    def test_install_builds_missing_pack_from_local_blender(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles, packs = self.prepare_without_pack(root)
            layout = (root / "blender", datafiles, "5.2.0")
            with mock.patch("scripts.bilingual.blender_layout", return_value=layout):
                result = install_pack(root / "Blender.app", None, False, packs, activate=False)
            output, manifest = pack_paths("5.2.0", packs)
            self.assertTrue(output.is_file())
            self.assertTrue(manifest.is_file())
            self.assertIn("已自动生成", result)
            self.assertTrue(
                (datafiles / "locale" / LANGUAGE_CODE / "LC_MESSAGES" / "blender.mo").is_file()
            )

    def test_install_dry_run_reports_missing_pack_without_building(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles, packs = self.prepare_without_pack(root)
            layout = (root / "blender", datafiles, "5.2.0")
            with mock.patch("scripts.bilingual.blender_layout", return_value=layout):
                result = install_pack(root / "Blender.app", None, True, packs, activate=False)
            output, manifest = pack_paths("5.2.0", packs)
            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())
            self.assertIn("将先从本地 Blender 自动生成", result)

    def test_install_does_not_overwrite_partial_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles, packs = self.prepare_without_pack(root)
            _output, manifest = pack_paths("5.2.0", packs)
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}\n", encoding="utf-8")
            layout = (root / "blender", datafiles, "5.2.0")
            with mock.patch("scripts.bilingual.blender_layout", return_value=layout):
                with self.assertRaisesRegex(BilingualError, "找不到 5.2.0"):
                    install_pack(root / "Blender.app", None, False, packs, activate=False)

    def test_install_is_idempotent_and_uninstall_is_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles, packs = self.prepare(root)
            layout = (root / "blender", datafiles, "5.1.2")
            with mock.patch("scripts.bilingual.blender_layout", return_value=layout):
                first = install_pack(root / "Blender.app", None, False, packs, activate=False)
                second = install_pack(root / "Blender.app", None, False, packs, activate=False)
                self.assertIn("语言 ID 61", first)
                self.assertIn("语言 ID 61", second)
                languages = (datafiles / "locale" / "languages").read_text(encoding="utf-8")
                self.assertEqual(1, languages.count(MANAGED_BEGIN))
                self.assertEqual(1, languages.count(MANAGED_END))
                self.assertTrue(
                    (datafiles / "locale" / LANGUAGE_CODE / "LC_MESSAGES" / "blender.mo").is_file()
                )
                uninstall_pack(root / "Blender.app", False, reset_language=False)
                languages = (datafiles / "locale" / "languages").read_text(encoding="utf-8")
                self.assertNotIn(LANGUAGE_CODE, languages)
                self.assertIn("Occupied:test", languages)
                self.assertFalse((datafiles / "locale" / LANGUAGE_CODE).exists())

    def test_install_rejects_unmanaged_same_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            datafiles, packs = self.prepare(root)
            languages = datafiles / "locale" / "languages"
            languages.write_text(languages.read_text() + f"62:Custom:{LANGUAGE_CODE}:100%\n")
            layout = (root / "blender", datafiles, "5.1.2")
            with mock.patch("scripts.bilingual.blender_layout", return_value=layout):
                with self.assertRaises(BilingualError):
                    install_pack(root / "Blender.app", None, False, packs, activate=False)

    def test_language_activation_uses_blender_and_saves_preferences(self) -> None:
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("scripts.bilingual.subprocess.run", return_value=completed) as run:
            set_blender_language(Path("/Applications/Blender.app/Contents/MacOS/Blender"), LANGUAGE_CODE)
        command = run.call_args.args[0]
        self.assertIn("--background", command)
        expression = command[-1]
        self.assertIn(f"language={LANGUAGE_CODE!r}", expression)
        self.assertIn("save_userpref", expression)


if __name__ == "__main__":
    unittest.main()
