# Dynamic Wallpaper - 动态壁纸程序

一个轻量级的 Windows 动态壁纸工具，可以将视频、可执行程序或 Python 脚本设置为桌面壁纸，并嵌入桌面底层（WorkerW）。

![截图占位符](resources/icons/icon.png)

## ✨ 功能特性

- 🎬 **视频壁纸**：使用 ffplay 播放视频文件作为桌面背景。
- 🖥️ **EXE 壁纸**：运行任意的可执行程序，并将其主窗口嵌入桌面。
- 🐍 **Python 脚本壁纸**：支持运行 Python 脚本
- 🧩 **系统托盘控制**：右键托盘图标，轻松切换壁纸、设置开机自启、查看关于信息。
- 📝 **日志记录**：自动记录运行日志，文件大小超过 256KB 自动轮转。
- 🔌 **嵌入式桌面**：通过 Windows API 将窗口嵌入 `WorkerW`，真正成为桌面的一部分。
- 📦 **打包支持**：提供 `cx_Freeze`，可生成单文件 exe。

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Windows 10/11 (仅支持 Windows)

### 安装依赖
主要依赖：
- `ruwps` – 系统托盘界面
- `pywin32` – Windows API 调用
- `dearpygui` – 高级绘图（用于 Python 脚本壁纸）

### 运行主程序
```bash
python wallpaper_window.py
```
程序启动后会在系统托盘显示图标，右键菜单选择壁纸类型。

## 📂 项目结构
```
DynamicWallpaper/
├── wallpaper_window.py      # 主程序入口
├── FileEdit.py              # 配置文件与开机自启管理
├── WorkerW.py                # Windows 窗口嵌入核心函数
├── WallpaperFrame.py         # 用于 Python 脚本壁纸的 wx.Frame 容器
├── resources/
│   ├── ffmpeg/               # ffplay.exe（视频播放）
│   ├── icons/                 # 托盘图标
│   ├── mp4/                    # 默认视频壁纸
│   └── example.py              # Python 脚本示例
├── setup.py                   # cx_Freeze 打包配置
└── README.md
```

## 🐍 编写自定义 Python 壁纸脚本

在pyenv中加入相应库，默认带有dearpygui
- 窗口创建后**立即通过 `print` 输出十六进制句柄**（主程序从 stdout 读取）

**示例**：[resources/example.py](resources/example.py)

## 🔧 打包成 EXE

### 使用 cx_Freeze
```bash
pip install cx_freeze
python setup.py build
```
生成的 exe 位于 `build/wallpaper/动态壁纸.exe`。

## ⚙️ 配置文件
程序在 `resources/config.json` 中保存上一次使用的壁纸路径和类型。格式如下：
```json
{
    "last_wallpaper_path": "C:\\video.mp4",
    "type": "video"
}
```

## 📝 日志
日志文件保存在程序根目录下的 `last.log`，采用 RotatingFileHandler，单个文件最大 256KB，保留一个备份。

## 🙏 致谢
- [ffmpeg](https://ffmpeg.org/) – 提供 ffplay 播放器
- [pywin32](https://github.com/mhammond/pywin32) – Windows API 绑定
- [ruwps](https://github.com/59de44955ebd/ruwps) – 轻量级托盘界面
- [cx_Freeze](https://cx-freeze.readthedocs.io/) – 打包工具

## 📄 许可证
本项目基于 MIT 许可证开源。