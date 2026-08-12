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
