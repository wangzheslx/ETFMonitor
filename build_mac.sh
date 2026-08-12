#!/bin/bash
# ============================================
#   ETF Monitor - macOS PyInstaller 打包脚本
#   需在 macOS 上运行（PyInstaller 不支持交叉编译）
# ============================================

set -e

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo "============================================"
echo "  ETF Monitor - macOS 打包脚本"
echo "============================================"
echo ""

# 检查 python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 未找到 python3，请先安装 Python 3 (https://www.python.org/downloads/)"
    exit 1
fi

# 检查/安装依赖
python3 -c "import PyInstaller, PyQt6, requests" 2>/dev/null || {
    echo "[INFO] 缺少依赖，正在安装..."
    python3 -m pip install --user -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[ERROR] 依赖安装失败"
        exit 1
    fi
}

# 清理旧的构建文件
if [ -f "dist/ETFMonitor.app" ]; then
    rm -rf "dist/ETFMonitor.app"
fi
if [ -d "build" ]; then
    rm -rf "build"
fi

echo "[INFO] 开始打包..."
python3 -m PyInstaller --clean --noconfirm ETFMonitor_mac.spec

echo "[INFO] 对 .app 进行本地 adhoc 签名（Apple Silicon 上必需）..."
if command -v codesign >/dev/null 2>&1; then
    codesign --force --deep --sign - "dist/ETFMonitor.app"
fi

echo ""
echo "============================================"
echo "  打包成功!"
echo "  输出: dist/ETFMonitor.app"
echo "============================================"
echo ""
echo "[TIP] 首次运行如需签名："
echo "      codesign --force --deep --sign - dist/ETFMonitor.app"
