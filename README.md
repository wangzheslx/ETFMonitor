# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## 项目概述

ETF Monitor 是一款 Windows 桌面悬浮窗应用，用于实时监控多只 ETF 股票价格。采用 PyQt6 构建，支持半透明无边框悬浮窗、系统托盘驻留、自定义数据源和刷新频率。

## 常用命令

```powershell
# 安装依赖
pip install PyQt6 requests

# 运行应用（源码模式）
python main.py

# 安装 PyInstaller 打包工具
pip install pyinstaller

# 使用 spec 文件打包为单个 exe（必须用 python -m 方式调用）
python -m PyInstaller --clean --noconfirm ETFMonitor.spec

# 或使用构建脚本（自动检测 .venv 虚拟环境）
build.bat

# 验证语法（不运行）
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('Syntax OK')"
```

## 项目文件结构

```
ETFMonitor/
├── main.py              # 主程序（全部业务逻辑，约 1550+ 行）
├── ETFMonitor.spec      # PyInstaller 打包配置
├── build.bat            # Windows 一键打包脚本（纯 ASCII，自动检测 .venv）
── build_mac.sh         # macOS 打包脚本（需在本机 macOS 运行）
├── ETFMonitor_mac.spec  # macOS 打包配置
├── version_info.txt     # exe 文件属性详细信息（版本、描述、版权等）
├── etf_icon.ico         # 自定义 ETF 主题图标（6 尺寸：16/32/48/64/128/256）
├── etf_config.json      # 用户配置文件（自动生成）
├── etf_list_cache.json  # ETF 全市场列表缓存
├── requirements.txt     # Python 依赖（PyQt6、requests、pyinstaller）
├── .venv/               # 虚拟环境（PyCharm 创建）
├── dist/                # 打包产物（ETFMonitor.exe）
└── build/               # 打包中间文件
```

## 架构概览

整个应用是单文件架构（`main.py`），按功能模块从上到下组织：

### 模块层次

```
main.py
├── 配置管理 (load_config / save_config / DEFAULT_CONFIG)
│   └── 配置文件: etf_config.json（自动创建在 exe/脚本所在目录）
├── 数据获取层
│   ├── ETFPriceFetcher (QObject) - 新浪/腾讯 API 解析，在子线程运行
│   │   └── _resolve_code() - 统一解析 SH/SZ 前缀，支持自动识别交易所
│   └── FetchThread (QThread) - 封装 fetcher 的线程执行
├── 图标生成
│   ├── create_tray_icon_pixmap() - 托盘图标，有数据时显示首只 ETF 涨跌幅
│   └── _draw_default_icon() - 默认灰色 "E" 图标
├── UI 对话框
│   ├── ETFDialog - 添加 ETF（代码输入 + 交易所下拉选择 SH/SZ/自动）
│   ├── ArrowedSpinBox (QSpinBox) - 自绘箭头避免 Windows 主题兼容问题
│   └── SettingsDialog - 设置面板（ETF 列表、数据源、刷新频率、外观、行为、开机自启）
├── 悬浮窗
│   └── ETFOverlayWidget (QWidget) - 主悬浮窗，无边框置顶，支持拖动和鼠标穿透
│       ├── data_updated 信号 → 通知托盘更新 tooltip 和图标
│       ├── _do_fetch() → 线程安全的数据获取，旧线程停止后才创建新线程
│       └── _rebuild_price_rows() → 动态重建价格行，安全清理旧控件
├── 托盘系统
│   ├── TrayTooltip (QWidget) - 自定义 tooltip 窗口，固定宽度 240px 防止换行
│   │   └── 用 QTimer 轮询 QCursor.pos() 检测悬停（PyQt6 无 hovered 信号）
│   └── TrayApp (QApplication) - 托盘管理，右键菜单，hover 检测，退出逻辑
│       └── setWindowIcon() - 加载 etf_icon.ico 作为应用图标
└── main() 入口
```

### 数据流

```
用户添加 ETF 代码 → etf_config.json 保存
  → QTimer 每 N 秒触发 _do_fetch()
    → FetchThread 在新线程调用 ETFPriceFetcher.fetch()
      → HTTP 请求新浪/腾讯接口
      → 解析返回数据，emit data_ready(dict)
    → _on_data_ready() 更新 price_widgets 的 QLabel
    → _update_display() 设置涨跌颜色
    → emit data_updated 信号
  → TrayApp._on_data_updated()
    → 更新托盘图标（首只 ETF 涨跌幅）
    → 更新 TrayTooltip 数据
```

### 关键设计决策

1. **线程安全**：`_do_fetch()` 在创建新线程前会 stop → quit → wait(2000) → terminate 旧线程，并 disconnect 旧信号连接，防止信号跨线程访问已删除的 widget 导致崩溃。

2. **配置持久化**：所有修改（添加/删除 ETF、设置变更、窗口拖动）都立即调用 `save_config()`。`_get_app_dir()` 用 `sys.frozen` 判断 PyInstaller 打包环境，exe 时用 `sys.executable` 目录，源码时用 `__file__` 目录。

3. **代码解析**：`_resolve_code()` 统一处理 `510050`（纯数字）、`SH510050`（带前缀）、`SZ159915` 三种格式。新浪/腾讯接口均使用此方法。

4. **托盘右键菜单**：放弃 `QSystemTrayIcon.setContextMenu()`（Windows 部分版本不可靠），改为在 `_on_tray_activated(Context)` 中手动创建 QMenu 并用 `menu.exec(QCursor.pos())` 弹出。

5. **悬浮窗不显示在任务栏**：使用 `Qt.WindowType.Tool` 标志，窗口不会出现在 Windows 任务栏。

6. **ArrowedSpinBox**：由于 CSS 箭头在某些 Windows 主题/PyQt6 版本中不渲染，改为 `setButtonSymbols(NoButtons)` + `paintEvent` 手动绘制实心三角形，`mousePressEvent` 处理点击区域。

### 配置结构 (etf_config.json)

```json
{
  "etf_codes": ["510050", "510300", "159915"],
  "data_source": "sina",
  "refresh_interval": 5,
  "position": {"x": null, "y": null},
  "locked": false,
  "opacity": 0.75,
  "font_size": 12,
  "up_color": "#FF4444",
  "down_color": "#00CC00",
  "text_color": "#E0E0E0",
  "bg_color": "#1A1A1A"
}
```

## 打包配置

### 打包文件清单

| 文件 | 用途 |
|------|------|
| `ETFMonitor.spec` | PyInstaller 打包配置（Windows） |
| `ETFMonitor_mac.spec` | PyInstaller 打包配置（macOS） |
| `build.bat` | Windows 一键打包脚本（纯 ASCII，自动检测 .venv） |
| `build_mac.sh` | macOS 一键打包脚本 |
| `version_info.txt` | exe 文件属性信息（版本、描述、版权等） |
| `etf_icon.ico` | 自定义 ETF 主题图标（6 尺寸） |

### 打包注意事项

- **构建脚本**：`build.bat` 自动检测 `.venv` 虚拟环境，优先使用 `.venv\Scripts\python.exe`；未找到时回退系统 Python。脚本全部使用 ASCII 字符，避免 cmd.exe 编码问题。
- **必须使用 `python -m PyInstaller` 调用**，直接调用 `pyinstaller` 命令可能因 PATH 问题找不到。
- **打包前确保所有依赖已安装**：`pip install PyQt6 requests`，否则打包后的 exe 运行时会报 `ModuleNotFoundError`。
- **虚拟环境隔离**：PyCharm 创建的 `.venv` 中的依赖与系统 Python 隔离，打包时必须使用 `.venv` 中的 Python 解释器。
- `ETFMonitor.spec` 自动收集 PyQt6 的 `platforms` 和 `styles` 插件目录到打包数据中。
- 排除 `tkinter`、`numpy`、`pandas`、`matplotlib`、`PIL`、`PyQt5` 等无用库减小体积。
- 输出 `dist/ETFMonitor.exe`，`console=False` 不显示命令行窗口。
- 图标嵌入：`icon='etf_icon.ico'` 将自定义图标嵌入 exe。
- 版本信息：`version='version_info.txt'` 将文件属性信息（文件说明、版本、版权等）嵌入 exe。
- 图标文件同时作为数据文件打包（`datas`），运行时 `TrayApp` 通过 `APP_DIR` 加载。

### 版本信息字段 (version_info.txt)

| 字段 | 值 |
|------|-----|
| CompanyName | ETFMonitor |
| FileDescription | ETF Monitor - ETF股票实时监控悬浮窗 |
| FileVersion | 1.0.0.0 |
| InternalName | ETFMonitor |
| LegalCopyright | Copyright (C) 2026 |
| OriginalFilename | ETFMonitor.exe |
| ProductName | ETF Monitor |
| ProductVersion | 1.0.0.0 |

## 已知坑

- `main.py` 有**重复的 `_on_error` 方法**（~1145 与 ~1151 行），后者覆盖前者；编辑前确认所在位置。
- `etf_config.json` 中 `auto_hide`、`edge_margin` 不在 `DEFAULT_CONFIG`，应用不读取但加载/保存时会被保留，勿误以为功能已实现。
- 打包时 `.spec` 已排除 tkinter/numpy/pandas 等；`dist/` 与 `build/` 为打包产物，别当作源码。
- macOS `.app` 内 `Contents/MacOS/` 通常只读，打包后配置无法持久化到该目录（`_get_app_dir()` 限制），改动配置路径时注意。
- Windows 图标缓存可能导致 exe 图标不更新，需运行 `ie4uinit.exe -show` 或重启资源管理器清除缓存。
- `build.bat` 必须全部使用 ASCII 字符，中文会导致 cmd.exe 编码解析错误（GBK vs UTF-8）。
