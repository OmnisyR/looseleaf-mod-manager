from __future__ import annotations

import runpy
import sys
from pathlib import Path

from modmanager import FileMapping, ManagerError, ModManagerCore

__all__ = ["ModManagerCore", "ManagerError", "FileMapping", "main"]

PYTHON_HELPER_ARG = "--looseleaf-run-python"


def run_python_script(argv: list[str]) -> int:
    if not argv:
        print(f"{PYTHON_HELPER_ARG} requires a script path", file=sys.stderr)
        return 2
    script = Path(argv[0]).resolve()
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    try:
        sys.argv = [str(script), *argv[1:]]
        sys.path.insert(0, str(script.parent))
        runpy.run_path(str(script), run_name="__main__")
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
