import sys
import os
import json
import subprocess
import logging
from typing import Optional

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QFileDialog
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QCoreApplication

if sys.platform.startswith("win"):
    import win32con
    import win32gui
    import win32api
    import ctypes

# ===================== 优先定义路径函数（日志配置需要） =====================
def get_app_root_path():
    """获取程序根目录（兼容打包后和开发环境）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后的运行环境
        app_root = os.path.dirname(sys.executable)
    else:
        # 开发环境（脚本运行）
        app_root = os.path.dirname(os.path.abspath(__file__))
    return app_root

# ===================== 修改：日志配置（输出到last.log文件） =====================
# 日志文件路径：程序根目录/last.log
log_file_path = os.path.join(get_app_root_path(), "last.log")
# 配置日志：输出到文件，追加模式，UTF-8编码，不存在则自动创建
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(  # 替换控制台输出为文件输出
            filename=log_file_path,
            mode='a',          # 追加模式（不会覆盖原有日志）
            encoding='utf-8'   # 确保中文正常显示
        )
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"程序启动，日志文件路径：{log_file_path}")  # 启动时记录日志路径

# ===================== JSON配置相关 =====================
def get_config_path():
    """获取配置文件路径（保存在程序下的resources文件夹）"""
    app_root = get_app_root_path()
    config_dir = os.path.join(app_root, "resources")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.json")
    logger.info(f"配置文件路径：{config_path}")
    return config_path

def init_config_file():
    """初始化配置文件（文件不存在时创建空配置）"""
    try:
        config_path = get_config_path()
        if not os.path.exists(config_path):
            default_config = {
                "last_wallpaper_path": "",
                "update_time": ""
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            logger.info(f"配置文件不存在，已自动创建：{config_path}")
        return True
    except PermissionError:
        logger.error("创建配置文件失败：没有写入权限！请以管理员身份运行程序")
        return False
    except Exception as e:
        logger.error(f"创建配置文件失败：{e}")
        return False

def save_wallpaper_path(video_path: str):
    """保存壁纸路径到JSON配置文件"""
    if not init_config_file():
        return
    try:
        config_path = get_config_path()
        config_data = {
            "last_wallpaper_path": os.path.abspath(video_path),
            "update_time": str(os.path.getmtime(video_path))
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        logger.info(f"壁纸路径已保存到程序目录：{config_path}")
    except PermissionError:
        logger.error("保存配置文件失败：没有写入权限！请以管理员身份运行程序")
    except Exception as e:
        logger.error(f"保存配置文件失败：{e}")

def load_wallpaper_path() -> Optional[str]:
    """从JSON配置文件读取壁纸路径（不存在则先创建）"""
    init_config_file()
    try:
        config_path = get_config_path()
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        video_path = config_data.get("last_wallpaper_path", "")
        if not video_path or not os.path.isfile(video_path):
            if video_path:
                logger.warning(f"配置文件中的路径无效：{video_path}")
            else:
                logger.info("配置文件中无有效壁纸路径，将使用默认视频")
            return None
        logger.info(f"从程序目录配置文件加载壁纸路径：{video_path}")
        return video_path
    except json.JSONDecodeError:
        logger.error("配置文件格式错误，将重新创建空配置文件")
        init_config_file()
        return None
    except Exception as e:
        logger.error(f"读取配置文件失败：{e}")
        return None

def get_workerw():
    """获取WorkerW窗口句柄（Windows桌面底层窗口）"""
    progman = win32gui.FindWindow("Progman", None)
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000)
    workerw = []
    def enum_win(hwnd, res):
        shellview = win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None)
        if shellview != 0:
            worker = win32gui.FindWindowEx(0, hwnd, "WorkerW", None)
            if worker != 0:
                workerw.append(worker)
        return True
    win32gui.EnumWindows(enum_win, None)
    return workerw[0] if workerw else None

def set_ffplay_to_workerw(ffplay_title):
    """将ffplay窗口嵌入到WorkerW（作为桌面壁纸）"""
    hwnd = win32gui.FindWindow(None, ffplay_title)
    if hwnd == 0:
        logger.warning(f"FFplay窗口未找到: {ffplay_title}")
        return False
    workerw = get_workerw()
    if not workerw:
        logger.error("WorkerW未找到")
        return False
    win32gui.SetParent(hwnd, workerw)
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style | win32con.WS_CHILD)
    screen_w, screen_h = FFPlayWallpaperProc.get_screen_size()
    win32gui.SetWindowPos(hwnd, 0, 0, 0, screen_w, screen_h, win32con.SWP_NOZORDER)
    return True

class FFPlayWallpaperProc:
    """ffplay壁纸进程管理类"""
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.title = None
        self.video_path = None

    def start(self, video_path: str):
        """启动ffplay播放视频作为壁纸（优化分辨率和全屏参数）"""
        self.stop()
        ffplay_path = os.path.join(get_app_root_path(), "resources", "ffmpeg", "ffplay.exe")
        ffplay_path = os.path.abspath(ffplay_path)
        screen_w, screen_h = self.get_screen_size()
        self.title = f"FFPLAY_WALLPAPER_{os.path.basename(video_path)}"
        cmd = [
            ffplay_path, 
            "-x", str(screen_w),
            "-y", str(screen_h),
            "-loop", "0",
            "-noborder",
            "-fs",
            "-window_title", self.title,
            "-an",
            "-loglevel", "quiet",
            "-i", video_path
        ]
        logger.info(f"启动ffplay壁纸（分辨率：{screen_w}x{screen_h}）：" + " ".join(cmd))
        self.process = subprocess.Popen(
            cmd,
            creationflags = subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,    # 重定向标准输出
            stderr=subprocess.DEVNULL     # 重定向标准错误
        )
        self.video_path = video_path

    def embed_to_workerw(self):
        """将ffplay窗口嵌入到桌面底层"""
        if sys.platform.startswith("win"):
            import time
            for _ in range(16):
                result = set_ffplay_to_workerw(self.title)
                if result:
                    logger.info("ffplay窗口已嵌入桌面WorkerW并设置为全屏")
                    return True
                time.sleep(0.1)
            logger.error("嵌入WorkerW并设置全屏失败")
        return False

    def stop(self):
        """停止ffplay进程"""
        if self.process and self.process.poll() is None:
            logger.info("关闭ffplay进程")
            self.process.terminate()
        self.process = None

    @staticmethod
    def get_screen_size():
        """获取桌面真实物理分辨率（适配Windows DPI缩放）"""
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                user32 = ctypes.windll.user32
                screen_w = user32.GetSystemMetrics(0)
                screen_h = user32.GetSystemMetrics(1)
                logger.info(f"获取到真实物理分辨率：{screen_w}x{screen_h}")
                return screen_w, screen_h
            except Exception as e:
                logger.warning(f"获取物理分辨率失败，使用Qt备用方案：{e}")
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        screen = app.primaryScreen().geometry()
        logger.info(f"Qt获取分辨率：{screen.width()}x{screen.height()}")
        return screen.width(), screen.height()

class SystemTrayManager:
    """系统托盘管理类"""
    def __init__(self, app: QApplication, wallproc: FFPlayWallpaperProc):
        self.app = app
        self.wallproc = wallproc
        icon_path = os.path.join(get_app_root_path(), "resources", "icons", "icon.png")
        icon_path = os.path.abspath(icon_path)
        if os.path.exists(icon_path):
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self.app)
        else:
            self.tray_icon = QSystemTrayIcon(self.app.style().standardIcon(QApplication.style().SP_ComputerIcon), self.app)
        self.tray_icon.setToolTip("FFplay 动态壁纸")
        self.menu = QMenu()
        self._setup_menu()
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()

    def _setup_menu(self):
        """初始化托盘菜单"""
        set_wall_action = QAction("切换壁纸", self.menu)
        set_wall_action.triggered.connect(self.select_video)
        self.menu.addAction(set_wall_action)
        quit_action = QAction("退出程序", self.menu)
        quit_action.triggered.connect(self.exit)
        self.menu.addAction(quit_action)

    def select_video(self):
        """选择视频文件作为新壁纸（新增：保存路径到JSON）"""
        default_video_dir = os.path.join(get_app_root_path(), "resources", "mp4")
        file_path, _ = QFileDialog.getOpenFileName(
            None, "选择动态壁纸视频",
            os.path.expanduser("~") if not os.path.exists(default_video_dir) else default_video_dir,
            "视频文件 (*.mp4 *.avi *.mov *.mkv);;所有文件 (*.*)"
        )
        if file_path and os.path.isfile(file_path):
            self.wallproc.start(file_path)
            self.wallproc.embed_to_workerw()
            save_wallpaper_path(file_path)
        else:
            logger.info("已取消切换壁纸")

    def exit(self):
        """退出程序"""
        logger.info("用户触发退出程序")
        self.wallproc.stop()
        self.tray_icon.hide()
        self.app.quit()

def main():
    """主函数（修改：优先加载配置文件中的路径，再用默认）"""
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("FFplay动态壁纸")
    wallproc = FFPlayWallpaperProc()

    # 加载配置文件中的壁纸路径
    video_path = load_wallpaper_path()
    default_video_path = os.path.join(get_app_root_path(), "resources", "mp4", "Warma.mp4")
    default_video_path = os.path.abspath(default_video_path)
    if not video_path:
        if os.path.isfile(default_video_path):
            video_path = default_video_path
            logger.info(f"使用默认视频：{video_path}")
        else:
            logger.error(f"默认视频文件不存在：{default_video_path}")
            sys.exit(1)

    # 启动壁纸
    wallproc.start(video_path)
    wallproc.embed_to_workerw()

    # 创建托盘管理器
    tray_manager = SystemTrayManager(app, wallproc)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()