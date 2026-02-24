#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import wx
import threading

from WorkerW import get_screen_size

class WallpaperFrame(wx.Frame):
    def __init__(self, update_func, init_func=None, draw_func=None):
        """
        :param update_func: 更新函数，将在后台线程中循环调用，接收 self，仅修改数据
        :param init_func:   初始化函数，接收 self，在主线程中调用
        :param draw_func:   绘制函数，接收 (gc, width, height, self)，在主线程中调用
        """
        screen_width, screen_height = get_screen_size()
        super().__init__(None, style=wx.NO_BORDER)
        self.SetSize(screen_width, screen_height)
        self.SetBackgroundColour(wx.BLACK)

        self.update_func = update_func
        self.draw_func = draw_func

        # 线程同步标志
        self._alive = True
        self._data_lock = threading.Lock()

        # 绑定事件
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_TIMER, self.on_timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        # 创建定时器，仅用于触发重绘（可选）
        self.timer = wx.Timer(self)
        self.timer.Start(16)

        # 调用初始化函数（在主线程中执行）
        if callable(init_func):
            init_func(self)

        # 启动后台更新线程
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()

        self.SetDoubleBuffered(True)
        self.Show()

    def _update_loop(self):
        """后台线程：循环调用 update_func，并通过 wx.CallAfter 通知主线程重绘"""
        while self._alive:
            if callable(self.update_func):
                self.update_func(self)   # 注意：update_func 应只修改数据，不操作 GUI
            # 请求主线程重绘
            wx.CallAfter(self._request_redraw)
            # 控制更新频率（例如与定时器同步）
            wx.MilliSleep(16)   # 约 60 FPS，可调整

    def _request_redraw(self):
        """在主线程中调用，请求重绘（检查窗口是否存活）"""
        if not self._alive:
            return
        self.Refresh(False)

    def on_timer(self, event):
        """定时器事件：可留空，重绘由 _request_redraw 触发"""
        pass

    def on_paint(self, event):
        """绘图事件：使用双缓冲和 GraphicsContext 绘制"""
        dc = wx.BufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        if gc and callable(self.draw_func):
            w, h = self.GetSize()
            self.draw_func(gc, w, h, self)

    def on_close(self, event):
        """窗口关闭时安全停止后台线程"""
        self._alive = False
        self.timer.Stop()
        if self._update_thread.is_alive():
            self._update_thread.join(timeout=1.0)
        self.Destroy()

    def stop(self):
        """供外部调用的停止方法（例如在切换壁纸时）"""
        if self._alive:
            self._alive = False
            self.timer.Stop()
            if self._update_thread.is_alive():
                self._update_thread.join(timeout=1.0)
            self.Close()

# 以下调试用

# 全局变量存储动画数据
rect = {
    'x': 100.0,
    'y': 100.0,
    'vx': 4.0,
    'vy': 3.0,
    'size': 80,
    'color': wx.Colour(0, 150, 255)  # 亮蓝色
}

# 帧率统计
frame_count = 0
last_time = None
fps = 0

def init(target):
    pass

def update(target):
    pass

def draw(gc, width, height, target):
    """绘制函数：使用 GraphicsContext 绘制矩形和调试信息"""
    # 绘制矩形
    gc.SetPen(wx.Pen(wx.WHITE, 2))          # 白色边框
    gc.SetBrush(wx.Brush(rect['color']))    # 蓝色填充
    x = rect['x'] - rect['size'] / 2
    y = rect['y'] - rect['size'] / 2
    gc.DrawRectangle(x, y, rect['size'], rect['size'])

    # 绘制文字信息
    gc.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT,
                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL), wx.WHITE)
    info = f"FPS: {fps}\nPos: ({rect['x']:.1f}, {rect['y']:.1f})"
    gc.DrawText(info, 20, 20)

    # 绘制辅助网格（可选）
    gc.SetPen(wx.Pen(wx.Colour(80, 80, 80), 1))
    for y in range(0, height, 50):
        gc.StrokeLine(0, y, width, y)
    for x in range(0, width, 50):
        gc.StrokeLine(x, 0, x, height)


# ========== 独立运行测试 ==========
if __name__ == "__main__":
    app = wx.App(False)
    frame = WallpaperFrame(update, init, draw)
    app.MainLoop()