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
- 可选的进阶 `.mi` 对比视图，可与官方 model info 文件比较；可用时会从 `asset_common_model_info.pac` 缓存官方文件。
- 应用时只在游戏目录写入 loose MOD 文件；不会修改 pac 中的官方游戏资源。可一键清理上次由管理器应用的 loose 文件。
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

这个 EXE 不会内置已导入的 MOD、游戏文件、7-Zip、KuroTools 或 `xinput1_4.dll`。运行数据和自动下载工具会在 EXE 同目录的 `manager_data` 下创建。

## 基础流程

1. 在右上角添加或切换当前游戏。
2. 将 MOD 压缩包或文件夹拖进左侧 MOD 列表。
3. 选中 MOD 后，可以在右侧绑定预览图。
4. 如果出现冲突，调整加载顺序。列表从上到下应用，靠下的 MOD 会覆盖靠上的同目标文件。
5. 点击 `应用到游戏`。
6. 需要撤回时点击 `清理已应用文件`，删除管理器上次写入的 loose 文件。

## MI Studio（集成的 model info 预览 / 调整工具）

MI Studio 已集成到 Mod 管理器中，用于预览和批量调整所有 model info（`.mi`）文件。点击管理器顶部的“进入 MI Studio >”会关闭管理器窗口并打开 MI Studio；点击 MI Studio 顶部的“< 返回 Mod 管理器”会切回管理器：

- 枚举全部三类 `.mi`：官方 `asset_common_model_info.pac` 中的原版文件、MOD 覆盖的文件、以及 MOD 自己注册的新模型文件，并按角色/服装名标注与筛选。
- 以中文可视化树形展示 `.mi` 结构（动态骨骼、碰撞体、IK、挂点等，默认折叠），字段带含义说明；“基准值”列始终显示官方 pac 解包值并高亮差异，“参考值”列可任选提供该文件的 MOD 作为对照；编辑起点则是当前生效的文件（MOD 优先）。
- 数值可用滑块或直接输入修改；左右对称的条目（Left/Right）默认联动修改，也可关闭联动单独设置。常改的字段可“★ 收藏”，收藏项在所有 mi 文件的结构树顶部置顶显示、可直接修改。
- 支持把文件加入自定义分组，修改可作用于单个文件、多选文件或整个组；也可以从任意其他 `.mi`（含外部文件）整段导入动态骨骼等段落。
- 所有修改统一写入一个共享 MOD「MI Studio 参数调整」（`mi-studio-tweaks`），该 MOD 固定保持在加载顺序最底部，覆盖其它 MOD；点击“应用到游戏”即可按管理器逻辑生效。

启动管理器：

```bat
.venv\Scripts\python.exe mod_manager.py
```

`mi_studio.py` / `run_mi_studio.bat` 仍可用于直接以 MI Studio 作为初始界面启动同一个集成程序。

注意：请先在管理器中添加并选择游戏。

## 工具自动下载

管理器不会把第三方工具提交到仓库。运行时会按需下载并缓存到 `manager_data/tools`：

- 7-Zip：用于 `.rar`、`.7z`、`.tar.zst` 等格式。优先解析 7-Zip 官方下载页，失败时使用 `ip7z/7zip` GitHub Release 作为回退。
- KuroTools：用于解析和重新打包 `.tbl`。需要表合并时会自动下载 `nnguyen259/KuroTools` 仓库源码。
- sora1looseload `xinput1_4.dll`：当当前游戏目录缺少 `xinput1_4.dll` 时，界面会显示下载按钮，默认下载 `Hinkiii/sora1looseload` 最新 Release 的 `xinput1_4.dll`。

这些下载内容都属于运行时缓存，不应提交到 GitHub。

## 数据目录

`manager_data` 保存所有本地状态：

- `config.json`: 语言、窗口布局、已注册游戏。
- `games/<game_id>/mods`: 已导入 MOD 的规范化副本和原始来源副本。
- `games/<game_id>/model_info_cache`: 进阶 `.mi` 对比视图使用的原始模型信息缓存。
- `games/<game_id>/table_cache`: 官方 `.tbl` 缓存，用于表合并。
- `tools`: 自动下载的 7-Zip、KuroTools 等工具缓存。

如果要完全重置，建议先在 GUI 中点击 `清理已应用文件`，再关闭程序并删除 `manager_data`。

## 测试

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
python -m compileall -q modmanager mistudio tests
```

## 发布注意事项

- 不要提交 `.venv`、`manager_data`、`__pycache__`、已导入的 MOD、生成的 EXE 或自动下载的工具。
- 打包好的 EXE 可以单独上传到 GitHub Releases。
- 第三方工具会在运行时下载，发布说明中应列出对应上游项目。
- 本仓库不包含游戏资源或第三方二进制文件。

## 许可证

本项目使用 MIT License。详见 [LICENSE](LICENSE)。
