# Looseleaf Mod Manager

[English README](README.md)

Looseleaf Mod Manager 是一个本地 GUI MOD 管理器，面向使用新版 `asset/...` 松散文件结构和 `table_*` 语言表的 PC Falcom 游戏。它最初为 `Trails in the Sky 1st Chapter / Sora no Kiseki the 1st` 制作，但核心文件管理流程也适用于采用相同结构的其他游戏。

## 功能

- 支持拖拽导入 MOD 压缩包、文件夹和单文件。
- 支持递归解压嵌套压缩包。
- 自动归类没有目录结构的文件：
  - `.mdl` -> `asset/common/model`
  - `.mi` -> `asset/common/model_info`
  - `.dds` -> `asset/dx11/image`
- 支持本地拖拽或 URL 缓存绑定预览图，支持动态 WebP/GIF。
- 支持启用/停用 MOD、拖拽调整加载顺序、检测冲突文件。
- 支持根据识别到的角色服装/模型 ID 筛选 MOD。
- 应用前自动备份被覆盖的原始游戏文件，并可还原由管理器写入的改动。
- 支持将 `t_costume.tbl`、`t_dlc.tbl`、`t_item.tbl`、`t_shop.tbl` 合并到当前游戏运行语言对应的表中。
- 检测缺失的 `xinput1_4.dll`，并可从 [Hinkiii/sora1looseload](https://github.com/Hinkiii/sora1looseload) 最新 Release 下载。
- 首次启动时根据操作系统语言选择界面语言：简体中文/繁体中文系统默认中文，其它系统默认英文。
- 选择游戏目录时会尽量从检测到的 Steam 游戏库开始，方便快速定位安装目录。

## 安装与启动

需要 Python 3.10 或更新版本。

1. 将本项目放在独立目录中，例如游戏目录下的 `__manager`。
2. 双击 `run.bat`。
3. 首次启动会创建 `.venv`，安装 `requirements.txt`，然后启动 GUI。
4. 选择游戏根目录，也就是包含游戏 `.exe` 的安装目录。

也可以手动运行：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe mod_manager.py
```

## 构建 Windows EXE

运行：

```bat
build_exe.bat
```

生成文件位于：

```text
dist\Looseleaf Mod Manager.exe
```

这个 EXE 不会内置已导入的 MOD、备份、游戏文件、7-Zip、KuroTools 或 `xinput1_4.dll`。运行数据和自动下载工具会在 EXE 同目录的 `manager_data` 下创建。

## 基础流程

1. 在右上角添加或切换当前游戏。
2. 将 MOD 压缩包或文件夹拖进左侧 MOD 列表。
3. 选中 MOD 后，可以在右侧绑定预览图。
4. 如果出现冲突，调整加载顺序。列表从上到下应用，靠下的 MOD 会覆盖靠上的同目标文件。
5. 点击 `应用到游戏`。
6. 需要撤回时点击 `还原游戏文件`。

## 工具自动下载

管理器不会把第三方工具提交到仓库。运行时会按需下载并缓存到 `manager_data/tools`：

- 7-Zip：用于 `.rar`、`.7z`、`.tar.zst` 等格式。优先解析 7-Zip 官方下载页，失败时使用 `ip7z/7zip` GitHub Release 作为回退。
- KuroTools：用于解析和重新打包 `.tbl`。需要表合并时会自动下载 `nnguyen259/KuroTools` 仓库源码。
- sora1looseload `xinput1_4.dll`：当当前游戏目录缺少 `xinput1_4.dll` 时，界面会显示下载按钮，默认下载 `Hinkiii/sora1looseload` 最新 Release 的 `xinput1_4.dll`。

这些下载内容都属于运行时缓存，不应提交到 GitHub。

## 数据目录

`manager_data` 保存所有本地状态：

- `config.json`: 语言、窗口布局、已注册游戏。
- `games/<game_id>/mods`: 已导入 MOD 的规范化副本和原始来源备份。
- `games/<game_id>/backups`: 首次覆盖游戏文件前保存的原始文件。
- `games/<game_id>/table_cache`: 原始 `.tbl` 缓存，用于还原和重新合并。
- `tools`: 自动下载的 7-Zip、KuroTools 等工具缓存。

如果要完全重置，建议先在 GUI 中点击 `还原游戏文件`，再关闭程序并删除 `manager_data`。

## 测试

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
python -m compileall -q modmanager tests
```

## 发布注意事项

- 不要提交 `.venv`、`manager_data`、`__pycache__`、已导入的 MOD、备份文件、生成的 EXE 或自动下载的工具。
- 打包好的 EXE 可以单独上传到 GitHub Releases。
- 第三方工具会在运行时下载，发布说明中应列出对应上游项目。
- 本仓库不包含游戏资源或第三方二进制文件。

## 许可证

本项目使用 MIT License。详见 [LICENSE](LICENSE)。
