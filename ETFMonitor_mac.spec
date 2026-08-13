# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 - ETF Monitor macOS 打包配置
将程序打包为 .app 应用包（单文件模式）
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
    # requests 相关
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    # JSON
    'json',
]

binaries = []
datas = []

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

# 过滤掉未使用模块对应的 Qt6 动态库,进一步减小体积
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
    upx=False,               # macOS/Apple Silicon 上 UPX 支持不可靠，关闭
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # 不显示终端窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.icns',        # 自定义应用图标
)

app = BUNDLE(
    exe,
    name='ETFMonitor.app',
    icon='icon.icns',        # 自定义应用图标
    bundle_identifier='com.etfmonitor.ETFMonitor',
    info_plist={
        'CFBundleDisplayName': 'ETF Monitor',
        'CFBundleName': 'ETFMonitor',
        'CFBundleShortVersionString': '1.0.4',
        'CFBundleVersion': '1.0.4',
        'LSMinimumSystemVersion': '11.0',
        'LSUIElement': True,   # 后台运行：不显示 Dock 图标、不进 Cmd+Tab，仅托盘常驻
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
    },
)