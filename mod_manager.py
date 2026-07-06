from __future__ import annotations

from modmanager import FileMapping, ManagerError, ModManagerCore

__all__ = ["ModManagerCore", "ManagerError", "FileMapping", "main"]


def main() -> int:
    from modmanager.ui.app import main as _main

    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
