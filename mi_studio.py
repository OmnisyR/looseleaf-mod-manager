"""MI Studio — standalone model info (.mi) previewer / editor.

Runs independently of the mod manager UI but shares its data (manager_data)
and source code. Edits are collected into a single mod pinned to the bottom
of the load order.
"""
from __future__ import annotations

import sys


def main() -> int:
    from mistudio.app import main as _main

    return _main()


if __name__ == "__main__":
    sys.exit(main())
