#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import dearpygui.dearpygui as dpg
import math
import random
import win32gui
import time, sys
from datetime import datetime

# ---- 配置参数 ----
WIDTH = 1280
HEIGHT = 720
METEOR_COUNT = 15                   # 流星数量
ANGLE = math.radians(135)           # 运动方向角度
SPEED_MIN = 8.0
SPEED_MAX = 15.0
TAIL_LENGTH = 25
FPS_TARGET = 60.0
METEOR_SIZE_MIN = 2.0               # 流星头部半径/拖尾起始最小
METEOR_SIZE_MAX = 5.0               # 流星头部半径/拖尾起始最大

HEAD_COLOR = (143, 124, 255, 255)
TAIL_END_COLOR = (83, 104, 255, 0)

BG_COLORS=[
    (103, 77, 123, 255),      # 左上角
    (63, 77, 123, 255),      # 右上角
    (123, 127, 183, 155),      # 右下角
    (103, 157, 183, 155)       # 左下角
]

RAND_TEXT=[
    "春江潮水连海平，海上明月共潮生",
    "G = mg"
]

def lerp_color(c1, c2, t):
    """RGBA线性插值"""
    return tuple(
        int(c1[i] + (c2[i] - c1[i]) * t)
        for i in range(4)
    )

# ---- 流星类 ----
class Meteor:
    def __init__(self):
        self.reset()

    def reset(self):
        speed = random.uniform(SPEED_MIN, SPEED_MAX)
        self.x = random.uniform(-WIDTH * 0.2, WIDTH)
        self.y = random.uniform(-HEIGHT * 0.3, HEIGHT * 0.2)
        self.vx = speed * math.cos(ANGLE)
        self.vy = speed * math.sin(ANGLE)
        self.tail = []
        self.tail_len = random.randint(int(TAIL_LENGTH * 0.8), TAIL_LENGTH)
        self.thickness = random.uniform(METEOR_SIZE_MIN, METEOR_SIZE_MAX)
        self._color_cache = {}  # 清理该流星的局部颜色缓存

    def update(self):
        self.tail.insert(0, (self.x, self.y))
        if len(self.tail) > self.tail_len:
            self.tail.pop()
        self.x += self.vx
        self.y += self.vy
        if self.x > WIDTH + 100 or self.x < -100 or self.y > HEIGHT + 100:
            self.reset()

    def draw(self, drawlist):
        if len(self.tail) < 2:
            return
        total = len(self.tail) - 1
        for i in range(total):
            p1 = self.tail[i]
            p2 = self.tail[i + 1]
            ti = i / total
            # 线性插值色值缓存先查局部再查全局
            if ti not in self._color_cache:
                self._color_cache[ti] = lerp_color(HEAD_COLOR, TAIL_END_COLOR, ti)
            color = self._color_cache[ti]
            thickness = max(1, self.thickness * (2 - ti))
            dpg.draw_line(p1, p2, color=color, thickness=thickness, parent=drawlist)
        dpg.draw_circle(self.tail[0], radius=self.thickness, color=HEAD_COLOR, fill=HEAD_COLOR, parent=drawlist)

def on_resize():
    vp_w = dpg.get_viewport_client_width()
    vp_h = dpg.get_viewport_client_height()
    dpg.configure_item("main_window", width=vp_w, height=vp_h)
    dpg.configure_item("drawlist", width=vp_w, height=vp_h)
    # 重新绘制背景（可选）
    dpg.delete_item("drawlist", children_only=True)
    dpg.draw_rectangle((0, 0), (vp_w, vp_h),multicolor = True, parent="drawlist", corner_colors=BG_COLORS)
    # 更新粒子的世界边界（可选）
    global WIDTH, HEIGHT
    WIDTH, HEIGHT = vp_w, vp_h

def draw_text(w, h, text, size, parent, offsetx=1.0, offsety=1.0):
    # 获取实际文本像素宽高
    text_size = dpg.get_text_size(text)
    # 居中坐标
    if text_size:
        text_x = int((w - text_size[0]* size // 64) // 2  * offsetx)
        text_y = int((h - text_size[1]* size // 64) // 2  * offsety)
        dpg.draw_text((text_x, text_y), text, color=(255,255,255,255), size=size, parent=parent)

def main():
    dpg.create_context()
    dpg.create_viewport(title="Dynamic Meteor Shower", width=WIDTH, height=HEIGHT, decorated=False)
    dpg.setup_dearpygui()

    with dpg.font_registry():
        my_font = dpg.add_font("C:\\Windows\\Fonts\\simhei.ttf", 64, tag="simhei")   # 本地字体，字号64
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common, parent=my_font)
        dpg.bind_font("simhei")

    vp_w = dpg.get_viewport_client_width()
    vp_h = dpg.get_viewport_client_height()

    with dpg.window(tag="main_window", width=vp_w, height=vp_h,
                    pos=(0, 0),
                    no_title_bar=True,
                    no_scrollbar=True,
                    no_scroll_with_mouse=True,
                    no_resize=True,
                    no_move=True,
                    autosize=False,
                    no_collapse=True,
                    no_close=True):
        with dpg.drawlist(width=vp_w, height=vp_h, tag="drawlist"):
            dpg.draw_rectangle((0, 0), (vp_w, vp_h),multicolor = True, corner_colors=BG_COLORS)

    dpg.show_viewport()

    # ========== 获取窗口句柄并输出 ==========
    try:
        hwnd = win32gui.FindWindow(None, "Dynamic Meteor Shower")
        if hwnd:
            print(f"0x{hwnd:08X}", flush=True)
        else:
            print("0xFFFFFFFF", flush=True)
    except Exception as e:
        # 输出错误标记，主程序会处理
        print("0xFFFFFFFF", flush=True)
        print(f"获取句柄失败: {e}", file=sys.stderr)
    # =====================================

    dpg.set_viewport_resize_callback(lambda: on_resize())

    meteors = [Meteor() for _ in range(METEOR_COUNT)]

    last_change_time = time.time()
    change_interval = 10.0  # 更换一次随机文本的间隔时间
    current_random_text = random.choice(RAND_TEXT)  # 初始文本

    while dpg.is_dearpygui_running():
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        # 更新文本
        now = time.time()
        if now - last_change_time >= change_interval:
            current_random_text = random.choice(RAND_TEXT)
            last_change_time = now

        # 加载流星雨
        for m in meteors:
            m.update()
        dpg.delete_item("drawlist", children_only=True)

        # 绘制背景
        dpg.draw_rectangle((-1, -1), (vp_w, vp_h),multicolor = True, parent="drawlist", corner_colors=BG_COLORS)

        # 绘制流星雨
        for m in meteors:
            m.draw("drawlist")

        # 绘制文字
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw_text(vp_w, vp_h, time_str, 100, "drawlist", offsety=0.3)

        draw_text(vp_w, vp_h, current_random_text, 32, "drawlist", offsety=1.1)

        dpg.render_dearpygui_frame()
        time.sleep(1.0 / FPS_TARGET)

    dpg.destroy_context()

if __name__ == "__main__":
    main()