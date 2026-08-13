# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 - ETF Monitor 打包配置
将程序打包为单个 exe，包含所有依赖和资源
"""

import sys
import os
from pathlib import Path

# 项目目录
PROJECT_DIR = Path(SPECPATH)  # SPECPATH 是 spec 文件所在目录

# 收集 PyQt6 的隐藏导入
hidden_imports = [
    # PyQt6 核心模块
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    # PyQt6 平台插件
    'PyQt6.QtCore.Qt',
    # requests 相关
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    # JSON
    'json',
]

# 收集 PyQt6 二进制依赖
binaries = []
datas = []

# 自动查找 PyQt6 的 Qt 平台插件目录
try:
    import PyQt6
    qt_plugin_path = os.path.join(os.path.dirname(PyQt6.__file__), 'Qt6', 'plugins')
    if os.path.exists(qt_plugin_path):
        # 添加 platforms 插件（qwindows.dll 等）
        platforms_path = os.path.join(qt_plugin_path, 'platforms')
        if os.path.exists(platforms_path):
            for f in os.listdir(platforms_path):
                datas.append((os.path.join(platforms_path, f), 'PyQt6/Qt6/plugins/platforms'))

        # 添加 styles 插件
        styles_path = os.path.join(qt_plugin_path, 'styles')
        if os.path.exists(styles_path):
            for f in os.listdir(styles_path):
                datas.append((os.path.join(styles_path, f), 'PyQt6/Qt6/plugins/styles'))
except Exception:
    pass

# 添加自定义图标文件
icon_src = os.path.join(str(PROJECT_DIR), 'etf_icon.ico')
if os.path.exists(icon_src):
    datas.append((icon_src, '.'))

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 标准库不需要的
        'tkinter',
        'unittest',
        'test',
        'pydoc_data',
        'distutils',
        'setuptools',
        'pkg_resources',
        # 数据科学(不需要)
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'scipy',
        # 旧版 Qt
        'PyQt5',
        'PySide2',
        'PySide6',
        # PyQt6 未使用的大模块(排除可显著减小体积)
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineQuick',
        'PyQt6.QtWebChannel',
        'PyQt6.QtWebSockets',
        'PyQt6.Qt3DCore',
        'PyQt6.Qt3DRender',
        'PyQt6.Qt3DAnimation',
        'PyQt6.Qt3DExtras',
        'PyQt6.Qt3DInput',
        'PyQt6.Qt3DLogic',
        'PyQt6.QtCharts',
        'PyQt6.QtDataVisualization',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtQuick3D',
        'PyQt6.QtQuickWidgets',
        'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets',
        'PyQt6.QtPositioning',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtSql',
        'PyQt6.QtTest',
        'PyQt6.QtBluetooth',
        'PyQt6.QtNfc',
        'PyQt6.QtRemoteObjects',
        'PyQt6.QtOpenGL',
        'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtSvg',
        'PyQt6.QtSvgWidgets',
        'PyQt6.QtNetwork',
        'PyQt6.QtPrintSupport',
        'PyQt6.QtDesigner',
        'PyQt6.QtHelp',
        'PyQt6.QtUiTools',
        'PyQt6.QtXml',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 过滤掉未使用模块对应的 Qt6 DLL,进一步减小体积
_qt6_exclude_prefixes = (
    'Qt6WebEngine', 'Qt6WebChannel', 'Qt6WebSockets',
    'Qt63D', 'Qt6Charts', 'Qt6DataVisualization',
    'Qt6Multimedia', 'Qt6Qml', 'Qt6Quick', 'Qt6Pdf',
    'Qt6Sensors', 'Qt6SerialPort', 'Qt6Sql', 'Qt6Test',
    'Qt6Bluetooth', 'Qt6Nfc', 'Qt6RemoteObjects',
    'Qt6PrintSupport', 'Qt6OpenGL', 'Qt6Svg',
    'Qt6Designer', 'Qt6Help', 'Qt6UiTools',
)
a.binaries = [b for b in a.binaries
              if not any(os.path.basename(b[1]).startswith(p)
                         for p in _qt6_exclude_prefixes)]
# 同步过滤 Qt6 插件目录中不需要的子目录
_keep_plugin_dirs = {'platforms', 'styles'}
a.datas = [d for d in a.datas
           if not (d[1].startswith('PyQt6/Qt6/plugins/')
                   and d[1].split('/')[-2] not in _keep_plugin_dirs)]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ETFMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,              # 去除调试符号减小体积
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='etf_icon.ico',      # 自定义 ETF 主题图标
    version='version_info.txt',  # 文件属性详细信息
)
