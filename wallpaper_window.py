#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import sys
import os
import subprocess
import threading
import time
import queue
from typing import Optional, Callable
from functools import wraps

import pythoncom
import win32ui
import ruwps

from FileEdit import *
from WallpaperGUIdpg import WallpaperGUI
from WorkerW import *

# ========== 装饰器与类型映射 ==========
class Wrapper_tool:
    """通用装饰器类"""
    def __init__(self, pre_func: Optional[Callable] = None):
        self.pre_func = pre_func          # 保存前置函数
        self.event_handlers = {}          # 可用于后续注册事件

    def __call__(self, event_name: Optional[str] = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):          # 添加 **kwargs 以支持关键字参数
                if self.pre_func:                  # 检查是否存在前置函数
                    self.pre_func(*args, **kwargs) # 调用保存的前置函数
                return func(*args, **kwargs)       # 调用原函数
            self.event_handlers[event_name] = func
            return wrapper
        return decorator
    
    def get_event(self, event_name: Optional[str]) -> Callable:
        """返回一个可用的函数"""
        if self.event_handlers[event_name] is None:
            wallpaper_logger.error(f"事件 {event_name} 未注册")
            raise AttributeError(f"事件 {event_name} 未注册，来自 Wrapper_tool")
        return self.event_handlers[event_name]

# ========== 装饰器定义 ==========

def bind_wallpaper_wrapper(self, path: str):
    if not path or not os.path.isfile(path):
        wallpaper_logger.error(f"无效路径：{path}")

bind_wallpaper_type = Wrapper_tool(bind_wallpaper_wrapper)

on_event = Wrapper_tool()
# ========== WallpaperProc 类 ==========
class WallpaperProc:
    """壁纸进程管理类"""
    def __init__(self):
        self.python_path = "resources/pyenv/pythonw.exe"
        self.ffplay_path = os.path.abspath(os.path.join(get_app_root_path(), "resources", "ffmpeg", "ffplay.exe"))
        self.screen_w, self.screen_h = get_screen_size()
        self.reset()

    def reset(self):
        self.process: Optional[subprocess.Popen] = None
        self.title = None
        self.path = None
        self.Hwnd = -1
        self._py_module = None
        self.frame = None
        self._script_process = None
        self.queue = None

    def start(self, type_: Optional[str], path: Optional[str]) -> bool:
        """统一启动入口"""
        default_wallpaper_path = os.path.abspath(os.path.join(get_app_root_path(), "resources", "example.py"))

        def default_wallpaper():
            if os.path.isfile(default_wallpaper_path):
                wallpaper_logger.info(f"使用默认py壁纸：{default_wallpaper_path}")
                return 'py', default_wallpaper_path
            else:
                wallpaper_logger.error(f"默认py壁纸不存在：{default_wallpaper_path}")
                sys.exit(1)

        if not path:
            wallpaper_logger.error(f"文件不存在：{path}，使用默认壁纸")
            type_, path = default_wallpaper()

        if type_ not in bind_wallpaper_type.event_handlers:
            wallpaper_logger.error(f"无对应类型的启动方法：{type_}，使用默认壁纸")
            type_, path = default_wallpaper()

        json_path = os.path.splitext(path)[0] + ".json"   # 替换扩展名为 .json
        if type_ == 'exe':
            if os.path.isfile(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        _title = data.get('title')            # 假设 JSON 中包含 "title" 字段
                        if _title:
                            self.title = _title
                            wallpaper_logger.info(f"从 {json_path} 读取到窗口标题: {_title}")
                        else:
                            wallpaper_logger.warning(f"JSON 文件中未找到 'title' 字段: {json_path}")
                            type_, path = default_wallpaper()
                except Exception as e:
                    wallpaper_logger.error(f"读取 JSON 文件失败 \n\t ({json_path}) \n\t {e}")
                    type_, path = default_wallpaper()
            else:
                wallpaper_logger.error(f".json文件不存在：{json_path}")
                type_, path = default_wallpaper()

        target_method = bind_wallpaper_type.get_event(type_)
        return target_method(self, path)

    @bind_wallpaper_type("video")
    def start_by_video(self, video_path: str) -> str:
        """启动ffplay播放视频作为壁纸"""
        self.stop()
        self.title = f"FFPLAY_WALLPAPER_{os.path.basename(video_path)}"
        cmd = [
            self.ffplay_path,
            "-x", str(self.screen_w),
            "-y", str(self.screen_h),
            "-loop", "0",
            "-noborder",
            "-fs",
            "-window_title", self.title,
            "-an",
            "-loglevel", "quiet",
            "-i", video_path
        ]
        wallpaper_logger.info(f"启动video壁纸（分辨率：{self.screen_w}x{self.screen_h}）：" + " ".join(cmd))
        self.process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.path = video_path

        return self.title

    @bind_wallpaper_type("exe")
    def start_by_EXE(self, EXE_path: str):
        """将可执行程序作为壁纸，尝试从同目录下的同名.json文件读取窗口标题"""
        # 保存从JSON读取的标题
        saved_title = self.title
        self.stop()
        self.title = saved_title
        # 启动进程
        self.process = subprocess.Popen(
            EXE_path,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.path = EXE_path

        return self.title

    @bind_wallpaper_type('py')
    def start_by_PY(self, py_path: str):
        """将.py脚本作为壁纸"""
        self.stop()
        # 启动进程
        self.process = subprocess.Popen(
            [self.python_path if os.path.isfile(self.python_path) else sys.executable, py_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # 行缓冲
        )
        self.path = py_path
        wallpaper_logger.info(f"启动子进程 PID: {self.process.pid}")

        # 读取子进程的第一行输出（应为HWND）
        output_queue = queue.Queue()

        def reader_thread():
            try:
                line = self.process.stdout.readline() # type: ignore
                if line:
                    output_queue.put(line.strip())
            except Exception as e:
                wallpaper_logger.warning(f"读取子进程输出异常: {e}")

        thread = threading.Thread(target=reader_thread, daemon=True)
        thread.start()

        hwnd = None
        try:
            line = output_queue.get(timeout=2)  # 最多等待2秒
            if line.startswith('0x'):
                hwnd = int(line, 16)
            else:
                hwnd = int(line)
            wallpaper_logger.info(f"从子进程stdout获取到HWND: 0x{hwnd:08X}")
        except queue.Empty:
            wallpaper_logger.error("等待子进程输出超时")
            # 读取stderr以便调试
            stderr = self.process.stderr.read() # type: ignore
            if stderr:
                wallpaper_logger.error(f"子进程错误输出: {stderr}")
            self.stop()
            return -1
        except ValueError:
            wallpaper_logger.error(f"无法解析子进程输出的HWND: {line}")
            self.stop()
            return -1
        except Exception as e:
            wallpaper_logger.exception(f"读取子进程输出失败: {e}")
            self.stop()
            return -1

        self.Hwnd = hwnd
        return hwnd

    def embed_to_workerw(self, target):
        """将窗口嵌入到桌面底层"""
        if not sys.platform.startswith("win"):
            return False

        for attempt in range(16):
            result = set_windows_to_workerw(target)
            if result >0:
                wallpaper_logger.info("窗口已通过标题嵌入桌面 WorkerW")
                self.Hwnd = result
                return True
            else:
                wallpaper_logger.warning(f"第 {attempt+1} 次找到窗口但嵌入失败，稍后重试...")
            time.sleep(0.1)

        wallpaper_logger.error("通过标题查找并嵌入失败")
        return False

    def stop(self):
        """停止进程"""
        if self.process and self.process.poll() is None:
            wallpaper_logger.info(f"关闭进程{self.process}")
            self.process.terminate()

        if self._script_process:
            self._script_process.terminate()

        if self.frame:
            self.frame.Close()
            wallpaper_logger.info(f"已通过frame.Close()终止进程")
        else:
            try:
                _, pid = win32process.GetWindowThreadProcessId(self.Hwnd)
                if pid:
                    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                    win32api.TerminateProcess(handle, 0)
                    win32api.CloseHandle(handle)
                    wallpaper_logger.info(f"已终止进程 (PID: {pid})，窗口句柄: 0x{self.Hwnd:08X}")
                    return True
            except Exception as e:
                wallpaper_logger.warning(f"通过窗口句柄终止进程失败: \n\t {e} \n\t 进程可能未结束")

        self.reset()

# ========== 系统托盘管理类 ==========
class WallpaperTrayApp(ruwps.App):
    def __init__(self, wallproc: WallpaperProc, gui_app: WallpaperGUI):
        # 设置托盘图标和标题
        icon_path = os.path.join(get_app_root_path(), "resources", "icons", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = None   # 或用默认

        super().__init__("动态壁纸", icon=icon_path, quit_button=None) # type: ignore
        self.wallproc = wallproc
        self.gui_app = gui_app
        self.autostart_enabled = is_autostart_enabled()

    def _autostart_text(self):
        return "开机自启 ✓" if self.autostart_enabled else "开机自启"

    def update_menu(self):
        """根据状态重建菜单（ruwps支持！）"""
        # 动态菜单结构
        self.menu = [
            ruwps.MenuItem(self._autostart_text(), callback=self.toggle_autostart),
            ruwps.MenuItem("切换壁纸(.exe文件)", self.select_exe),
            ruwps.MenuItem("切换壁纸(视频文件)", self.select_video),
            ruwps.MenuItem("切换壁纸(.py文件)", self.select_py),
            ruwps.MenuItem("关于", self.about),
            ruwps.MenuItem("设置", self.settings),
            ruwps.MenuItem("退出程序", self.exit)
        ]

    def run(self):
        self.update_menu()  # 初始化菜单
        super().run()

    @ruwps.clicked("切换壁纸(视频文件)")
    def select_video(self, sender):
        default_dir = os.path.join(get_app_root_path(), "resources", "mp4")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")
        file_path = self._show_file_dialog(
            title="选择视频文件",
            default_path=default_dir,
            file_types=[("视频文件", "*.mp4;*.avi;*.mov;*.mkv")]
        )
        if file_path:
            self.wallproc.embed_to_workerw(self.wallproc.start_by_video(file_path))
            save_wallpaper_path(file_path, "video")
            wallpaper_logger.info(f"壁纸已切换：{file_path}")

    @ruwps.clicked("切换壁纸(.exe文件)")
    def select_exe(self, sender):
        default_dir = os.path.join(get_app_root_path(), "resources")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")
        file_path = self._show_file_dialog(
            title="选择可执行文件",
            default_path=default_dir,
            file_types=[("可执行文件", "*.exe")]
        )
        if file_path:
            self.wallproc.embed_to_workerw(self.wallproc.start("exe", file_path))
            save_wallpaper_path(file_path, "exe")
            wallpaper_logger.info(f"壁纸已切换：{file_path}")

    @ruwps.clicked("切换壁纸(.py文件)")
    def select_py(self, sender):
        default_dir = os.path.join(get_app_root_path(), "resources")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")
        file_path = self._show_file_dialog(
            title="选择Python脚本",
            default_path=default_dir,
            file_types=[("Python文件", "*.py")]
        )
        if file_path:
            self.wallproc.embed_to_workerw(self.wallproc.start("py", file_path))
            save_wallpaper_path(file_path, "py")
            wallpaper_logger.info(f"壁纸已切换：{file_path}")

    @ruwps.clicked("关于")
    def about(self, sender):
        self.gui_app.show_about_popup()

    @ruwps.clicked("设置")
    def settings(self, sender):
        wallpaper_logger.info("设置未实现")

    @ruwps.clicked("退出程序")
    def exit(self, sender):
        wallpaper_logger.info("用户触发退出程序")
        self.wallproc.stop()
        self.gui_app.stop()
        self.quit()   # ruwps 提供的退出方法

    def toggle_autostart(self, sender):
        new_state = not self.autostart_enabled
        try:
            set_autostart(new_state)
            self.autostart_enabled = new_state
            # 同步菜单项文本和状态
            self.update_menu()
            wallpaper_logger.info(f"开机自启已{'启用' if new_state else '禁用'}")
        except Exception as e:
            wallpaper_logger.exception("设置开机自启失败")

    def _show_file_dialog(self, title: str, default_path: str, file_types: list):
        pythoncom.CoInitialize()
        try:
            filter_str = ""
            for desc, ext in file_types:
                filter_str += f"{desc}|{ext}|"
            filter_str += "||"
            dlg = win32ui.CreateFileDialog(
                1,                      # 1=打开文件, 0=保存文件
                None,                   # 默认扩展名
                None,                   # 初始文件名
                0,                      # Flags # type: ignore
                filter_str
            )
            dlg.SetOFNTitle(title)
            dlg.SetOFNInitialDir(default_path)
            if dlg.DoModal() == win32con.IDOK: # type: ignore
                return dlg.GetPathName()
            return None
        finally:
            pythoncom.CoUninitialize()


def main():
    wallproc = None  # 提前声明，便于 finally 中访问
    try:
        app = WallpaperGUI()
        # 初始化壁纸管理器
        wallproc = WallpaperProc()

        # 加载配置文件中的壁纸路径
        wallpaper_path, wallpaper_type = load_wallpaper_path()

        # 创建并运行系统托盘
        tray_manager = WallpaperTrayApp(wallproc, app)

        # 启动壁纸
        wallproc.embed_to_workerw(wallproc.start(wallpaper_type, wallpaper_path))

        tray_manager.run()

    except KeyboardInterrupt:
        wallpaper_logger.info("用户通过键盘中断退出")
    except Exception as e:
        wallpaper_logger.exception(f"程序运行中发生未捕获异常")
    finally:
        # 无论何种原因退出，都尝试停止壁纸进程
        if wallproc:
            wallproc.stop()
        win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER, None, win32con.SPIF_SENDCHANGE)
        wallpaper_logger.info("程序结束")

if __name__ == '__main__':
    main()