import sys
from typing import Tuple, Union
from FileEdit import wallpaper_logger
import win32con
import win32gui
import win32api
import ctypes
import win32process


def get_screen_size() -> Tuple[int, int]:
    """
    获取桌面真实物理分辨率（仅 Windows，通过 ctypes 直接调用 API）
    返回 (width, height)
    """
    if not sys.platform.startswith("win"):
        # 非 Windows 系统可添加其他实现（如 tkinter），这里简单返回默认值
        wallpaper_logger.warning("非 Windows 系统，返回默认分辨率 1920x1080")
        return 1920, 1080

    try:
        # 设置进程 DPI 感知（推荐使用 2 = PROCESS_PER_MONITOR_DPI_AWARE）
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception as e:
        wallpaper_logger.debug(f"设置 DPI 感知失败（可能已设置或系统不支持）：\n\t {e}")

    try:
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        wallpaper_logger.info(f"获取到 Windows 真实物理分辨率：{screen_w}x{screen_h}")
        return screen_w, screen_h
    except Exception as e:
        wallpaper_logger.error(f"获取屏幕分辨率失败：\n\t {e}")
        # 回退方案：尝试使用 tkinter（可选，但会增加依赖）
        # 这里简单返回 1920x1080 避免崩溃
        return 1920, 1080

def find_window_by_pid(pid: int):
    """
    根据进程ID查找该进程的第一个顶层窗口
    :param pid: 进程ID
    :return: 窗口句柄（hwnd），如果未找到返回None
    """
    def enum_windows_callback(hwnd, hwnd_list):
        # 获取窗口所属进程ID
        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
        if found_pid == pid:
            hwnd_list.append(hwnd)
        return True

    hwnd_list = []
    win32gui.EnumWindows(enum_windows_callback, hwnd_list)
    return hwnd_list[0] if hwnd_list else None

def find_hwnd_by_title(title, partial_match=True):
    """
    根据窗口标题查找窗口句柄
    :param title: 窗口标题
    :param partial_match: 是否模糊匹配（标题包含即可）
    :return: 窗口句柄列表（可能多个），或第一个匹配的句柄（若只取一个）
    """
    hwnds = []
    def enum_callback(hwnd, param):
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            if partial_match:
                if title.lower() in window_title.lower():
                    hwnds.append(hwnd)
            else:
                if title == window_title:
                    hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(enum_callback, None)
    return hwnds

def kill_process_by_hwnd(hwnd):
    """
    通过窗口句柄终止所属进程
    :param hwnd: 窗口句柄
    :return: 成功返回 True，否则 False
    """
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid:
            handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
            win32api.TerminateProcess(handle, 0)
            win32api.CloseHandle(handle)
            wallpaper_logger.info(f"已终止进程 (PID: {pid})，窗口句柄: 0x{hwnd:08X}")
            return True
    except Exception as e:
        wallpaper_logger.error(f"通过窗口句柄终止进程失败: \n\t {e}")
    return False

def get_workerw():
    """获取 WorkerW 窗口句柄（Windows 桌面底层窗口）"""
    if not sys.platform.startswith("win"):
        wallpaper_logger.error("get_workerw 仅在 Windows 下有效")
        return None

    progman = win32gui.FindWindow("Progman", None)
    if progman == 0:
        wallpaper_logger.error("未找到 Progman 窗口")
        return None

    # 向 Progman 发送消息，触发创建 WorkerW（0x052C 是 WM_USER+?，用于切换桌面）
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000)

    workerw = []

    def enum_win(hwnd, _):
        # 查找包含 SHELLDLL_DefView 的窗口
        shellview = win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None)
        if shellview != 0:
            # 找到其父窗口（WorkerW）
            worker = win32gui.FindWindowEx(0, hwnd, "WorkerW", None)
            if worker != 0:
                workerw.append(worker)
        return True

    win32gui.EnumWindows(enum_win, None)

    if not workerw:
        wallpaper_logger.error("未找到 WorkerW 窗口")
        return None

    wallpaper_logger.info(f"找到 WorkerW 窗口句柄：0x{workerw[0]:08X}")
    return workerw[0]


def set_windows_to_workerw(target: Union[str, int, None]):
    """
    将指定窗口嵌入 WorkerW 作为桌面壁纸
    :param target: 窗口标题（str）或窗口句柄（int）
    :return: 成功返回 hwnd，失败返回 -1
    """
    if not sys.platform.startswith("win"):
        wallpaper_logger.error("set_windows_to_workerw 仅在 Windows 下有效")
        return -1

    hwnd = 0

    # ----- 解析目标窗口 -----
    if isinstance(target, str):
        if not target.strip():
            wallpaper_logger.error("窗口标题不能为空")
            return False
        hwnd = win32gui.FindWindow(None, target.strip())
        if hwnd == 0:
            wallpaper_logger.warning(f"未找到标题为 '{target}' 的窗口")
            return -1
        wallpaper_logger.info(f"通过标题 '{target}' 找到窗口句柄：0x{hwnd:08X}")

    elif isinstance(target, int):
        hwnd = target
        if hwnd <= 0:
            wallpaper_logger.warning(f"无效窗口句柄：0x{hwnd:08X}")
            return -1
        if not win32gui.IsWindow(hwnd):
            wallpaper_logger.warning(f"句柄 0x{hwnd:08X} 不是有效窗口")
            return -1
        wallpaper_logger.info(f"使用指定窗口句柄：0x{hwnd:08X}")

    else:
        wallpaper_logger.error(f"不支持的参数类型：{type(target)}，仅支持 str 或 int")
        return -1

    # ----- 获取 WorkerW -----
    workerw = get_workerw()
    if not workerw:
        return -1

    # ----- 嵌入并设置样式 -----
    try:
        # 设置父窗口
        win32gui.SetParent(hwnd, workerw)

        # 修改窗口样式为 WS_CHILD，并保持可见
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style |= win32con.WS_CHILD | win32con.WS_VISIBLE
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

        # 移除窗口边框和标题栏
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style &= ~(win32con.WS_EX_DLGMODALFRAME | win32con.WS_EX_WINDOWEDGE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

        # 设置窗口位置和大小（覆盖整个屏幕）
        screen_w, screen_h = get_screen_size()
        win32gui.SetWindowPos(
            hwnd,
            0,                  # 忽略，因为 SWP_NOZORDER 标志会保持 Z 序
            0, 0,
            screen_w, screen_h,
            win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED  # 确保样式更新
        )

        wallpaper_logger.info(f"窗口 0x{hwnd:08X} 已成功嵌入 WorkerW，尺寸：{screen_w}x{screen_h}")
        return hwnd

    except Exception as e:
        wallpaper_logger.exception(f"嵌入窗口到 WorkerW 失败：{e}")
        return -1