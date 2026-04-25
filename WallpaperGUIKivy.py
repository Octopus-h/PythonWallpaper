import time, os

from FileEdit import wallpaper_logger

from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.resources import resource_add_path

# --------- 全局字体设置 ---------
def set_global_font():
    font_name = "LXGWWenKaiLite-Light.ttf"
    font_dir = os.path.join(os.path.dirname(__file__), "resources")
    font_path = os.path.join(font_dir, font_name)
    if not os.path.isfile(font_path):
        wallpaper_logger.warning(f"字体文件不存在:{font_path}")
        print("字体文件不存在:",font_path)
    resource_add_path(font_dir)
    LabelBase.register(name="Roboto", fn_regular=font_path)
    wallpaper_logger.info(f"全局中字体注册成功: {font_path}")
    print("全局中文字体注册成功:", font_path)

class TextApp(App):
    def __init__(self):
        super().__init__()
        self.popup = None          # 当前弹窗实例

    def build(self):
        # 创建初始弹窗（不立即打开）
        self._create_popup("", "")
        return Label(text="")   # 隐藏的根widget

    def _create_popup(self, text: str, title: str):
        """根据文本内容创建弹窗"""
        # 创建默认的滚动文本布局
        layout = BoxLayout(orientation='vertical')
        scroll = ScrollView(size_hint=(1, 1))
        label = Label(text=text,
                        font_size=22,
                        size_hint_y=None,
                        halign="left", valign="top",
                        text_size=(800, None))
        label.bind(texture_size=lambda instance, value: setattr(label, 'height', value[1]))
        #绑定关闭按钮
        btn = Button(text="关闭", size_hint=(1, None), height=50)
        btn.bind(on_release=self._dismiss_popup)

        scroll.add_widget(label)
        layout.add_widget(scroll)
        layout.add_widget(btn)
        content = layout

        # 创建弹窗 
        popup = Popup(title=title, content=content, size_hint=(1, 1), auto_dismiss=False)
        return popup

    def _dismiss_popup(self, *args):
        """关闭弹窗并隐藏主窗口"""
        if self.popup:
            self.popup.dismiss()
        Window.hide()   # 隐藏空白根窗口

    def change_popup(self, text: str, title: str):
        """
        动态更换弹窗内容。
        :param text: 新文本（当 content 为 None 时使用）
        :param title: 新标题（如果为 None 则沿用原标题）
        """

        # 关闭旧弹窗（如果存在）
        if self.popup:
            self.popup.dismiss()
        # 替换为新弹窗
        self.popup = self._create_popup(text=text,title=title)
        # 显示窗口（如果被隐藏了）
        Window.show()
        # 打开新弹窗
        self.popup.open()

class WallpaperGUI:
    def __init__(self):
        set_global_font()
        self.textApp = None

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

    def show_about_popup(self):
        about_text = self.build_about_text()

        if not self.textApp:
            self.textApp = TextApp()

        self.textApp.change_popup(about_text, "关于")
        self.textApp.run()

    def stop(self):
        if self.textApp:
            self.textApp.stop()



if __name__ == '__main__':
    gui = WallpaperGUI()
    time.sleep(3)
    gui.show_about_popup()
    time.sleep(3)
    gui.stop()