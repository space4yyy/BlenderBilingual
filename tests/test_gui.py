from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from blender_bilingual_gui import inject
from scripts.bilingual import MOCatalog, MOEntry, ORDER_EN_ZH


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
                mock.patch("blender_bilingual_gui.install_pack", side_effect=inspect_install),
            ):
                self.assertEqual("ok", inject(root, ORDER_EN_ZH))


if __name__ == "__main__":
    unittest.main()
