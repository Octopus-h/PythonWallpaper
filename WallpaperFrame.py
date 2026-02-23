#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import wx

from WorkerW import get_screen_size

class WallpaperFrame(wx.Frame):
    def __init__(self, update_func, init_func=None, draw_func=None):
        """
        :param update_func: 更新函数，接收 self，负责更新数据并调用 self.Refresh()
        :param init_func:   初始化函数，接收 self，负责创建数据结构
        :param draw_func:   绘制函数，接收 (gc, width, height, self)，使用 GraphicsContext 绘制
        """
        # 获取屏幕尺寸
        screen_width, screen_height = get_screen_size()
        
        # 创建无边框、全屏框架
        super().__init__(None, style=wx.NO_BORDER)
        self.SetSize(screen_width, screen_height)
        self.SetBackgroundColour(wx.BLACK)
        
        # 保存函数
        self.update_func = update_func
        self.init_func = init_func
        self.draw_func = draw_func
        
        # 绑定事件
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_TIMER, self.on_timer)
        
        # 创建定时器（约 60 FPS）
        self.timer = wx.Timer(self)
        self.timer.Start(16)
        
        # 调用初始化函数
        if callable(self.init_func):
            self.init_func(self)

        self.SetDoubleBuffered(True)
        
        self.Show()
    
    def on_paint(self, event):
        """绘图事件：使用 GraphicsContext 绘制"""
        dc = wx.PaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        if gc and callable(self.draw_func):
            w, h = self.GetSize()
            self.draw_func(gc, w, h, self)
    
    def on_timer(self, event):
        """定时器事件：更新数据并触发重绘"""
        if callable(self.update_func):
            self.update_func(self)
            self.Refresh(False)  # 请求重绘

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