from __future__ import annotations

import runpy
import sys
import traceback
from pathlib import Path

from modmanager import FileMapping, ManagerError, ModManagerCore

__all__ = ["ModManagerCore", "ManagerError", "FileMapping", "main"]

PYTHON_HELPER_ARG = "--looseleaf-run-python"


def run_python_script(argv: list[str]) -> int:
    if not argv:
        print(f"{PYTHON_HELPER_ARG} requires a script path", file=sys.stderr)
        return 2
    script = Path(argv[0]).resolve()
    if not script.is_file():
        print(f"{PYTHON_HELPER_ARG} script not found: {script}", file=sys.stderr)
        return 2
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    try:
        sys.argv = [str(script), *argv[1:]]
        sys.path.insert(0, str(script.parent))
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as exc:
            if exc.code is None:
                return 0
            if isinstance(exc.code, int):
                return exc.code
            print(exc.code, file=sys.stderr)
            return 1
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 1
    finally:
        sys.argv = old_argv
        sys.path[:] = old_path
    return 0


def main() -> int:
    from modmanager.ui.app import main as _main

    return _main()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == PYTHON_HELPER_ARG:
        raise SystemExit(run_python_script(sys.argv[2:]))
    raise SystemExit(main())
