import sys
import os
from cx_Freeze import setup, Executable

# 基础配置
base = None
if sys.platform == "win32":
    base = "Win32GUI"  # 隐藏控制台

# 找到 pywintypes39.dll 的路径（根据环境调整）
pywin32_dll_path = os.path.join(
    sys.prefix,  # Python 安装根目录
    "Lib", "site-packages", "pywin32_system32", "pywintypes39.dll"
)

# 资源文件
include_files = [
    (pywin32_dll_path, "pywintypes39.dll"),  # 补充缺失的dll
    ("resources/ffmpeg", "resources/ffmpeg"),
    ("resources/icons", "resources/icons"),
    ("resources/mp4", "resources/mp4"),
    ("resources/example.py", "resources/example.py")
]

# 可执行文件配置
executables = [
    Executable(
        "wallpaper_window.py",
        base=base,
        icon="resources/icons/icon.ico",
        target_name="动态壁纸.exe"
    )
]

build_exe_options = {
    "include_files": include_files,
    # 包含必要的模块：FreeSimpleGUIWx, wx, win32等
    "includes": [
        "FreeSimpleGUIWx",
        "wx",                # wxPython 核心
        "win32gui", "win32con", "subprocess", "ctypes",
        "json", "logging", "os", "sys", "typing", "functools"
    ],
    # 排除无用模块
    "excludes": [
        # === wxPython 冗余子模块 ===
        "wx.media", "wx._media"
        "wx.html", "wx._html",            # HTML 渲染
        # === pywin32 冗余 ===
        "pywin", "pywin.dialogs", "pywin.mfc", "win32ui",
        "win32com.gen_py", "win32com.client.makepy", "win32com.client.selecttlb",
        "win32clipboard", "win32pipe", "win32file",
        "win32security", "win32trace",
        # === 系统冗余模块 ===
        "tkinter", "tcl", "tk",  # 排除 Tkinter
        "unittest", "pytest",
        "email","smtplib", "smtplib",
        "sqlite3", "decimal",
        "http", "xml",
        "concurrent",
        # === 未使用的第三方库 ===
        "PIL", "mulitprocressing", "numpy", "matplotlib", "requests"
    ],
    "optimize": 2,
    "zip_include_packages": ["*"],
    "zip_exclude_packages": [],
    "build_exe": "build/wallpaper"
}

setup(
    name="wallpaper",
    version="1.0",
    description="动态壁纸程序",
    options={"build_exe": build_exe_options},
    executables=executables
)