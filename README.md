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
- Optional advanced `.mi` comparison against official model info files, with official files cached from `asset_common_model_info.pac` when available.
- Apply writes loose MOD files into the game folder only; it does not modify official resources inside pac archives. The manager can clean the loose files from the last apply.
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

The EXE does not bundle imported MODs, game files, 7-Zip, KuroTools, or `xinput1_4.dll`. Runtime data and downloaded tools are created next to the EXE under `manager_data`.

## Basic Workflow

1. Add or switch the active game from the top-right toolbar.
2. Drop a MOD archive or folder onto the MOD list.
3. Select the MOD and optionally bind a preview image on the right.
4. If conflicts are reported, adjust load order. MODs are applied top-to-bottom; lower MODs overwrite earlier targets.
5. Click `Apply`.
6. Click `Clean Applied Files` to remove loose files written by the last apply.

## MI Studio (integrated model info previewer / editor)

MI Studio is integrated into the Mod Manager. It previews and batch edits every
model info (`.mi`) file. Click `MI Studio >` in the manager toolbar to close the
manager window and open MI Studio; click `< Mod Manager` in MI Studio to switch
back:

- Enumerates all three `.mi` origins: official files inside
  `asset_common_model_info.pac`, MOD overrides, and MOD-registered new models,
  labelled and filterable by character/costume name.
- Visualizes the `.mi` structure (dynamic bones, colliders, IK, locators, ...)
  as a readable tree (collapsed by default) with field explanations. The
  基准值 (baseline) column always shows the official pac values with diff
  highlighting, and an optional 参考值 (reference) column can show any mod
  that provides the file; editing itself starts from the effective file
  (mods win over pac).
- Values are edited via sliders or direct input; left/right symmetric entries
  are linked by default and can be unlinked for individual tweaks. Frequently
  used fields can be starred — favorites are pinned at the top of the tree
  for every mi file and remain editable there.
- Files can be organized into custom groups; an edit can target a single file,
  the multi-selection, or a whole group. Whole sections (e.g. DynamicBone) can
  also be imported from any other `.mi`, including external files.
- All edits are stored in a single shared MOD (`mi-studio-tweaks`, "MI Studio
  参数调整") pinned to the bottom of the load order so it wins every conflict.
  Click "应用到游戏" (Apply) to deploy through the manager's own apply logic.

Run the manager with:

```bat
.venv\Scripts\python.exe mod_manager.py
```

`mi_studio.py` / `run_mi_studio.bat` can still start the same integrated program
with MI Studio as the first screen. Add and select the game in the manager first.

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
- `games/<game_id>/model_info_cache`: original `.mi` files cached for the optional advanced comparison view.
- `games/<game_id>/table_cache`: official `.tbl` cache used for table merging.
- `tools`: downloaded 7-Zip, KuroTools, and other runtime tools.

To fully reset the manager, click `Clean Applied Files` in the GUI first, close the app, then delete `manager_data`.

## Tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
python -m compileall -q modmanager mistudio tests
```

## Publishing Notes

- Do not commit `.venv`, `manager_data`, `__pycache__`, imported MODs, generated EXE files, or downloaded tools.
- Packaged EXE builds can be uploaded to GitHub Releases separately.
- Third-party tools are downloaded at runtime; list their upstream projects in release notes.
- This repository does not include game assets or third-party binaries.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
