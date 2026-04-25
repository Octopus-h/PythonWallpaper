#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
import sys
import os
import subprocess
import threading
import time
from typing import Optional, Callable
from functools import wraps

import pythoncom
import pystray
import win32ui
from PIL import Image

from FileEdit import *
from WallpaperGUIdpg import WallpaperGUI
from WallpaperFrame import WallpaperFrame
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
        default_wallpaper_path = os.path.abspath(os.path.join(get_app_root_path(), "resources", "mp4", "Warma.mp4"))

        def default_wallpaper():
            if os.path.isfile(default_wallpaper_path):
                wallpaper_logger.info(f"使用默认视频：{default_wallpaper_path}")
                return 'video', default_wallpaper_path
            else:
                wallpaper_logger.error(f"默认视频文件不存在：{default_wallpaper_path}")
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

        # 检查脚本类型标志
        is_non_wx = check_NOT_USE_WX(py_path)

        try:
            # if not is_non_wx:
                module_name = os.path.splitext(os.path.basename(py_path))[0]
                spec = importlib.util.spec_from_file_location(module_name, py_path)
                if spec is None:
                    wallpaper_logger.error(f"无法加载脚本: {py_path}")
                    return
                module = importlib.util.module_from_spec(spec)
                self._py_module = module
                # 执行模块代码
                spec.loader.exec_module(module)  # type: ignore

                if hasattr(module, 'update') and callable(module.update) \
                and hasattr(module, 'init') and callable(module.init) \
                and hasattr(module, 'draw') and callable(module.draw):
                    # 创建窗口
                    self.frame = WallpaperFrame(module.update, module.init, module.draw)
                    # 获取句柄
                    self.Hwnd = self.frame.GetHandle()
                else:
                    wallpaper_logger.error(f"获取update(), init()失败：{module}")

            # else:
            #     wallpaper_logger.info("脚本使用非 wx 库")

            #     # 更加自定义的导入
            #     self._script_process = Process(
            #         target=run_script_in_process,
            #         args=(py_path, self.queue),
            #         daemon=True
            #     )
            #     self._script_process.start()

            #     # 等待获取窗口句柄（最多5秒）
            #     try:
            #         _hwnd = self.queue.get(timeout=5)
            #     except Exception as e:
            #         wallpaper_logger.exception(f"获取窗口句柄出错")
            #         _hwnd = -1

            #     if _hwnd >0:
            #         self.Hwnd = _hwnd
            #     else:
            #         wallpaper_logger.error(f"hwnd无效：{_hwnd}")

        except Exception as e:
            wallpaper_logger.exception(f"运行Python脚本出错: {e}")

        return self.Hwnd

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
class SystemTrayManager:
    def __init__(self, wallproc: WallpaperProc, app: WallpaperGUI):
        self.wallproc = wallproc
        self.app = app
        self.autostart_enabled = is_autostart_enabled()
        wallpaper_logger.info(f"初始化托盘管理器，开机自启初始状态: {self.autostart_enabled}")

        # 图标路径
        self.icon_path = os.path.join(get_app_root_path(), "resources", "icons", "icon.png")
        self.icon_path = os.path.abspath(self.icon_path)
        if not os.path.exists(self.icon_path):
            wallpaper_logger.warning("图标文件不存在，使用系统默认图标")
            self.icon_path = None

        # 声明式菜单定义
        self.menu_def = ['menu',
            [
                self._autostart_menu_text(),
                '---',
                '切换壁纸',
                [
                    '切换壁纸(.exe文件)',
                    '---',
                    '切换壁纸(视频文件)',
                    '---',
                    '切换壁纸(.py文件)',
                ],
                '---',
                '杂项',
                [
                    '关于',
                    '---',
                    '设置'
                ],
                '---',
                '退出程序'
            ]
        ]

        self.icon = None
        self.menu = None

        self.commands = []
        self.flag = False

        self._create_menu()
        self._tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        self._tray_thread.start()

    def _build_menu_from_def(self, items_def: list):
        """递归解析菜单定义，支持标题后紧跟列表的模式"""
        result = []
        i = 0
        while i < len(items_def):
            item = items_def[i]
            if isinstance(item, str):
                if item == '---':
                    result.append(pystray.Menu.SEPARATOR)
                    i += 1
                else:
                    # 检查下一个元素是否是列表（子菜单）
                    if i + 1 < len(items_def) and isinstance(items_def[i+1], list):
                        # 当前 item 是子菜单标题，下一项是子菜单内容
                        sub_items = self._build_menu_from_def(items_def[i+1])
                        submenu = pystray.Menu(*sub_items)
                        result.append(pystray.MenuItem(item, submenu))
                        i += 2  # 跳过标题和子菜单列表
                    else:
                        # 普通菜单项
                        if item.startswith('开机自启'):
                            handler = self.toggle_autostart
                        else:
                            handler = self._get_func
                        result.append(pystray.MenuItem(item, handler))
                        i += 1
            elif isinstance(item, list):
                # 如果遇到列表，但没有前置标题，则直接递归处理（这种情况可能不会发生）
                sub_items = self._build_menu_from_def(item)
                # 这里假设列表本身代表一个子菜单，但没有标题，则忽略（或者可以用空标题？）
                result.extend(sub_items)
                i += 1
            else:
                i += 1
        return result

    def _create_menu(self):
        items = self._build_menu_from_def(self.menu_def[1])
        self.menu = pystray.Menu(*items)
        if self.icon is not None:
            self.icon.menu = self.menu

    def _run_tray(self):
        if self.icon_path:
            icon_img = Image.open(self.icon_path)
        else:
            icon_img = None
        self.icon = pystray.Icon("动态壁纸", icon_img, "动态壁纸", self.menu)
        self.icon.run()

    def _get_func(self, icon, char:str):
        wallpaper_logger.info(f"_get_func调用：{str(char)}，icon：{icon}")
        on_event.get_event(str(char))(self)

    def _show_file_dialog(self, title: str, default_path: str, file_types: list):
        pythoncom.CoInitialize()
        try:
            # 构造过滤器字符串
            filter_str = ""
            for desc, ext in file_types:
                filter_str += f"{desc}|{ext}|"
            filter_str += "||"   # 最后以两个竖线结尾

            dlg = win32ui.CreateFileDialog(
                1,                      # 1=打开文件, 0=保存文件
                None,                   # 默认扩展名（可省略或None）
                None,                   # 初始文件名（可省略或None）
                0,                      # 标志(Flags), 常用0就够 # type: ignore
                                        # 详细 Flags 见 MSDN OPENFILENAME
                filter_str              # 文件类型过滤器
                )

            dlg.SetOFNTitle(title)
            dlg.SetOFNInitialDir(default_path)
            if dlg.DoModal() == win32con.IDOK: # type: ignore
                return dlg.GetPathName()
            return None
        finally:
            pythoncom.CoUninitialize()

    def _autostart_menu_text(self):
        return "开机自启 ✓" if self.autostart_enabled else "开机自启"

    def _update_menu(self):
        self.menu_def[1][0] = self._autostart_menu_text()
        self._create_menu()
        wallpaper_logger.debug(f"托盘菜单已更新，开机自启文本: {self.menu_def[1][0]}")

    def toggle_autostart(self):
            new_state = not self.autostart_enabled
            try:
                set_autostart(new_state)
                self.autostart_enabled = new_state
                self._update_menu()
                wallpaper_logger.info(f"开机自启已{'启用' if new_state else '禁用'}")
            except Exception as e:
                wallpaper_logger.exception("设置开机自启失败")

    # ---------- 事件处理方法（使用装饰器注册）----------
    @on_event('切换壁纸(视频文件)')
    def select_video(self):
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

    @on_event('切换壁纸(.exe文件)')
    def select_exe(self):
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

    @on_event('切换壁纸(.py文件)')
    def select_py(self):
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

    @on_event('关于')
    def about(self):
        self.commands.append(self.app.show_about_popup)

    @on_event('设置')
    def settings(self):
        wallpaper_logger.info("设置未实现")

    @on_event('退出程序')
    def exit(self):
        wallpaper_logger.info("用户触发退出程序")
        self.wallproc.stop()
        if self.icon:
            self.icon.stop()

        self.app.stop()
        self.flag = True

    def run(self):
        while not self.flag:
            if len(self.commands) > 0:
                cmd_func = self.commands.pop(0)
                cmd_func()    # 每个命令独立拉起事件循环等操作
            time.sleep(0.05)


def main():
    wallproc = None  # 提前声明，便于 finally 中访问
    try:
        # 初始化壁纸管理器
        wallproc = WallpaperProc()

        # 加载配置文件中的壁纸路径
        wallpaper_path, wallpaper_type = load_wallpaper_path()

        # 创建并运行系统托盘
        app = WallpaperGUI()
        tray_manager = SystemTrayManager(wallproc, app)

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