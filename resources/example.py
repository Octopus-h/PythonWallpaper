#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import wx
import math
import random

# 标记使用 wx 模式
# 不支持其他库
# NOT_USE_WX = False

# 颜色定义（wx.Colour 列表）
colors = [
    wx.Colour(255, 0, 0),      # 红
    wx.Colour(0, 255, 0),      # 绿
    wx.Colour(0, 0, 255),      # 蓝
    wx.Colour(255, 255, 0),    # 黄
    wx.Colour(0, 255, 255),    # 青
    wx.Colour(255, 215, 0),    # 金
]

class Particle:
    def __init__(self, x, y, vx, vy, size, color, age):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = size
        self.color = color
        self.flag = 1
        self.age = age   # 用于动态改变大小的偏移量

def init(target):
    """初始化粒子数据"""
    target.particles = []
    w, h = target.GetSize()
    for _ in range(10):
        x = random.uniform(0, w)
        y = random.uniform(0, h)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(3, 5)
        vx = speed * math.cos(angle)
        vy = speed * math.sin(angle)
        size = random.uniform(30, 40)
        color = random.choice(colors)
        age = random.uniform(0, 1000)
        target.particles.append(Particle(x, y, vx, vy, size, color, age))

# 警告：update()采用多线程调用，请勿写死循环，sleep，不应操作GUI
def update(target):
    """更新粒子位置"""
    w, h = target.GetSize()
    for p in target.particles:
        p.x += p.vx
        p.y += p.vy
        p.age += p.flag * 50

        # 边界反弹（假设原点在左上角）
        if p.x < 0 or p.x > w:
            p.vx = -p.vx
        if p.y < 0 or p.y > h:
            p.vy = -p.vy

        if (p.age >= 1000 and p.flag > 0) or (p.age <= 0 and p.flag < 0):
            p.flag = -p.flag

def draw(gc, width, height, target):
    """使用 GraphicsContext 绘制所有粒子"""
    # 清除背景
    bgColor = wx.Colour(0, 0, 0, 20)
    gc.SetPen(wx.Pen(bgColor, 1))
    gc.SetBrush(wx.Brush(bgColor))
    gc.DrawRectangle(0, 0, width, height)

    for p in target.particles:
        # 设置画笔和画刷
        gc.SetPen(wx.Pen(p.color, 1))   # 边框用同色细线
        gc.SetBrush(wx.Brush(p.color))
        
        # 计算当前大小（带 age 微调）
        r = p.size + p.age * 0.05
        
        # 绘制圆形（左上角坐标模式，gc 的 DrawEllipse 需要左上角和宽高）
        # 注意：GraphicsContext 默认坐标原点在窗口左上角
        gc.DrawEllipse(p.x - r/2, p.y - r/2, r, r)