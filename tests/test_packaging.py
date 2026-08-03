from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_macos_bundle_declares_app_management_usage(self) -> None:
        build_script = (ROOT / "packaging" / "build_app.py").read_text(encoding="utf-8")
        self.assertIn('"NSAppBundlesUsageDescription"', build_script)
        self.assertIn('codesign', build_script)


if __name__ == "__main__":
    unittest.main()
