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
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

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
    strip=False,
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
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'LSMinimumSystemVersion': '11.0',
        'LSUIElement': True,   # 后台运行：不显示 Dock 图标、不进 Cmd+Tab，仅托盘常驻
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
    },
)