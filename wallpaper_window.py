#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
from multiprocessing import Process, Queue
import sys
import os
import subprocess
from typing import Optional, Callable
from functools import wraps

import FreeSimpleGUIWx as sg

from FileEdit import *
from WallpaperFrame import WallpaperFrame
from WorkerW import *

# ========== 装饰器与类型映射==========
type_to_method = {}

def bind_wallpaper_type(target_type: str):
    """装饰器：给业务方法绑定目标类型"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, path: str):
            if not path or not os.path.isfile(path):
                logger.error(f"无效路径：{path}")
                return False
            return func(self, path)
        type_to_method[target_type] = wrapper
        return wrapper
    return decorator

event_handlers = {}

def on_event(event_name: str):
    """
    装饰器工厂：将方法注册到事件映射表
    :param event_name: 菜单项文本（即 tray.Read() 返回的事件字符串）
    """
    def decorator(func):
        event_handlers[event_name] = func.__name__
        return func
    return decorator

# ========== WallpaperProc 类==========
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
        self.queue = Queue()

    def start(self, type_: Optional[str], path: Optional[str]) -> bool:
        """统一启动入口"""
        default_wallpaper_path = os.path.abspath(os.path.join(get_app_root_path(), "resources", "mp4", "Warma.mp4"))

        def default_wallpaper():
            if os.path.isfile(default_wallpaper_path):
                logger.info(f"使用默认视频：{default_wallpaper_path}")
                return 'video', default_wallpaper_path
            else:
                logger.error(f"默认视频文件不存在：{default_wallpaper_path}")
                sys.exit(1)

        if not path:
            logger.error(f"文件不存在：{path}，使用默认壁纸")
            type_, path = default_wallpaper()

        if type_ not in type_to_method:
            logger.error(f"无对应类型的启动方法：{type_}，使用默认壁纸")
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
                            logger.info(f"从 {json_path} 读取到窗口标题: {_title}")
                        else:
                            logger.warning(f"JSON 文件中未找到 'title' 字段: {json_path}")
                            type_, path = default_wallpaper()
                except Exception as e:
                    logger.error(f"读取 JSON 文件失败 \n\t ({json_path}) \n\t {e}")
                    type_, path = default_wallpaper()
            else:
                logger.error(f".json文件不存在：{json_path}")
                type_, path = default_wallpaper()

        target_method = type_to_method[type_]
        return target_method(self, path)

    @bind_wallpaper_type("video")
    def start_by_video(self, video_path: str):
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
        logger.info(f"启动video壁纸（分辨率：{self.screen_w}x{self.screen_h}）：" + " ".join(cmd))
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
        self.stop()
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
                    logger.error(f"无法加载脚本: {py_path}")
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
                    logger.error(f"获取update(), init()失败：{module}")

            # else:
            #     logger.info("脚本使用非 wx 库")

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
            #         logger.exception(f"获取窗口句柄出错")
            #         _hwnd = -1

            #     if _hwnd >0:
            #         self.Hwnd = _hwnd
            #     else:
            #         logger.error(f"hwnd无效：{_hwnd}")

        except Exception as e:
            logger.exception(f"运行Python脚本出错: {e}")

        return self.Hwnd

    def embed_to_workerw(self, target):
        """将窗口嵌入到桌面底层"""
        if not sys.platform.startswith("win"):
            return False

        import time
        for attempt in range(16):
            result = set_windows_to_workerw(target)
            if result >0:
                logger.info("窗口已通过标题嵌入桌面 WorkerW")
                self.Hwnd = result
                return True
            else:
                logger.warning(f"第 {attempt+1} 次找到窗口但嵌入失败，稍后重试...")
            time.sleep(0.1)

        logger.error("通过标题查找并嵌入失败")
        return False

    def stop(self):
        """停止进程"""
        if self.process and self.process.poll() is None:
            logger.info(f"关闭进程{self.process}")
            self.process.terminate()

        if self._script_process:
            self._script_process.terminate()

        if self.frame:
            self.frame.Close()
            logger.info(f"已通过frame.Close()终止进程")
        else:
            try:
                _, pid = win32process.GetWindowThreadProcessId(self.Hwnd)
                if pid:
                    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                    win32api.TerminateProcess(handle, 0)
                    win32api.CloseHandle(handle)
                    logger.info(f"已终止进程 (PID: {pid})，窗口句柄: 0x{self.Hwnd:08X}")
                    return True
            except Exception as e:
                logger.warning(f"通过窗口句柄终止进程失败: \n\t {e} \n\t 进程可能未结束")

        self.reset()

# ========== 使用 FreeSimpleGUIWx 重写的系统托盘管理类==========
class SystemTrayManager:
    """系统托盘管理类（使用装饰器注册事件）"""

    def __init__(self, wallproc: WallpaperProc):
        self.wallproc = wallproc
        self.autostart_enabled = is_autostart_enabled()
        logger.info(f"初始化托盘管理器，开机自启初始状态: {self.autostart_enabled}")

        # 图标路径
        icon_path = os.path.join(get_app_root_path(), "resources", "icons", "icon.png")
        icon_path = os.path.abspath(icon_path)

        # 定义托盘菜单（FreeSimpleGUIWx 格式）
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
                                '关于',
                                '---',
                                '退出程序'
                            ]
                        ]

        # 创建系统托盘图标
        self.tray = sg.SystemTray(
            menu=self.menu_def,
            filename=icon_path if os.path.exists(icon_path) else None,
            tooltip='动态壁纸'
        )

        if not os.path.exists(icon_path):
            logger.warning("图标文件不存在，使用系统默认图标")

        # 构建实例方法映射（将方法名转换为实际绑定的实例方法）
        self._handlers = {}
        for event, method_name in event_handlers.items():
            if hasattr(self, method_name):
                self._handlers[event] = getattr(self, method_name)
            else:
                logger.error(f"事件 {event} 对应的方法 {method_name} 不存在")

    def _autostart_menu_text(self):
        return "开机自启 ✓" if self.autostart_enabled else "开机自启"

    def _update_menu(self):
        self.menu_def[1][0] = self._autostart_menu_text()
        self.tray.update(menu=self.menu_def)
        logger.debug(f"托盘菜单已更新，开机自启文本: {self.menu_def[1][0]}")

    def run(self):
        """进入托盘事件循环（阻塞直到退出）"""
        try:
            while True:
                event = self.tray.Read()   # 等待菜单点击

                # 托盘可能被系统销毁，此时 event 为 None
                if event is None:
                    logger.info("托盘图标已关闭，退出程序")
                    break

                if event.startswith('开机自启'):   # 用 startswith 匹配动态文本
                    self.toggle_autostart()
                else:
                    # 查找事件对应的处理方法
                    handler = self._handlers.get(event)
                    if handler:
                        handler()   # 执行事件处理
                        if event == '退出程序':
                            break   # 退出事件循环
                    else:
                        logger.debug(f"忽略未知事件: {event}")

        except Exception as e:
            logger.exception("托盘事件循环发生异常")
        finally:
            # 确保资源释放（exit 方法内部已调用 wallproc.stop 和 tray.close）
            self.exit()

    def toggle_autostart(self):
            new_state = not self.autostart_enabled
            try:
                set_autostart(new_state)
                self.autostart_enabled = new_state
                self._update_menu()
                logger.info(f"开机自启已{'启用' if new_state else '禁用'}")
            except Exception as e:
                logger.exception("设置开机自启失败")

    # ---------- 事件处理方法（使用装饰器注册）----------
    @on_event('切换壁纸(视频文件)')
    def select_video(self):
        """弹出文件选择对话框，切换壁纸"""
        default_video_dir = os.path.join(get_app_root_path(), "resources", "mp4")
        if not os.path.exists(default_video_dir):
            default_video_dir = os.path.expanduser("~")

        file_path = sg.popup_get_file(
            "选择动态壁纸视频",
            title="选择视频文件",
            default_path=default_video_dir,
            file_types=(
                ("视频文件", "*.mp4;*.avi;*.mov;*.mkv"),
            )
        )

        if file_path and os.path.isfile(file_path):
            self.wallproc.embed_to_workerw(self.wallproc.start_by_video(file_path))
            save_wallpaper_path(file_path, "video")
            logger.info(f"壁纸已切换：{file_path}")
        else:
            logger.info("已取消切换壁纸")

    @on_event('切换壁纸(.exe文件)')
    def select_exe(self):
        """弹出文件选择对话框，切换壁纸"""
        default_video_dir = os.path.join(get_app_root_path(), "resources")
        if not os.path.exists(default_video_dir):
            default_video_dir = os.path.expanduser("~")

        file_path = sg.popup_get_file(
            "选择动态壁纸视频",
            title="选择视频文件",
            default_path=default_video_dir,
            file_types=(
                ("可执行文件", "*.exe"),
            )
        )

        if file_path and os.path.isfile(file_path):
            self.wallproc.embed_to_workerw(self.wallproc.start("exe", file_path))
            save_wallpaper_path(file_path, "exe")
            logger.info(f"壁纸已切换：{file_path}")
        else:
            logger.info("已取消切换壁纸")

    @on_event('切换壁纸(.py文件)') # 开发中
    def select_py(self):
        """弹出文件选择对话框，选择并运行一个Python脚本，并将其窗口作为壁纸"""
        # 设置默认打开的目录，可以根据需要调整
        default_dir = os.path.join(get_app_root_path(), "resources", "example.py") 
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")

        file_path = sg.popup_get_file(
            "选择一个Python脚本",
            title="选择脚本文件",
            default_path=default_dir,
            file_types=(
                ("Python文件", "*.py"),
            )
        )

        if file_path and os.path.isfile(file_path):
            self.wallproc.embed_to_workerw(self.wallproc.start("py", file_path))
            save_wallpaper_path(file_path, "py")
            logger.info(f"壁纸已切换：{file_path}")
        else:
            logger.info("已取消切换壁纸")

    @on_event('关于')
    def about(self):
        """显示关于信息"""
        # 构建需要滚动的内容
        about_text = """
动态壁纸程序
版本 1.0
作者：Octopus-h
基于 FreeSimpleGUIWx 和 pywin32
使用 ffplay 播放视频壁纸

ffplay来自：
https://github.com/Octopus-h/ffplay-minimal-build

如果出现默认壁纸，可能是：exe没有配套json，你的壁纸路径改变，等等
如果有疑问，请找到程序目录下的last.log，或许可以帮到你

致谢：
感谢所有使用和支持本软件的朋友。
感谢ffmpeg：https://git.ffmpeg.org/ffmpeg.git
感谢cx_Freeze
    """.strip()

        layout = [
            [sg.Multiline(about_text, size=(60, 15), disabled=False, autoscroll=False)]
        ]
        
        window = sg.Window('关于', layout, finalize=True)

    @on_event('退出程序')
    def exit(self):
        """退出程序"""
        logger.info("用户触发退出程序")
        self.wallproc.stop()
        self.tray.close()

def main():
    # 设置 FreeSimpleGUIWx 主题
    sg.theme('DefaultNoMoreNagging')

    wallproc = None  # 提前声明，便于 finally 中访问
    try:
        # 初始化壁纸管理器
        wallproc = WallpaperProc()

        # 加载配置文件中的壁纸路径
        wallpaper_path, wallpaper_type = load_wallpaper_path()

        # 启动壁纸
        wallproc.embed_to_workerw(wallproc.start(wallpaper_type, wallpaper_path))

        # 创建并运行系统托盘
        tray_manager = SystemTrayManager(wallproc)
        tray_manager.run()  # 阻塞，直到退出

    except KeyboardInterrupt:
        logger.info("用户通过键盘中断退出")
    except Exception as e:
        logger.exception(f"程序运行中发生未捕获异常")
    finally:
        # 无论何种原因退出，都尝试停止壁纸进程
        if wallproc:
            wallproc.stop()
        win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER, None, win32con.SPIF_SENDCHANGE)
        logger.info("程序结束")

if __name__ == '__main__':
    main()