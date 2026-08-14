"""
ETF 悬浮窗监控应用
- 半透明无边框悬浮窗，实时显示多只ETF价格
- 支持鼠标穿透、位置锁定
- 系统托盘图标，主窗口不显示在任务栏
- 托盘悬浮提示实时ETF行情，右键菜单快速操作
- 数据源可配置（新浪/腾讯），刷新频率可调
"""
import sys
import os
import json
import time
import re
import requests
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QInputDialog, QMessageBox, QDialog,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QColorDialog, QDialogButtonBox, QGroupBox, QCheckBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QSizePolicy, QStyleOptionSpinBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, pyqtSignal, QThread, QObject,
    QMimeData
)
from PyQt6.QtGui import (
    QFont, QColor, QAction, QIcon, QPainter, QPixmap, QPen,
    QBrush, QMouseEvent, QCursor
)

# ---------- 配置文件路径 ----------
# 使用 os.path 获取用户数据目录，兼容 exe 打包和源码运行
def _get_app_dir():
    """获取应用数据目录（优先 exe 所在目录，其次脚本目录）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的 exe
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

APP_DIR = _get_app_dir()
CONFIG_FILE = os.path.join(APP_DIR, "etf_config.json")

# ---------- 默认配置 ----------
DEFAULT_CONFIG = {
    "etf_codes": ["510050", "510300", "159915"],
    "data_source": "sina",       # sina / tencent
    "refresh_interval": 5,       # 秒
    "position": {"x": None, "y": None},
    "locked": False,
    "opacity": 0.75,
    "font_size": 12,
    "up_color": "#FF4444",       # 涨（红色）
    "down_color": "#00CC00",     # 跌（绿色）
    "text_color": "#E0E0E0",     # 普通文字颜色
    "bg_color": "#1A1A1A",       # 背景色
    "hover_tooltip_enabled": True,  # 鼠标悬停托盘图标时是否自动弹出行情卡片
}


def load_config():
    """加载配置，缺失字段用默认值填充"""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                # 用已保存的值覆盖默认值
                for k, v in saved.items():
                    cfg[k] = v
        except (json.JSONDecodeError, IOError):
            # 文件损坏则用默认配置覆盖
            pass
    # 确保 etf_codes 是列表
    if not isinstance(cfg.get("etf_codes"), list):
        cfg["etf_codes"] = DEFAULT_CONFIG["etf_codes"]
    return cfg


def save_config(cfg):
    """保存配置到磁盘"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ---------- 开机自启（macOS: LaunchAgent / Windows: 注册表 Run 项） ----------
AUTOSTART_LABEL = "ETFMonitor"
AUTOSTART_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.etfmonitor.ETFMonitor.plist")


def _get_autostart_command():
    """获取开机自启的注册命令。
    打包模式：返回 exe/app 路径；
    源码模式：返回 python 解释器 + main.py 脚本路径。
    Windows 返回字符串（写入注册表 REG_SZ），macOS 返回列表（ProgramArguments）。
    """
    if getattr(sys, "frozen", False):
        # 打包模式
        if sys.platform == "darwin":
            # .../ETFMonitor.app/Contents/MacOS/ETFMonitor -> .../ETFMonitor.app
            exe = os.path.abspath(sys.executable)
            app_path = os.path.dirname(os.path.dirname(os.path.dirname(exe)))
            return ["/usr/bin/open", "-a", app_path]
        return f'"{os.path.abspath(sys.executable)}"'
    # 源码模式：用 Python 解释器运行 main.py
    script = os.path.abspath(__file__)
    if sys.platform == "win32":
        # 优先用 pythonw.exe（无控制台窗口），找不到则回退到 python.exe
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, "pythonw.exe")
        python_exe = pythonw if os.path.exists(pythonw) else sys.executable
        return f'"{python_exe}" "{script}"'
    return [sys.executable, script]


def autostart_supported():
    """源码模式和打包模式均支持开机自启"""
    return True


def autostart_is_enabled():
    """读取系统真实状态（文件/注册表是否存在）"""
    if sys.platform == "darwin":
        return os.path.exists(AUTOSTART_PLIST)
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                winreg.QueryValueEx(key, AUTOSTART_LABEL)
                return True
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            return False
        except Exception:
            return False
    return False


def set_autostart(enabled):
    """开启/关闭开机自启，返回是否成功"""
    command = _get_autostart_command()
    if not command:
        return False
    try:
        if sys.platform == "darwin":
            import plistlib
            import subprocess
            os.makedirs(os.path.dirname(AUTOSTART_PLIST), exist_ok=True)
            if enabled:
                # command 已是列表：[/usr/bin/open, -a, app_path] 或 [python, script]
                plist = {
                    "Label": "com.etfmonitor.ETFMonitor",
                    "ProgramArguments": command,
                    "RunAtLoad": True,
                    "KeepAlive": False,
                }
                with open(AUTOSTART_PLIST, "wb") as f:
                    plistlib.dump(plist, f)
                subprocess.run(["launchctl", "load", AUTOSTART_PLIST],
                               capture_output=True, timeout=5)
            else:
                subprocess.run(["launchctl", "unload", AUTOSTART_PLIST],
                               capture_output=True, timeout=5)
                if os.path.exists(AUTOSTART_PLIST):
                    os.remove(AUTOSTART_PLIST)
            return True
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE)
            try:
                if enabled:
                    # command 已是字符串：'"exe"' 或 '"pythonw" "script"'
                    winreg.SetValueEx(key, AUTOSTART_LABEL, 0,
                                      winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, AUTOSTART_LABEL)
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
            return True
    except Exception:
        return False
    return False


# ---------- 数据获取 ----------
class ETFPriceFetcher(QObject):
    """在子线程中获取ETF价格数据"""
    data_ready = pyqtSignal(dict)  # {code: {"name":..., "price":..., "change_pct":..., "time":...}}
    error_occurred = pyqtSignal(str)

    def __init__(self, source="sina"):
        super().__init__()
        self.source = source
        self._stop = False

    def stop(self):
        self._stop = True

    def fetch(self, codes):
        """同步获取，在线程中调用"""
        try:
            if self.source == "sina":
                data = self._fetch_sina(codes)
            elif self.source == "tencent":
                data = self._fetch_tencent(codes)
            else:
                data = {}
            if not self._stop:
                self.data_ready.emit(data)
        except Exception as e:
            if not self._stop:
                self.error_occurred.emit(str(e))

    def _fetch_sina(self, codes):
        """新浪接口: 支持 shCODE / szCODE / 纯数字CODE 三种格式"""
        results = {}
        for code in codes:
            try:
                # 解析交易所前缀
                full, pure_code = self._resolve_code(code)
                url = f"https://hq.sinajs.cn/list={full}"
                resp = requests.get(url, timeout=5, headers={
                    "Referer": "https://finance.sina.com.cn"
                })
                resp.encoding = "gbk"
                text = resp.text.strip()
                if not text or "FAILED" in text:
                    continue
                quote_str = text.split('"')[1] if '"' in text else ""
                if not quote_str:
                    continue
                parts = quote_str.split(",")
                name = parts[0] if len(parts) > 0 else pure_code
                price = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
                prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
                # 用纯代码作为 key，方便与列表匹配
                results[pure_code] = {
                    "name": name,
                    "price": price,
                    "change_pct": round(change_pct, 2),
                    "time": datetime.now().strftime("%H:%M:%S"),
                }
            except Exception:
                continue
        return results

    @staticmethod
    def _resolve_code(code):
        """解析ETF代码，返回 (带前缀完整代码, 纯数字代码)"""
        code = code.strip().upper()
        # 已经是带前缀的格式
        if code.startswith(("SH", "SZ")):
            prefix = code[:2].lower()
            pure = code[2:]
            return f"{prefix}{pure}", pure
        # 纯数字，自动判断交易所
        if code.isdigit():
            if code.startswith(("5", "6", "9")):
                return f"sh{code}", code
            else:
                return f"sz{code}", code
        # 其他情况直接返回
        return code, code

    def _fetch_tencent(self, codes):
        """腾讯接口"""
        results = {}
        code_list = []
        code_map = {}  # 腾讯返回的 code -> 用户输入的纯代码
        for code in codes:
            full, pure = self._resolve_code(code)
            code_list.append(full)
            code_map[full] = pure
        if not code_list:
            return results
        try:
            url = f"https://qt.gtimg.cn/q={','.join(code_list)}"
            resp = requests.get(url, timeout=5)
            resp.encoding = "gbk"
            text = resp.text.strip()
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # v_sh510050="1~上证50ETF~510050~2.800~2.790~...~"
                quote_str = line.split('"')[1] if '"' in line else ""
                if not quote_str:
                    continue
                parts = quote_str.split("~")
                code_raw = parts[2] if len(parts) > 2 else ""
                name = parts[1] if len(parts) > 1 else code_raw
                price = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
                prev_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0.0
                change_pct = float(parts[32]) if len(parts) > 32 and parts[32] else 0.0
                # 用纯数字代码作为 key
                pure_code = code_raw
                results[pure_code] = {
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                    "time": datetime.now().strftime("%H:%M:%S"),
                }
        except Exception:
            pass
        return results


class FetchThread(QThread):
    """获取数据的线程"""
    def __init__(self, fetcher, codes):
        super().__init__()
        self.fetcher = fetcher
        self.codes = codes

    def run(self):
        self.fetcher.fetch(self.codes)


# ---------- ETF 全市场列表拉取（查询添加用） ----------
# 模块级缓存：全市场 ETF 列表（~1300 条）全局共享，避免重复请求
_ETF_LIST_CACHE = None        # list[dict]: [{"code": "159901", "name": "..."}, ...]
_ETF_LIST_CACHE_TIME = 0.0    # 缓存写入时间戳（time.time()）
_ETF_LIST_CACHE_TTL = 24 * 3600  # 缓存有效期 24 小时

# 磁盘缓存文件：首次成功拉取后持久化全量列表，后续网络差/被限流时用作离线兜底
_ETF_LIST_CACHE_FILE = os.path.join(APP_DIR, "etf_list_cache.json")


def _load_etf_disk_cache():
    """从磁盘加载上次成功拉取的 ETF 列表（离线兜底用）"""
    try:
        if os.path.exists(_ETF_LIST_CACHE_FILE):
            with open(_ETF_LIST_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass
    return None


def _save_etf_disk_cache(lst):
    """把完整列表持久化到磁盘，供下次离线兜底"""
    try:
        with open(_ETF_LIST_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False)
    except Exception:
        pass


# 启动即加载磁盘缓存：首次打开对话框能秒显示（哪怕离线），后台再尝试在线更新
_ETF_LIST_CACHE = _load_etf_disk_cache()

# 东方财富全量基金代码表（静态 JS 文件，无需 token）：
# 内容形如 var r = [["000001","HXCZHH","华夏成长混合","混合型-灵活","HUAXIACHENGZHANGHUNHE"],...]
# 第 0 列=代码、第 2 列=简称、第 3 列=类型；这里取名称含 "ETF" 且不含 "联接"、且代码属于场内段
# 注：原 push2.eastmoney.com/api/qt/clist/get 在本机被服务端直接断连（反爬/IP 封锁），改用此静态文件
_ETF_FUND_CODE_URL = "https://fund.eastmoney.com/js/fundcode_search.js"

# 场内代码段前缀：沪市 5 字头 / 深市 15/16/18 字头（剔除 0 字头场外联接基金）
_ETF_LIST_CODE_PREFIXES = (
    "51", "52", "53", "54", "55", "56", "57", "58",  # 沪市 ETF/LOF
    "15", "16", "18",                                  # 深市 ETF/LOF
)


class ETFBrowseFetcher(QObject):
    """在子线程中拉取全市场 ETF 列表（代码 + 名称），供查询添加使用"""

    data_ready = pyqtSignal(list)        # 累积列表，每页拉到就发一次（增量刷新）
    finished = pyqtSignal()              # 全部拉取结束（成功/失败收尾）
    error_occurred = pyqtSignal(str)

    def __init__(self, ignore_cache=False):
        super().__init__()
        self._stop = False
        self._ignore_cache = ignore_cache  # True 时跳过缓存读取，用于"重新加载"

    def stop(self):
        self._stop = True

    def fetch(self):
        """同步获取，在线程中调用。命中缓存则直接返回"""
        global _ETF_LIST_CACHE, _ETF_LIST_CACHE_TIME
        try:
            # 缓存命中（且未强制忽略）
            if (not self._ignore_cache
                    and _ETF_LIST_CACHE is not None
                    and (time.time() - _ETF_LIST_CACHE_TIME) < _ETF_LIST_CACHE_TTL):
                if not self._stop:
                    self.data_ready.emit(list(_ETF_LIST_CACHE))
                    self.finished.emit()
                return
            session = requests.Session()  # 复用连接(keep-alive)，减少握手、降低被限流概率
            text = None
            # 静态文件单次拉取带重试，避免偶发网络抖动导致整批丢失
            for _ in range(4):
                if self._stop:
                    return
                try:
                    resp = session.get(
                        _ETF_FUND_CODE_URL,
                        timeout=10,
                        headers={"User-Agent": "Mozilla/5.0",
                                 "Referer": "https://fund.eastmoney.com/"},
                    )
                    text = resp.text
                    # 简单校验：必须含 var r = [ 开头才算有效响应
                    if text and "var r" in text and "[" in text:
                        break
                    text = None
                except Exception:
                    text = None
                    if self._stop:
                        return
                    time.sleep(0.6 * (_ + 1))  # 退避重试：0.6 / 1.2 / 1.8 / 2.4s

            result = []
            if text:
                try:
                    # 正则提取每条记录的 代码 和 简称（第 0、2 列），鲁棒性高于 JSON 解析
                    for code, name in re.findall(
                            r'\["(\d{6})","[^"]*","([^"]*?)","[^"]*","[^"]*"\]', text):
                        # 过滤：名称含 ETF、不含联接（剔除场外联接基金）、代码属于场内段
                        if ("ETF" in name and "联接" not in name
                                and name
                                and code.startswith(_ETF_LIST_CODE_PREFIXES)):
                            result.append({"code": code, "name": name})
                    # 按代码升序，保持稳定展示
                    result.sort(key=lambda x: x["code"])
                except Exception:
                    result = []

            if result and len(result) >= 200:
                # 拉取相对完整：立即发给 UI + 写内存缓存 + 持久化
                if not self._stop:
                    self.data_ready.emit(list(result))
                _ETF_LIST_CACHE = result
                _ETF_LIST_CACHE_TIME = time.time()
                _save_etf_disk_cache(result)  # 持久化，供下次离线兜底
            else:
                # 在线失败或残缺：用磁盘缓存兜底，保证查询基本可用
                disk = _load_etf_disk_cache()
                if disk and len(disk) >= 200:
                    result = disk
                    if not self._stop:
                        self.data_ready.emit(list(result))
                elif not self._stop and result:
                    # 列表残缺但非空：仍发给 UI 显示（不写缓存，避免残缺数据污染）
                    self.data_ready.emit(list(result))
            if not self._stop:
                self.finished.emit()
        except Exception as e:
            if not self._stop:
                self.error_occurred.emit(str(e))


class ETFBrowseThread(QThread):
    """拉取 ETF 列表的线程（独立于 FetchThread，避免改动其带参签名）"""

    def __init__(self, fetcher):
        super().__init__()
        self.fetcher = fetcher

    def run(self):
        self.fetcher.fetch()


# ---------- 托盘图标生成 ----------
def create_tray_icon_pixmap(size=32, price_data=None, config=None):
    """生成系统托盘图标，有数据时显示首个ETF的涨跌幅"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if price_data and config:
        # 有数据时：显示首个ETF的涨跌幅作为图标
        codes = config.get("etf_codes", [])
        if codes and codes[0] in price_data:
            info = price_data[codes[0]]
            change = info.get("change_pct", 0)
            up_color = config.get("up_color", "#FF4444")
            down_color = config.get("down_color", "#00CC00")
            text_color = config.get("text_color", "#E0E0E0")

            if change > 0:
                bg_color = QColor(up_color)
                bg_color.setAlpha(180)
                fg_color = QColor("#FFFFFF")
                sign = "+"
            elif change < 0:
                bg_color = QColor(down_color)
                bg_color.setAlpha(180)
                fg_color = QColor("#FFFFFF")
                sign = ""
            else:
                bg_color = QColor(60, 60, 60, 180)
                fg_color = QColor(200, 200, 200)
                sign = ""

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(1, 1, size - 2, size - 2, 5, 5)

            painter.setPen(fg_color)
            font = QFont("Consolas", 9, QFont.Weight.Bold)
            painter.setFont(font)
            text = f"{sign}{change:.1f}%"
            painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, text)
        else:
            _draw_default_icon(painter, size)
    else:
        _draw_default_icon(painter, size)

    painter.end()
    return pixmap


def _draw_default_icon(painter, size):
    """默认图标：深灰圆角矩形 + E 文字"""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(60, 60, 60, 200))
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 6, 6)
    painter.setPen(QColor(200, 200, 200))
    font = QFont("Microsoft YaHei", 14, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "E")


# ---------- 添加/编辑ETF对话框 ----------
class ETFDialog(QDialog):
    """添加 ETF 对话框 - 支持交易所选择"""

    def __init__(self, parent=None, code="", title="添加 ETF"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(320, 180)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 10)

        # 标签
        lbl = QLabel("ETF 代码:")
        lbl.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        main_layout.addWidget(lbl)

        # 代码输入行（输入框 + 交易所下拉）
        code_row = QHBoxLayout()
        code_row.setSpacing(8)

        self.code_edit = QLineEdit(code)
        self.code_edit.setPlaceholderText("如: 510050")
        self.code_edit.setMaxLength(8)
        self.code_edit.setMinimumHeight(28)
        self.code_edit.returnPressed.connect(self.accept)
        code_row.addWidget(self.code_edit, stretch=2)

        # 交易所选择
        self.exchange_combo = QComboBox()
        self.exchange_combo.setMinimumHeight(28)
        self.exchange_combo.addItem("自动识别", "auto")
        self.exchange_combo.addItem("上海 (SH)", "sh")
        self.exchange_combo.addItem("深圳 (SZ)", "sz")
        self.exchange_combo.setToolTip("选择交易所前缀，或自动识别（5/6/9开头为上海）")
        code_row.addWidget(self.exchange_combo, stretch=1)

        main_layout.addLayout(code_row)

        # 提示
        hint = QLabel("自动识别：5/6/9 开头 → 上海，其余 → 深圳")
        hint.setStyleSheet("color: #888; font-size: 10px; background: transparent;")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)

        main_layout.addStretch()

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_ok = QPushButton("确定")
        btn_ok.setFixedWidth(80)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)
        main_layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background: #2A2A2A; }
            QLabel { color: #CCCCCC; background: transparent; }
            QLineEdit { background: #3A3A3A; color: #E0E0E0; border: 1px solid #555; padding: 4px 8px; border-radius: 3px; }
            QComboBox { background: #3A3A3A; color: #E0E0E0; border: 1px solid #555; padding: 4px 8px; border-radius: 3px; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView { background: #3A3A3A; color: #E0E0E0; selection-background-color: #2A6AB0; }
            QPushButton { background: #4A4A4A; color: #E0E0E0; border: 1px solid #666; padding: 6px 0px; border-radius: 3px; font-size: 12px; }
            QPushButton:hover { background: #5A5A5A; }
            QPushButton:pressed { background: #3A3A3A; }
            QPushButton[default="true"] { background: #2A6AB0; border: 1px solid #3A8AD0; }
            QPushButton[default="true"]:hover { background: #3A7AC0; }
        """)

    def get_code(self):
        """返回带交易所前缀的完整代码"""
        raw = self.code_edit.text().strip()
        if not raw:
            return ""
        exchange = self.exchange_combo.currentData()
        if exchange == "auto":
            return raw  # 纯数字，由 _resolve_code 自动判断
        elif exchange == "sh":
            return f"SH{raw}" if not raw.upper().startswith("SH") else raw.upper()
        elif exchange == "sz":
            return f"SZ{raw}" if not raw.upper().startswith("SZ") else raw.upper()
        return raw


# ---------- ETF 查询/浏览对话框 ----------
class ETFBrowseDialog(QDialog):
    """查询添加 ETF 对话框 - 拉取全市场 ETF 列表，按名称/代码搜索后批量加入"""

    def __init__(self, parent=None, existing_codes=None):
        super().__init__(parent)
        self.setWindowTitle("查询添加 ETF")
        self.setFixedSize(560, 520)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)

        # 已在监控列表中的代码，用于在列表里标记
        self._existing = set(c.strip() for c in (existing_codes or []))
        self._all_etfs = []          # 完整列表 [{code, name}]
        self._loaded = False
        self._browse_fetcher = None
        self._browse_thread = None

        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())

        # 打开后立即异步加载
        self._load_list()

    def _build_stylesheet(self):
        return """
            QDialog { background: #1F2128; color: #E6E8EC; font-size: 13px; }
            QLabel { color: #E6E8EC; background: transparent; }
            QLabel#hintLbl { color: #9099A8; font-size: 11px; }
            QLabel#statusLbl { color: #9099A8; font-size: 11px; padding: 2px 2px; }
            QLineEdit {
                background: #282B33; color: #E6E8EC; border: 1px solid #3A3F4B;
                border-radius: 6px; padding: 7px 10px;
            }
            QLineEdit:focus { border: 1px solid #3B82F6; }
            QListWidget {
                background: #282B33; color: #E6E8EC; border: 1px solid #3A3F4B;
                border-radius: 6px; padding: 4px; outline: none;
                font-size: 13px;
            }
            QListWidget::item { padding: 6px 10px; border-radius: 4px; }
            QListWidget::item:hover { background: #3A3F4B; }
            QListWidget::item:selected { background: #3B82F6; color: white; }
            QPushButton {
                background: #282B33; color: #E6E8EC; border: 1px solid #3A3F4B;
                border-radius: 6px; padding: 7px 16px; font-size: 13px;
            }
            QPushButton:hover { background: #3A3F4B; }
            QPushButton:pressed { background: #1F2128; }
            QPushButton#primaryBtn {
                background: #3B82F6; color: white; border: none; font-weight: bold;
            }
            QPushButton#primaryBtn:hover { background: #5B9CFF; }
        """

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # 搜索行
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_lbl = QLabel("搜索:")
        search_lbl.setFixedWidth(42)
        search_row.addWidget(search_lbl)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入代码或名称关键字，如 510050 或 创业板")
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit, stretch=1)

        self.btn_reload = QPushButton("重新加载")
        self.btn_reload.clicked.connect(lambda: self._load_list(force=True))
        search_row.addWidget(self.btn_reload)
        layout.addLayout(search_row)

        # 状态行
        self.status_label = QLabel("正在加载 ETF 列表...")
        self.status_label.setObjectName("statusLbl")
        layout.addWidget(self.status_label)

        # 结果列表（多选）
        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_list.setUniformItemSizes(True)
        self.result_list.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(self.result_list, stretch=1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        self.count_label = QLabel("共 0 条")
        self.count_label.setObjectName("hintLbl")
        btn_row.addWidget(self.count_label)
        btn_row.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(90)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("添加选中")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setFixedWidth(110)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    # ---------- 数据加载 ----------
    def _load_list(self, force=False):
        """异步加载 ETF 列表（force=True 时强制刷新缓存）"""
        if force and self._browse_thread and self._browse_thread.isRunning():
            return  # 正在加载，忽略
        # 命中缓存且非强制：直接同步填充
        if not force and _ETF_LIST_CACHE is not None and self._loaded is False:
            self._on_loaded(list(_ETF_LIST_CACHE))
            return

        # 强制刷新时清空旧内容，给用户即时反馈
        if force:
            self.result_list.clear()
            self._all_etfs = []
            self.count_label.setText("共 0 条")
        self.status_label.setText("正在重新加载 ETF 列表..." if force else "正在加载 ETF 列表...")
        self.status_label.repaint()

        # 清理上一个线程（如果有）
        self._cleanup_thread()

        # force 时让 fetcher 跳过缓存读取，强制走网络并覆盖缓存
        self._browse_fetcher = ETFBrowseFetcher(ignore_cache=force)
        self._browse_fetcher.data_ready.connect(self._on_loaded)
        self._browse_fetcher.error_occurred.connect(self._on_error)
        self._browse_fetcher.finished.connect(self._on_fetch_finished)
        self._browse_thread = ETFBrowseThread(self._browse_fetcher)
        self._browse_thread.start()

    def _on_loaded(self, etfs):
        # 增量刷新：每页拉取都会调用一次，保留当前搜索关键字
        self._all_etfs = etfs or []
        self._loaded = True
        self._apply_filter(self.search_edit.text().strip())
        # 拉取进行中显示进度，最终文案由 finished 信号设置
        loading = self._browse_thread and self._browse_thread.isRunning()
        if loading and self._all_etfs:
            self.status_label.setText(f"已加载 {len(self._all_etfs)} 只，后台继续拉取剩余…")
        elif self._all_etfs:
            self.status_label.setText(f"共 {len(self._all_etfs)} 只 ETF，可多选后点「添加选中」")
        else:
            self.status_label.setText("未获取到 ETF 列表，点「重新加载」重试")

    def _on_fetch_finished(self):
        """拉取全部结束（成功/失败收尾）后的最终状态文案"""
        if self._all_etfs:
            self.status_label.setText(f"共 {len(self._all_etfs)} 只 ETF，可多选后点「添加选中」")
        else:
            self.status_label.setText("未获取到 ETF 列表，点「重新加载」重试")

    def _on_error(self, msg):
        self._all_etfs = []
        self.result_list.clear()
        self.count_label.setText("共 0 条")
        self.status_label.setText(f"加载失败: {msg[:40]}，点「重新加载」重试")

    # ---------- 本地过滤 ----------
    def _on_search_changed(self, text):
        self._apply_filter(text.strip())

    def _apply_filter(self, keyword):
        self.result_list.clear()
        kw = keyword.lower()

        if kw:
            filtered = [e for e in self._all_etfs
                        if kw in e["code"].lower() or kw in e["name"].lower()]
            show = filtered
            self.count_label.setText(f"匹配 {len(filtered)} 条")
        else:
            # 空关键字：只渲染前 500 条，避免一次塞入千项卡顿
            show = self._all_etfs[:500]
            total = len(self._all_etfs)
            if total > 500:
                self.count_label.setText(f"显示前 500 / {total} 条，请输入关键字过滤")
            else:
                self.count_label.setText(f"共 {total} 条")

        for e in show:
            mark = "  （已在列表）" if e["code"] in self._existing else ""
            text = f"{e['name']}   ({e['code']}){mark}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, e["code"])
            if e["code"] in self._existing:
                # 已添加项用灰色区分
                item.setForeground(QColor("#6B7280"))
            self.result_list.addItem(item)

    def get_selected_codes(self):
        """返回选中项的纯数字代码列表（去重）"""
        codes = []
        seen = set()
        for item in self.result_list.selectedItems():
            code = item.data(Qt.ItemDataRole.UserRole)
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    # ---------- 线程清理 ----------
    def _cleanup_thread(self):
        if self._browse_thread and self._browse_thread.isRunning():
            self._browse_fetcher.stop()
            self._browse_thread.quit()
            if not self._browse_thread.wait(2000):
                self._browse_thread.terminate()
                self._browse_thread.wait(1000)
        if self._browse_fetcher:
            try:
                self._browse_fetcher.data_ready.disconnect(self._on_loaded)
                self._browse_fetcher.error_occurred.disconnect(self._on_error)
                self._browse_fetcher.finished.disconnect(self._on_fetch_finished)
            except Exception:
                pass

    def closeEvent(self, event):
        self._cleanup_thread()
        event.accept()


# ---------- 设置对话框 ----------
class ArrowedSpinBox(QSpinBox):
    """带实心箭头图标的 SpinBox，避免某些 Windows 主题下箭头不显示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)  # 隐藏默认箭头
        # 通过 paintEvent 自绘箭头按钮区域
        self._hover_up = False
        self._hover_down = False

    def wheelEvent(self, event):
        """禁用滚轮避免误操作，可按需启用"""
        super().wheelEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        # 在右侧绘制上下箭头按钮
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        rect = self.rect()
        btn_w = 18
        # 上箭头区域
        up_rect = QRect(rect.right() - btn_w, rect.top() + 1, btn_w, rect.height() // 2 - 1)
        down_rect = QRect(rect.right() - btn_w, rect.top() + rect.height() // 2, btn_w, rect.height() // 2 - 1)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 上箭头
        bg = QColor("#5A9CFF") if self._hover_up else QColor("#3A3F4B")
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(up_rect.adjusted(1, 1, -1, 0), 3, 3)
        painter.setBrush(QColor("#E6E8EC"))
        cx, cy = up_rect.center().x(), up_rect.center().y() + 1
        points = [QPoint(cx - 4, cy + 2), QPoint(cx + 4, cy + 2), QPoint(cx, cy - 2)]
        painter.drawPolygon(points)

        # 下箭头
        bg = QColor("#5A9CFF") if self._hover_down else QColor("#3A3F4B")
        painter.setBrush(bg)
        painter.drawRoundedRect(down_rect.adjusted(1, 0, -1, -1), 3, 3)
        painter.setBrush(QColor("#E6E8EC"))
        cx, cy = down_rect.center().x(), down_rect.center().y() - 1
        points = [QPoint(cx - 4, cy - 2), QPoint(cx + 4, cy - 2), QPoint(cx, cy + 2)]
        painter.drawPolygon(points)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self.rect()
            btn_w = 18
            up_rect = QRect(rect.right() - btn_w, rect.top() + 1, btn_w, rect.height() // 2 - 1)
            down_rect = QRect(rect.right() - btn_w, rect.top() + rect.height() // 2, btn_w, rect.height() // 2 - 1)
            if up_rect.contains(event.pos()):
                self.setValue(self.value() + self.singleStep())
                return
            elif down_rect.contains(event.pos()):
                self.setValue(self.value() - self.singleStep())
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        rect = self.rect()
        btn_w = 18
        up_rect = QRect(rect.right() - btn_w, rect.top() + 1, btn_w, rect.height() // 2 - 1)
        down_rect = QRect(rect.right() - btn_w, rect.top() + rect.height() // 2, btn_w, rect.height() // 2 - 1)
        self._hover_up = up_rect.contains(event.pos())
        self._hover_down = down_rect.contains(event.pos())
        self.update()


class SettingsDialog(QDialog):
    """设置对话框 - 现代风格布局，清晰分区"""

    # 统一配色（深色模式）
    COLOR_BG = "#1F2128"
    COLOR_BG_ALT = "#282B33"
    COLOR_BORDER = "#3A3F4B"
    COLOR_TEXT = "#E6E8EC"
    COLOR_TEXT_DIM = "#9099A8"
    COLOR_ACCENT = "#3B82F6"
    COLOR_ACCENT_HOVER = "#5B9CFF"
    COLOR_DANGER = "#EF4444"

    def __init__(self, parent, config, names=None):
        super().__init__(parent)
        # 深拷贝配置，避免直接修改原始对象
        self.config = dict(config)
        self.config["etf_codes"] = list(config.get("etf_codes", []))
        self._names = names or {}  # {code: name}，用于列表显示名称
        self.setWindowTitle("设置 · ETF 监控")
        self.setMinimumSize(480, 660)
        self.resize(520, 740)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self._build_ui()
        self.setStyleSheet(self._build_stylesheet())

    def _build_stylesheet(self):
        """生成统一样式表"""
        return f"""
        /* === 基础 === */
        QDialog {{
            background: {self.COLOR_BG};
            color: {self.COLOR_TEXT};
            font-size: 13px;
        }}
        QLabel {{ color: {self.COLOR_TEXT}; background: transparent; }}

        /* === 分组 === */
        QGroupBox {{
            background: {self.COLOR_BG_ALT};
            color: {self.COLOR_TEXT};
            border: 1px solid {self.COLOR_BORDER};
            border-radius: 8px;
            margin-top: 18px;
            padding: 16px 14px 10px 14px;
            font-weight: bold;
            font-size: 13px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            color: {self.COLOR_ACCENT};
            background: {self.COLOR_BG};
            border-radius: 3px;
        }}

        /* === 输入控件 === */
        QLineEdit, QComboBox, QSpinBox {{
            background: {self.COLOR_BG};
            color: {self.COLOR_TEXT};
            border: 1px solid {self.COLOR_BORDER};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 20px;
            selection-background-color: {self.COLOR_ACCENT};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {self.COLOR_ACCENT};
        }}

        /* ComboBox 下拉按钮 */
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid {self.COLOR_BORDER};
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
            background: {self.COLOR_BG_ALT};
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0; height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid {self.COLOR_TEXT_DIM};
        }}
        QComboBox QAbstractItemView {{
            background: {self.COLOR_BG_ALT};
            color: {self.COLOR_TEXT};
            selection-background-color: {self.COLOR_ACCENT};
            border: 1px solid {self.COLOR_BORDER};
            border-radius: 4px;
            padding: 4px;
            outline: none;
        }}

        /* SpinBox 上下箭头 - 仅修改背景，保留默认箭头渲染 */
        QSpinBox::up-button, QSpinBox::down-button {{
            subcontrol-origin: border;
            width: 20px;
            background: {self.COLOR_BG_ALT};
            border-left: 1px solid {self.COLOR_BORDER};
        }}
        QSpinBox::up-button {{
            border-top-right-radius: 5px;
        }}
        QSpinBox::down-button {{
            border-bottom-right-radius: 5px;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background: {self.COLOR_ACCENT};
            border-left: 1px solid {self.COLOR_ACCENT};
        }}

        /* === 按钮 === */
        QPushButton {{
            background: {self.COLOR_BG_ALT};
            color: {self.COLOR_TEXT};
            border: 1px solid {self.COLOR_BORDER};
            border-radius: 6px;
            padding: 8px 18px;
            font-size: 13px;
            min-height: 18px;
        }}
        QPushButton:hover {{
            background: {self.COLOR_BORDER};
            border-color: {self.COLOR_TEXT_DIM};
        }}
        QPushButton:pressed {{
            background: {self.COLOR_BG};
        }}
        QPushButton#primaryBtn {{
            background: {self.COLOR_ACCENT};
            color: white;
            border: none;
            font-weight: bold;
        }}
        QPushButton#primaryBtn:hover {{
            background: {self.COLOR_ACCENT_HOVER};
        }}
        QPushButton#dangerBtn:hover {{
            background: {self.COLOR_DANGER};
            color: white;
            border-color: {self.COLOR_DANGER};
        }}

        /* === 复选框 === */
        QCheckBox {{
            color: {self.COLOR_TEXT};
            spacing: 10px;
            padding: 4px 0;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {self.COLOR_BORDER};
            background: {self.COLOR_BG};
        }}
        QCheckBox::indicator:checked {{
            background: {self.COLOR_ACCENT};
            border-color: {self.COLOR_ACCENT};
        }}

        /* === 列表 === */
        QListWidget {{
            background: {self.COLOR_BG};
            color: {self.COLOR_TEXT};
            border: 1px solid {self.COLOR_BORDER};
            border-radius: 6px;
            padding: 4px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: 4px;
            margin: 2px 0;
        }}
        QListWidget::item:hover {{
            background: {self.COLOR_BORDER};
        }}
        QListWidget::item:selected {{
            background: {self.COLOR_ACCENT};
            color: white;
        }}

        /* === 表单标签 === */
        QLabel[role="formLabel"] {{
            color: {self.COLOR_TEXT_DIM};
            font-size: 12px;
            min-width: 80px;
        }}
        QLabel[role="hint"] {{
            color: {self.COLOR_TEXT_DIM};
            font-size: 11px;
            padding: 2px 4px;
        }}
        """

    def _make_form_row(self, label_text, widget, hint_text=None):
        """创建统一的表单行（标签 + 控件 + 可选提示）"""
        row = QHBoxLayout()
        row.setSpacing(10)

        lbl = QLabel(label_text)
        lbl.setProperty("role", "formLabel")
        lbl.setFixedWidth(72)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(lbl)

        row.addWidget(widget, stretch=1)

        if hint_text:
            hint = QLabel(hint_text)
            hint.setProperty("role", "hint")
            row.addWidget(hint)

        return row

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        outer.setContentsMargins(18, 18, 18, 18)

        # === 1. ETF 列表 ===
        grp_etf = QGroupBox("监控列表")
        grp_layout = QVBoxLayout(grp_etf)
        grp_layout.setSpacing(8)
        grp_layout.setContentsMargins(10, 14, 10, 10)

        # 列表
        self.etf_list = QListWidget()
        self.etf_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.etf_list.setMinimumHeight(140)
        self.etf_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.etf_list.setUniformItemSizes(True)
        self.etf_list.itemDoubleClicked.connect(self._on_edit_item)
        self._refresh_etf_list()
        grp_layout.addWidget(self.etf_list, stretch=1)

        # 操作行 - 独立且标签在右
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_add = QPushButton("添加")
        self.btn_add.setObjectName("primaryBtn")
        self.btn_add.setMinimumWidth(80)
        self.btn_add.setMinimumHeight(30)
        self.btn_add.clicked.connect(self._on_add)
        action_row.addWidget(self.btn_add)

        self.btn_browse = QPushButton("查询添加")
        self.btn_browse.setObjectName("primaryBtn")
        self.btn_browse.setMinimumWidth(90)
        self.btn_browse.setMinimumHeight(30)
        self.btn_browse.setToolTip("按名称/代码搜索全市场 ETF 并批量添加")
        self.btn_browse.clicked.connect(self._on_browse)
        action_row.addWidget(self.btn_browse)

        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("dangerBtn")
        self.btn_del.setMinimumWidth(80)
        self.btn_del.setMinimumHeight(30)
        self.btn_del.clicked.connect(self._on_delete)
        action_row.addWidget(self.btn_del)

        action_row.addStretch()

        hint = QLabel("双击列表项可编辑")
        hint.setProperty("role", "hint")
        action_row.addWidget(hint)

        grp_layout.addLayout(action_row)
        outer.addWidget(grp_etf, stretch=4)

        # === 2. 数据源 + 刷新频率 (横向并列) ===
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # 数据源
        grp_src = QGroupBox("数据源")
        src_layout = QVBoxLayout(grp_src)
        src_layout.setContentsMargins(10, 14, 10, 10)
        src_layout.setSpacing(6)
        self.src_combo = QComboBox()
        self.src_combo.addItem("新浪财经", "sina")
        self.src_combo.addItem("腾讯财经", "tencent")
        cur = self.config.get("data_source", "sina")
        idx = self.src_combo.findData(cur)
        if idx >= 0:
            self.src_combo.setCurrentIndex(idx)
        src_layout.addWidget(self.src_combo)
        row1.addWidget(grp_src, stretch=1)

        # 刷新间隔
        grp_refresh = QGroupBox("刷新频率")
        ref_layout = QVBoxLayout(grp_refresh)
        ref_layout.setContentsMargins(10, 14, 10, 10)
        ref_layout.setSpacing(6)
        self.refresh_spin = ArrowedSpinBox()
        self.refresh_spin.setRange(1, 300)
        self.refresh_spin.setSuffix(" 秒")
        self.refresh_spin.setValue(self.config.get("refresh_interval", 5))
        ref_layout.addWidget(self.refresh_spin)
        row1.addWidget(grp_refresh, stretch=1)

        outer.addLayout(row1)

        # === 3. 外观 (透明度 + 字号) ===
        grp_appear = QGroupBox("外观")
        app_layout = QVBoxLayout(grp_appear)
        app_layout.setContentsMargins(10, 14, 10, 10)
        app_layout.setSpacing(10)

        self.opacity_spin = ArrowedSpinBox()
        self.opacity_spin.setRange(20, 100)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setValue(int(self.config.get("opacity", 0.75) * 100))
        app_layout.addLayout(self._make_form_row("透明度", self.opacity_spin))

        self.font_spin = ArrowedSpinBox()
        self.font_spin.setRange(8, 24)
        self.font_spin.setSuffix(" px")
        self.font_spin.setValue(self.config.get("font_size", 12))
        app_layout.addLayout(self._make_form_row("字号", self.font_spin))

        # grp_appear 留到下方与“行为”并排

        # === 4. 行为 (开关) ===
        grp_behave = QGroupBox("行为")
        bh_layout = QVBoxLayout(grp_behave)
        bh_layout.setContentsMargins(10, 14, 10, 10)
        bh_layout.setSpacing(4)
        self.lock_cb = QCheckBox("锁定悬浮窗位置（禁止拖动）")
        self.lock_cb.setChecked(self.config.get("locked", False))
        bh_layout.addWidget(self.lock_cb)

        self.hover_cb = QCheckBox("鼠标悬停托盘图标时显示行情卡片")
        self.hover_cb.setChecked(self.config.get("hover_tooltip_enabled", True))
        self.hover_cb.setToolTip("关闭后可避免行情卡片遮挡右键菜单")
        bh_layout.addWidget(self.hover_cb)

        self.autostart_cb = QCheckBox("开机自启（登录后自动启动到托盘）")
        if autostart_supported():
            self.autostart_cb.setChecked(autostart_is_enabled())
        else:
            self.autostart_cb.setEnabled(False)
            self.autostart_cb.setToolTip("源码模式下不可用，请使用打包后的应用")
        bh_layout.addWidget(self.autostart_cb)

        # 外观 + 行为 横向并排，节省垂直空间给监控列表
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(grp_appear)
        row2.addWidget(grp_behave)
        outer.addLayout(row2)

        # === 底部按钮 ===
        outer.addStretch(1)
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()
        btn_reset = QPushButton("恢复默认")
        btn_reset.clicked.connect(self._on_reset)
        btn_box.addWidget(btn_reset)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_ok = QPushButton("保存")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)
        outer.addLayout(btn_box)

    def _refresh_etf_list(self):
        self.etf_list.clear()
        codes = self.config.get("etf_codes", [])
        if not codes:
            placeholder = QListWidgetItem("（暂无添加 ETF，请点击下方 添加 按钮）")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)  # 不可选中/编辑
            foreground = QColor(self.COLOR_TEXT_DIM)
            placeholder.setForeground(foreground)
            self.etf_list.addItem(placeholder)
            return
        for code in codes:
            name = self._names.get(code, "")
            label = f"{code}  {name}" if name else code
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.etf_list.addItem(item)

    def _on_add(self):
        dlg = ETFDialog(self, title="添加 ETF")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            code = dlg.get_code()
            if code:
                codes = self.config.get("etf_codes", [])
                if code not in codes:
                    codes.append(code)
                    self.config["etf_codes"] = codes
                    self._refresh_etf_list()
                    save_config(self.config)

    def _on_browse(self):
        """打开 ETF 查询对话框，批量添加选中项"""
        dlg = ETFBrowseDialog(self, existing_codes=self.config.get("etf_codes", []))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_codes = dlg.get_selected_codes()
            if not new_codes:
                return
            codes = self.config.get("etf_codes", [])
            added = 0
            for code in new_codes:
                if code not in codes:
                    codes.append(code)
                    added += 1
            self.config["etf_codes"] = codes
            self._refresh_etf_list()
            save_config(self.config)
            if added == 0:
                QMessageBox.information(self, "提示", "所选 ETF 已在监控列表中")
            else:
                QMessageBox.information(self, "已添加", f"成功添加 {added} 只 ETF")

    def _on_delete(self):
        # 跳过占位项
        if self.etf_list.count() <= 0:
            return
        row = self.etf_list.currentRow()
        if row < 0:
            # 默认删除最后一项
            row = self.etf_list.count() - 1
        item = self.etf_list.item(row)
        # 用 UserRole 区分真项（有 code）与占位项（None）
        if item and item.data(Qt.ItemDataRole.UserRole):
            codes = self.config.get("etf_codes", [])
            if row < len(codes):
                del codes[row]
                self.config["etf_codes"] = codes
                self._refresh_etf_list()
                save_config(self.config)

    def _on_edit_item(self, item):
        """双击列表项编辑 ETF 代码"""
        code = item.data(Qt.ItemDataRole.UserRole)
        if not code:
            return
        dlg = ETFDialog(self, code=code, title="编辑 ETF")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_code = dlg.get_code()
            if not new_code or new_code == code:
                return
            codes = self.config.get("etf_codes", [])
            if new_code in codes:
                QMessageBox.information(self, "提示", "该 ETF 已在列表中")
                return
            if code in codes:
                idx = codes.index(code)
                codes[idx] = new_code
                self.config["etf_codes"] = codes
                self._refresh_etf_list()
                save_config(self.config)

    def _on_reset(self):
        """恢复默认设置"""
        self.src_combo.setCurrentIndex(self.src_combo.findData("sina"))
        self.refresh_spin.setValue(5)
        self.opacity_spin.setValue(75)
        self.font_spin.setValue(12)
        self.lock_cb.setChecked(False)
        self.hover_cb.setChecked(True)

    def _on_ok(self):
        codes = []
        for i in range(self.etf_list.count()):
            item = self.etf_list.item(i)
            # 用 UserRole 取纯代码，跳过占位项
            code = item.data(Qt.ItemDataRole.UserRole)
            if code:
                codes.append(code)
        self.config["etf_codes"] = codes
        self.config["data_source"] = self.src_combo.currentData()
        self.config["refresh_interval"] = self.refresh_spin.value()
        self.config["opacity"] = self.opacity_spin.value() / 100.0
        self.config["font_size"] = self.font_spin.value()
        self.config["locked"] = self.lock_cb.isChecked()
        self.config["hover_tooltip_enabled"] = self.hover_cb.isChecked()
        if autostart_supported():
            set_autostart(self.autostart_cb.isChecked())
        save_config(self.config)
        self.accept()


# ---------- 悬浮窗主窗口 ----------
class ETFOverlayWidget(QWidget):
    """半透明无边框悬浮窗"""
    # 数据更新信号，供托盘更新 tooltip 和图标
    data_updated = pyqtSignal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.price_data = {}  # {code: {...}}
        self.dragging = False
        self.drag_start_pos = QPoint()
        self.window_start_pos = QPoint()
        # 窗口标志
        self._apply_window_flags()

        # 设置透明度
        self.setWindowOpacity(self.config.get("opacity", 0.75))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # 样式
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.config.get('bg_color', '#1A1A1A')};
                color: {self.config.get('text_color', '#E0E0E0')};
                font-family: "Microsoft YaHei", "Consolas", monospace;
                font-size: {self.config.get('font_size', 12)}px;
                border-radius: 8px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                padding: 1px 4px;
            }}
        """)

        # 布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 4, 6, 4)
        self.main_layout.setSpacing(1)

        # 标题行
        self.title_label = QLabel("ETF 监控")
        title_font = QFont("Microsoft YaHei", self.config.get("font_size", 12) - 1, QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(f"color: {self.config.get('text_color', '#E0E0E0')}; padding: 2px 4px;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        # 分隔线
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444444;")
        self.main_layout.addWidget(sep)

        # 价格行容器
        self.price_widgets = {}  # code -> QLabel
        self.price_layout = QVBoxLayout()
        self.price_layout.setSpacing(0)
        self.main_layout.addLayout(self.price_layout)

        # 状态行
        self.status_label = QLabel("等待数据...")
        self.status_label.setStyleSheet(f"color: #888888; font-size: {max(8, self.config.get('font_size', 12) - 3)}px; padding: 2px 4px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.status_label)

        self._rebuild_price_rows()
        self.adjustSize()

        # 恢复位置
        pos = self.config.get("position", {})
        x, y = pos.get("x"), pos.get("y")
        if x is not None and y is not None:
            self.move(x, y)
        else:
            # 默认右下角
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(geo.right() - self.width() - 20, geo.bottom() - self.height() - 80)

        # 数据获取器
        self.fetcher = ETFPriceFetcher(self.config.get("data_source", "sina"))
        self.fetch_thread = None

        # 定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._do_fetch)
        self.timer.start(self.config.get("refresh_interval", 5) * 1000)

    def _apply_window_flags(self):
        """设置窗口标志：无边框、置顶、不在任务栏显示、鼠标穿透"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        # 鼠标穿透（默认不锁定时可交互）
        if not self.config.get("locked", False):
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def set_mouse_pass_through(self, enabled):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if enabled:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowTransparentForInput)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowTransparentForInput)
        self.show()

    def _rebuild_price_rows(self):
        """重建价格显示行"""
        # 清除旧控件的 QLabel
        for code, widgets in list(self.price_widgets.items()):
            for key in ("code", "name", "price", "change"):
                w = widgets.get(key)
                if w:
                    try:
                        self.price_layout.removeWidget(w)
                        w.deleteLater()
                    except Exception:
                        pass
        self.price_widgets.clear()

        # 清除 price_layout 中所有子布局
        while self.price_layout.count():
            item = self.price_layout.takeAt(0)
            if item.layout():
                self._clear_layout(item.layout())
            if item.widget():
                try:
                    item.widget().deleteLater()
                except Exception:
                    pass

        codes = self.config.get("etf_codes", [])
        for code in codes:
            row = QHBoxLayout()
            row.setSpacing(4)
            code_lbl = QLabel(code)
            code_lbl.setFixedWidth(65)
            code_lbl.setStyleSheet(f"color: #AAAAAA; font-size: {self.config.get('font_size', 12) - 1}px;")
            row.addWidget(code_lbl)

            name_lbl = QLabel("--")
            name_lbl.setFixedWidth(75)
            name_lbl.setStyleSheet(f"color: #CCCCCC; font-size: {self.config.get('font_size', 12) - 1}px;")
            row.addWidget(name_lbl)

            price_lbl = QLabel("----")
            price_lbl.setFixedWidth(60)
            price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(price_lbl)

            change_lbl = QLabel("--.--%")
            change_lbl.setFixedWidth(60)
            change_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(change_lbl)

            self.price_layout.addLayout(row)
            self.price_widgets[code] = {
                "code": code_lbl,
                "name": name_lbl,
                "price": price_lbl,
                "change": change_lbl,
            }

    def update_config(self, config):
        """更新配置并刷新界面"""
        old_codes = self.config.get("etf_codes", [])
        new_codes = config.get("etf_codes", [])
        old_interval = self.config.get("refresh_interval", 5)

        self.config = config

        # 应用新设置
        self.setWindowOpacity(config.get("opacity", 0.75))
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {config.get('bg_color', '#1A1A1A')};
                color: {config.get('text_color', '#E0E0E0')};
                font-family: "Microsoft YaHei", "Consolas", monospace;
                font-size: {config.get('font_size', 12)}px;
                border-radius: 8px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                padding: 1px 4px;
            }}
        """)

        # 锁定/穿透
        self.set_mouse_pass_through(config.get("locked", False))

        # ETF 列表变化时重建
        if set(old_codes) != set(new_codes):
            self._rebuild_price_rows()
            self.price_data = {}
            self.adjustSize()

        # 数据源变化
        self.fetcher.source = config.get("data_source", "sina")

        # 刷新间隔变化
        new_interval = config.get("refresh_interval", 5)
        if old_interval != new_interval:
            self.timer.setInterval(new_interval * 1000)

        self._do_fetch()

    def _do_fetch(self):
        """触发数据获取"""
        codes = self.config.get("etf_codes", [])
        if not codes:
            self.status_label.setText("无 ETF 代码")
            self.data_updated.emit({})
            return
        # 停止上一个线程
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetcher.stop()
            self.fetch_thread.quit()
            if not self.fetch_thread.wait(2000):
                self.fetch_thread.terminate()
                self.fetch_thread.wait(1000)
        # 断开旧连接，避免重复信号
        if self.fetch_thread:
            try:
                self.fetcher.data_ready.disconnect(self._on_data_ready)
                self.fetcher.error_occurred.disconnect(self._on_error)
            except Exception:
                pass
        # 创建新线程
        self.fetcher = ETFPriceFetcher(self.config.get("data_source", "sina"))
        self.fetcher.data_ready.connect(self._on_data_ready)
        self.fetcher.error_occurred.connect(self._on_error)
        self.fetch_thread = FetchThread(self.fetcher, codes)
        self.fetch_thread.finished.connect(self._on_fetch_finished)
        self.fetch_thread.start()

    def _on_fetch_finished(self):
        """线程结束清理"""
        try:
            self.fetcher.data_ready.disconnect(self._on_data_ready)
            self.fetcher.error_occurred.disconnect(self._on_error)
        except Exception:
            pass

    def _on_data_ready(self, data):
        """处理返回的数据"""
        try:
            self.price_data.update(data)
            self._update_display()
        except Exception:
            pass  # 防止 widget 已删除导致的崩溃

    def _on_error(self, msg):
        try:
            self.status_label.setText(f"获取失败: {msg[:20]}")
        except Exception:
            pass

    def _on_error(self, msg):
        self.status_label.setText(f"获取失败: {msg[:20]}")

    def _update_display(self):
        """更新显示"""
        codes = self.config.get("etf_codes", [])
        up_color = self.config.get("up_color", "#FF4444")
        down_color = self.config.get("down_color", "#00CC00")
        font_size = self.config.get("font_size", 12)

        all_ok = True
        for code in codes:
            widgets = self.price_widgets.get(code)
            if not widgets:
                continue
            info = self.price_data.get(code)
            if info:
                widgets["name"].setText(info.get("name", code)[:5])
                price = info.get("price", 0)
                widgets["price"].setText(f"{price:.3f}" if price else "----")
                change = info.get("change_pct", 0)
                if change > 0:
                    color = up_color
                elif change < 0:
                    color = down_color
                else:
                    color = self.config.get("text_color", "#E0E0E0")
                sign = "+" if change > 0 else ""
                widgets["change"].setText(f"{sign}{change:.2f}%")
                widgets["price"].setStyleSheet(f"color: {color}; font-size: {font_size}px;")
                widgets["change"].setStyleSheet(f"color: {color}; font-size: {font_size}px;")
            else:
                widgets["name"].setText("--")
                widgets["price"].setText("----")
                widgets["change"].setText("--.--%")
                all_ok = False

        if all_ok and self.price_data:
            latest_time = max((v.get("time", "") for v in self.price_data.values()), default="")
            self.status_label.setText(f"更新: {latest_time}")
        elif not all_ok:
            self.status_label.setText("部分数据获取失败")

        self.adjustSize()
        # 发射信号通知托盘更新
        self.data_updated.emit(self.price_data)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.config.get("locked", False):
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint()
            self.window_start_pos = self.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            self.move(self.window_start_pos + delta)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            # 保存位置
            self.config["position"] = {"x": self.x(), "y": self.y()}
            save_config(self.config)

    @staticmethod
    def _clear_layout(layout):
        """递归清除布局中的所有子项"""
        while layout.count():
            item = layout.takeAt(0)
            if item.layout():
                ETFOverlayWidget._clear_layout(item.layout())
            if item.widget():
                try:
                    item.widget().deleteLater()
                except Exception:
                    pass

    def closeEvent(self, event):
        self.timer.stop()
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetcher.stop()
            self.fetch_thread.quit()
            self.fetch_thread.wait(2000)
        self.config["position"] = {"x": self.x(), "y": self.y()}
        save_config(self.config)
        event.accept()


# ---------- 自定义托盘 ToolTip ----------
class TrayTooltip(QWidget):
    """无边框、自定义绘制、可固定宽度的托盘悬浮窗口"""

    def __init__(self):
        super().__init__()
        # 无边框、置顶、不在任务栏显示、可点击穿透背景
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        # 鼠标穿透：纯展示窗口，让点击/右键穿过它落到下层（如托盘图标），避免遮挡
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setMinimumWidth(220)  # 最小宽度，根据内容自适应
        self.setMaximumWidth(400)
        self._build_ui()

    def _build_ui(self):
        # 使用普通 Widget + QLabel 列表而非 QTextEdit，确保单行显示
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(4)

        # 标题
        self.title_label = QLabel("ETF 监控")
        title_font = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #5B9CFF; background: transparent; padding: 2px 0;")
        main_layout.addWidget(self.title_label)

        # 分隔线
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3A3F4B;")
        main_layout.addWidget(sep)

        # 数据行容器
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(2)
        main_layout.addLayout(self.rows_layout)

        self.setStyleSheet("""
            QWidget {
                background: #1F2128;
                border: 1px solid #3A3F4B;
                border-radius: 6px;
                color: #E6E8EC;
                font-family: "Microsoft YaHei", "Consolas";
                font-size: 11px;
            }
            QLabel { background: transparent; border: none; padding: 0; }
        """)

    def update_data(self, config, price_data):
        """更新数据 - 每列独立 QLabel，确保严格对齐"""
        # 清空旧行
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.layout():
                self._clear_row_layout(item.layout())
            if item.widget():
                item.widget().deleteLater()

        codes = config.get("etf_codes", [])
        up_color = config.get("up_color", "#FF4444")
        down_color = config.get("down_color", "#00CC00")

        if not codes:
            lbl = QLabel("（未添加 ETF）")
            lbl.setStyleSheet("color: #9099A8; background: transparent; font-size: 11px;")
            self.rows_layout.addWidget(lbl)
            return

        if not price_data:
            for code in codes:
                lbl = QLabel(f"{code}  等待数据...")
                lbl.setStyleSheet("color: #9099A8; background: transparent; font-size: 11px;")
                self.rows_layout.addWidget(lbl)
            return

        for code in codes:
            info = price_data.get(code)
            if info:
                name = info.get("name", code)
                price = info.get("price", 0)
                change = info.get("change_pct", 0)
                sign = "+" if change > 0 else ""
                arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
                color = up_color if change > 0 else (down_color if change < 0 else "#9099A8")

                row = QHBoxLayout()
                row.setSpacing(6)

                # 代码 - 固定 48px
                code_lbl = QLabel(code)
                code_lbl.setFixedWidth(48)
                code_lbl.setStyleSheet("color: #AAAAAA; background: transparent; font-size: 11px;")
                row.addWidget(code_lbl)

                # 名称 - 固定 72px，超出省略
                name_lbl = QLabel(name)
                name_lbl.setFixedWidth(72)
                name_lbl.setStyleSheet("color: #E6E8EC; background: transparent; font-size: 11px;")
                row.addWidget(name_lbl)

                # 价格 - 固定 60px，右对齐
                price_lbl = QLabel(f"{price:.3f}")
                price_lbl.setFixedWidth(60)
                price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                price_lbl.setStyleSheet(f"color: {color}; background: transparent; font-size: 11px;")
                row.addWidget(price_lbl)

                # 涨跌幅 - 固定 72px，右对齐
                change_text = f"{arrow}{sign}{change:.2f}%"
                change_lbl = QLabel(change_text)
                change_lbl.setFixedWidth(72)
                change_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                change_lbl.setStyleSheet(f"color: {color}; background: transparent; font-size: 11px;")
                row.addWidget(change_lbl)

                self.rows_layout.addLayout(row)
            else:
                lbl = QLabel(f"{code}  数据获取失败")
                lbl.setStyleSheet("color: #9099A8; background: transparent; font-size: 11px;")
                self.rows_layout.addWidget(lbl)

        self.adjustSize()

    @staticmethod
    def _clear_row_layout(layout):
        """递归清理布局中的所有控件"""
        while layout.count():
            item = layout.takeAt(0)
            if item.layout():
                TrayTooltip._clear_row_layout(item.layout())
            if item.widget():
                item.widget().deleteLater()

    def show_at(self, pos):
        """在指定位置（托盘图标位置）显示"""
        self.show()
        # 调整位置：显示在托盘图标上方
        screen = QApplication.screenAt(pos)
        if screen:
            geo = screen.availableGeometry()
            x = pos.x() - self.width() // 2
            y = pos.y() - self.height() - 5
            # 防止超出屏幕
            x = max(geo.left() + 5, min(x, geo.right() - self.width() - 5))
            y = max(geo.top() + 5, y)
            self.move(x, y)
        self.raise_()


# ---------- 托盘管理类 ----------
class TrayApp(QApplication):
    """管理系统托盘，连接悬浮窗数据与托盘显示"""

    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        # 设置应用图标
        icon_path = os.path.join(APP_DIR, "etf_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.config = load_config()
        self._tray_tooltip_cache = "ETF 监控"

        # 创建悬浮窗
        self.overlay = ETFOverlayWidget(self.config)
        self.overlay.show()

        # 连接数据更新信号
        self.overlay.data_updated.connect(self._on_data_updated)

        # 创建系统托盘
        self.tray = QSystemTrayIcon(self)
        self._update_tray_icon()  # 初始图标
        # 使用自定义 ToolTip 窗口代替系统 ToolTip
        self.tray_tooltip = TrayTooltip()
        self.tray.setToolTip("")  # 清空系统 tooltip，避免重复显示

        self.tray.show()

        # 定时检测鼠标是否悬停在托盘图标上（QSystemTrayIcon 无 hovered 信号）
        self._hover_check_timer = QTimer(self)
        self._hover_check_timer.setInterval(400)
        self._hover_check_timer.timeout.connect(self._check_tray_hover)
        self._hover_check_timer.start()

        # 统一用 activated 信号处理所有托盘事件
        # setContextMenu 在部分 Windows 版本中不可靠，改用手动弹出
        self.tray.activated.connect(self._on_tray_activated)

    # ---------- 数据更新回调 ----------
    def _on_data_updated(self, price_data):
        """悬浮窗数据更新时同步刷新托盘图标和 tooltip"""
        self._update_tray_icon()
        self._update_tray_tooltip(price_data)

    def _update_tray_icon(self):
        """根据最新价格数据更新托盘图标"""
        icon = QIcon(create_tray_icon_pixmap(
            32,
            price_data=self.overlay.price_data,
            config=self.config
        ))
        self.tray.setIcon(icon)

    def _update_tray_tooltip(self, price_data):
        """更新托盘悬浮提示（使用自定义 ToolTip 窗口，避免系统换行）"""
        # 不再使用系统的 setToolTip，由 TrayTooltip 类自定义渲染
        # 只需更新缓存的 tooltip 数据
        if not self.tray_tooltip:
            self.tray_tooltip = TrayTooltip()
        self.tray_tooltip.update_data(self.config, price_data)

    # ---------- 操作 ----------
    def _show_overlay(self):
        if not self.overlay.isVisible():
            self.overlay.show()
        # 确保窗口在最前
        self.overlay.raise_()
        self.overlay.activateWindow()

    def _hide_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()

    def _toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.activateWindow()

    def _refresh_now(self):
        self.overlay._do_fetch()

    def _on_toggle_hover(self, checked):
        """切换“鼠标悬停显示行情卡片”开关，实时生效并落盘"""
        self.config["hover_tooltip_enabled"] = checked
        save_config(self.config)
        if not checked:
            self.tray_tooltip.hide()  # 立即隐藏当前可能正在显示的卡片

    def _on_toggle_autostart(self, checked):
        """切换开机自启（写入/删除系统的 LaunchAgent 或注册表项）"""
        ok = set_autostart(checked)
        if not ok:
            QMessageBox.warning(self.overlay, "开机自启", "设置失败，请检查系统权限。")
        # 实际状态以系统为准，不写入 config

    def _open_settings(self):
        # 构建 code->name 映射：优先实时行情数据，其次 ETF 全市场缓存
        names = {}
        for code, info in self.overlay.price_data.items():
            n = info.get("name")
            if n:
                names[code] = n
        if _ETF_LIST_CACHE:
            for e in _ETF_LIST_CACHE:
                c = e.get("code")
                if c and c not in names:
                    names[c] = e.get("name", "")
        # 使用悬浮窗作为父窗口，确保对话框能正常获取焦点
        dlg = SettingsDialog(self.overlay, dict(self.config), names=names)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            self.config = dlg.config
            save_config(self.config)
            self.overlay.update_config(self.config)
            self._update_tray_icon()

    def _check_tray_hover(self):
        """定时检测鼠标是否在托盘图标上，控制自定义 tooltip 显示"""
        # 悬停提示被关闭：确保隐藏并直接返回，不做任何检测
        if not self.config.get("hover_tooltip_enabled", True):
            if self.tray_tooltip.isVisible():
                self.tray_tooltip.hide()
            return
        geom = self.tray.geometry()
        if not geom.isValid():
            self.tray_tooltip.hide()
            return
        # 扩展检测区域（托盘图标可能很小，给 4px 容差）
        cursor_pos = QCursor.pos()
        hit_rect = geom.adjusted(-4, -4, 4, 4)
        if hit_rect.contains(cursor_pos):
            if not self.tray_tooltip.isVisible():
                self.tray_tooltip.show_at(geom.center())
        else:
            # 如果鼠标也不在 tooltip 上，隐藏
            if not self.tray_tooltip.geometry().contains(cursor_pos):
                self.tray_tooltip.hide()

    def _on_tray_activated(self, reason):
        # 隐藏自定义 tooltip
        self.tray_tooltip.hide()
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_overlay()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            # 左键单击 - 切换显示
            self._toggle_overlay()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # 右键菜单 - 手动弹出
            # 菜单显示期间暂停 hover 检测：tooltip 的显隐操作在 macOS 上会让菜单失焦、瞬间关闭
            self._hover_check_timer.stop()
            try:
                self._show_tray_menu()
            finally:
                self._hover_check_timer.start()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self._refresh_now()

    def _show_tray_menu(self):
        """手动弹出托盘右键菜单"""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background: #2A2A2A; color: #E0E0E0; border: 1px solid #555; padding: 4px; }
            QMenu::item { padding: 5px 24px; }
            QMenu::item:selected { background: #3A3A3A; }
            QMenu::separator { height: 1px; background: #555; margin: 4px 10px; }
        """)

        show_action = QAction("显示主窗口")
        show_action.triggered.connect(self._show_overlay)
        menu.addAction(show_action)

        hide_action = QAction("隐藏悬浮窗")
        hide_action.triggered.connect(self._hide_overlay)
        menu.addAction(hide_action)

        menu.addSeparator()

        refresh_action = QAction("立即刷新")
        refresh_action.triggered.connect(self._refresh_now)
        menu.addAction(refresh_action)

        hover_action = QAction("鼠标悬停显示行情")
        hover_action.setCheckable(True)
        hover_action.setChecked(self.config.get("hover_tooltip_enabled", True))
        hover_action.triggered.connect(self._on_toggle_hover)
        menu.addAction(hover_action)

        auto_action = QAction("开机自启")
        auto_action.setCheckable(True)
        if autostart_supported():
            auto_action.setChecked(autostart_is_enabled())
            auto_action.triggered.connect(self._on_toggle_autostart)
        else:
            auto_action.setEnabled(False)
            auto_action.setToolTip("源码模式下不可用，请使用打包后的应用")
        menu.addAction(auto_action)

        settings_action = QAction("设置...")
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("退出")
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        menu.exec(QCursor.pos())

    def _quit_app(self):
        """退出：停所有定时器、强制结束阻塞中的网络线程，避免进程残留"""
        self._hover_check_timer.stop()
        self.tray_tooltip.hide()
        try:
            # 保存悬浮窗当前位置
            self.overlay.config["position"] = {"x": self.overlay.x(), "y": self.overlay.y()}
            save_config(self.overlay.config)
            # 停悬浮窗刷新定时器
            self.overlay.timer.stop()
            # 强制结束可能正阻塞在 requests.get 的数据获取线程
            t = self.overlay.fetch_thread
            if t and t.isRunning():
                self.overlay.fetcher.stop()
                t.quit()
                t.wait(500)
                if t.isRunning():
                    t.terminate()  # 网络阻塞中 quit 无法唤醒，强制终止 OS 线程
        except Exception:
            pass
        self.tray.hide()
        # 兜底：事件循环退出后强制结束进程，确保无残留（避免重启时旧进程仍占资源）
        self.aboutToQuit.connect(lambda: os._exit(0))
        self.quit()


# ---------- 入口 ----------
def main():
    app = TrayApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
