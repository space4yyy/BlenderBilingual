from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_desktop_build_runs_for_main_branch_pushes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "build-gui.yml").read_text(
            encoding="utf-8"
        )
        push_section = workflow.split("  push:\n", 1)[1].split("\njobs:\n", 1)[0]
        self.assertIn("    branches:\n      - main\n", push_section)

    def test_python_cache_uses_build_requirements(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "build-gui.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("          cache-dependency-path: requirements-build.txt\n", workflow)


if __name__ == "__main__":
    unittest.main()
