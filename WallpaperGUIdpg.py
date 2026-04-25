import time

from dearpygui import dearpygui as dpg
import os

class WallpaperGUI:
    def __init__(self):
        self.window_tag = "about_window"
        self.label_tag = "about_label"
        self.font_tag = "main_chs_font"
        self.font_path = os.path.join(os.path.dirname(__file__), "resources", "LXGWWenKaiLite-Light.ttf")

        self.font = None

    def build_about_text(self):
        return """
动态壁纸程序
版本 1.0.5.2
作者：Octopus-h
基于 FreeSimpleGUIWx 和 pywin32
使用 ffplay 播放视频壁纸
Github项目地址：https://github.com/Octopus-h/PythonWallpaper
BiliBili：https://space.bilibili.com/1549375854

ffplay来自：
https://github.com/Octopus-h/ffplay-minimal-build

如果出现默认壁纸，可能是：exe没有配套json，你的壁纸路径改变，等等
如果有疑问，请找到程序目录下的last.log，或许可以帮到你
exe版本请到Github项目查看release
更新时请记得复制resources下的配置文件(其实目前并不重要)

致谢：
感谢所有使用和支持本软件的朋友。
感谢ffmpeg：https://git.ffmpeg.org/ffmpeg.git
感谢cx_Freeze：https://cx-freeze.readthedocs.io/
感谢霞鹜文楷：https://github.com/lxgw/LxgwWenKai-Lite/
感谢wxPython：https://github.com/wxWidgets/Phoenix/blob/wxPython-4.2.0
等等......

更新历史：
2026/4/26-v1.0.5.2：更换gui库
2026/3/27-v1.0.5.2：重写装饰器
                    更换图标
2026/3/6-v1.0.5.2：修正自启时无法加载.py脚本
2026/2/25-v1.0.5.1：修正exe无法导入的bug(由python打包的exe启动过慢也可能失败)
2026/2/24-v1.0.5：添加更新历史
                  更正了版本号
                  添加托盘选项 杂项 设置 (然而并未想好设置应包含什么)
                  使关于的窗口更大，字体更大
                  修改WallpaperFrame，采用多线程调用update()，避免阻塞主线程
2026/2/23-v1.0.4：创建Github项目
        """

    def setup_font(self):
        if not os.path.exists(self.font_path):
            print("未找到中文字体文件，中文可能无法显示")
            return None
        with dpg.font_registry():
            self.font = dpg.add_font(self.font_path, 22, tag=self.font_tag)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full, parent=self.font)
        if self.font:
            dpg.bind_font(self.font_tag)

    def show_about_popup(self):
        dpg.create_context()
        self.setup_font()

        with dpg.window(label="关于", tag=self.window_tag, autosize=False,
                        show=True, no_collapse=True,
                        no_title_bar=True, no_resize=True, no_move=True):
            dpg.add_text(self.build_about_text(), tag=self.label_tag, wrap=750)
            dpg.add_button(label="关闭", width=-1, callback=lambda *_: [dpg.configure_item(self.window_tag, show=False), dpg.stop_dearpygui()])

        def on_resize():
            vp_w = dpg.get_viewport_width()
            vp_h = dpg.get_viewport_height()
            dpg.configure_item(self.window_tag, width=vp_w, height=vp_h)

        dpg.set_viewport_resize_callback(on_resize)

        dpg.create_viewport(title='about', width=800, height=640, decorated=True)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def stop(self):
        pass

if __name__ == '__main__':
    gui = WallpaperGUI()
    gui.show_about_popup()