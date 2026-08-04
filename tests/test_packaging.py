from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_desktop_apps_do_not_request_installation_directory_privileges(self) -> None:
        build_script = (ROOT / "packaging" / "build_app.py").read_text(encoding="utf-8")
        self.assertNotIn("--uac-admin", build_script)
        self.assertNotIn("NSAppBundlesUsageDescription", build_script)
        self.assertNotIn("codesign", build_script)


if __name__ == "__main__":
    unittest.main()
