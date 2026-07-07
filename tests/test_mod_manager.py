from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from mod_manager import run_python_script


class PythonHelperTests(unittest.TestCase):
    def test_missing_helper_script_returns_error_code(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = run_python_script(["missing-helper-script.py"])

        self.assertEqual(code, 2)
        self.assertIn("script not found", stderr.getvalue())

    def test_helper_script_exception_returns_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            script = Path(raw_temp) / "boom.py"
            script.write_text("raise RuntimeError('boom')\n", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = run_python_script([str(script)])

        self.assertEqual(code, 1)
        self.assertIn("RuntimeError: boom", stderr.getvalue())

    def test_helper_script_system_exit_returns_requested_code(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            script = Path(raw_temp) / "exit.py"
            script.write_text("raise SystemExit(7)\n", encoding="utf-8")

            code = run_python_script([str(script)])

        self.assertEqual(code, 7)


if __name__ == "__main__":
    unittest.main()
