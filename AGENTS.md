# AGENTS.md

## 项目概况
单文件 PyQt6 桌面应用（`main.py`，~1550 行），Windows 悬浮窗实时监控 ETF 行情，系统托盘常驻。无测试框架、无 lint/typecheck 配置、无 CI、非 git 仓库。依赖：`requirements.txt`（PyQt6、requests、pyinstaller）。

## 常用命令
- 运行（源码模式）：`python main.py`（本机开发 venv 在 `.venv`）
- 验证改动（无测试/typecheck，仅此语法校验 + 手动运行）：
  `python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('Syntax OK')"`
- Windows 打包：`build.bat` 或 `pyinstaller --clean --noconfirm ETFMonitor.spec` → `dist/ETFMonitor.exe`
- macOS 打包：`./build_mac.sh`（**必须在本机 macOS 运行**，PyInstaller 不支持交叉编译）→ `dist/ETFMonitor.app`

## 架构要点
- 全部代码在 `main.py`，按模块自上而下：配置管理 → 数据获取（ETFPriceFetcher / FetchThread）→ 托盘图标 → 对话框（ETFDialog / SettingsDialog）→ ETFOverlayWidget 悬浮窗 → TrayTooltip → TrayApp → main() 入口。
- **线程安全模式**：`_do_fetch()` 创建新线程前会 stop → quit → wait(2000) → terminate 旧线程并 disconnect 信号，防止跨线程访问已删除 widget。改动数据获取逻辑时保持此模式。
- 涨跌配色遵循 A 股约定：红涨绿跌（config `up_color` / `down_color`），勿改成西方绿涨红跌。
- `_resolve_code()` 统一处理纯数字 / SH / SZ 前缀（5/6/9 开头→上海）。新增数据源应复用该方法，新浪返回 GBK 编码且需 Referer 头；腾讯字段以 `~` 分隔（3=现价、4=昨收、32=涨跌幅）。
- 配置任何修改（增删 ETF、设置、拖动窗口）都立即 `save_config()`；`_get_app_dir()` 用 `sys.frozen` 区分打包/源码目录。
- 托盘 tooltip 用 QTimer 轮询 `QCursor.pos()` 模拟悬停（PyQt6 无 hovered 信号）；右键菜单手动 `QMenu.exec()`，不用 `setContextMenu()`（Windows 部分版本不可靠）。
- 代码注释与 UI 文案均为中文。

## 已知坑
- `main.py` 有**重复的 `_on_error` 方法**（~1145 与 ~1151 行），后者覆盖前者；编辑前确认所在位置。
- `etf_config.json` 中 `auto_hide`、`edge_margin` 不在 `DEFAULT_CONFIG`，应用不读取但加载/保存时会被保留，勿误以为功能已实现。
- 打包时 `.spec` 已排除 tkinter/numpy/pandas 等；`dist/` 与 `build/` 为打包产物，别当作源码。
- macOS `.app` 内 `Contents/MacOS/` 通常只读，打包后配置无法持久化到该目录（`_get_app_dir()` 限制），改动配置路径时注意。

## 参考
`CODEBUDDY.md` 含更详细的模块层次、数据流与关键设计决策，改动涉及对应模块时查阅。
