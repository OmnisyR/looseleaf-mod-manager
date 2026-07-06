# Looseleaf Mod Manager

[Simplified Chinese README](README_sc.md)

Looseleaf Mod Manager is a local GUI MOD manager for PC Falcom games that use the newer `asset/...` loose-file layout and `table_*` language tables. It was built for `Trails in the Sky 1st Chapter / Sora no Kiseki the 1st`, but the core file management flow also works for other games with the same structure.

## Features

- Drag-and-drop import for MOD archives, folders, and loose files.
- Recursive extraction for nested archives.
- Automatic target mapping for loose files:
  - `.mdl` -> `asset/common/model`
  - `.mi` -> `asset/common/model_info`
  - `.dds` -> `asset/dx11/image`
- Preview image binding by local drag-and-drop or URL cache, including animated WebP/GIF.
- Enable/disable MODs, drag to edit load order, and detect file conflicts.
- Character filtering based on detected costume/model character IDs.
- Back up original game files before overwriting them, then restore managed changes later.
- Merge `t_costume.tbl`, `t_dlc.tbl`, `t_item.tbl`, and `t_shop.tbl` into the currently active game language.
- Detect missing `xinput1_4.dll` and download it from the latest [Hinkiii/sora1looseload](https://github.com/Hinkiii/sora1looseload) Release.
- First-run language defaults to Chinese for Simplified/Traditional Chinese operating systems, otherwise English.
- Game folder picker starts from the detected Steam library when possible.

## Install And Run

Python 3.10 or newer is required.

1. Put this project in a standalone folder, for example `__manager` under the game folder.
2. Double-click `run.bat`.
3. On first launch, the script creates `.venv`, installs `requirements.txt`, and starts the GUI.
4. Select the game root folder, meaning the install directory that contains the game `.exe`.

Manual startup:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe mod_manager.py
```

## Build A Windows EXE

Run:

```bat
build_exe.bat
```

The executable is written to:

```text
dist\Looseleaf Mod Manager.exe
```

The EXE does not bundle imported MODs, backups, game files, 7-Zip, KuroTools, or `xinput1_4.dll`. Runtime data and downloaded tools are created next to the EXE under `manager_data`.

## Basic Workflow

1. Add or switch the active game from the top-right toolbar.
2. Drop a MOD archive or folder onto the MOD list.
3. Select the MOD and optionally bind a preview image on the right.
4. If conflicts are reported, adjust load order. MODs are applied top-to-bottom; lower MODs overwrite earlier targets.
5. Click `Apply`.
6. Click `Restore Game` to undo files managed by this app.

## Automatic Tool Downloads

Third-party tools are not committed to the repository. They are downloaded on demand and cached under `manager_data/tools`:

- 7-Zip: used for `.rar`, `.7z`, `.tar.zst`, and similar formats. The manager tries the official 7-Zip download page first and falls back to the `ip7z/7zip` GitHub Release URLs.
- KuroTools: used to parse and repack `.tbl` files. It is downloaded from `nnguyen259/KuroTools` when table merging is needed.
- sora1looseload `xinput1_4.dll`: if the active game folder is missing `xinput1_4.dll`, the GUI shows a download button. The default source is the latest `Hinkiii/sora1looseload` GitHub Release asset.

All downloaded tools are runtime cache and should not be committed.

## Data Directory

`manager_data` stores local state:

- `config.json`: language, window layout, and registered games.
- `games/<game_id>/mods`: normalized imported MODs and raw-source copies.
- `games/<game_id>/backups`: original game files saved before first overwrite.
- `games/<game_id>/table_cache`: original `.tbl` cache for restore and repeated merges.
- `tools`: downloaded 7-Zip, KuroTools, and other runtime tools.

To fully reset the manager, restore game files from the GUI first, close the app, then delete `manager_data`.

## Tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
python -m compileall -q modmanager tests
```

## Publishing Notes

- Do not commit `.venv`, `manager_data`, `__pycache__`, imported MODs, backups, generated EXE files, or downloaded tools.
- Packaged EXE builds can be uploaded to GitHub Releases separately.
- Third-party tools are downloaded at runtime; list their upstream projects in release notes.
- This repository does not include game assets or third-party binaries.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
