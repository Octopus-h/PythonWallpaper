#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import dearpygui.dearpygui as dpg
import math
import win32gui
import random
# 配置参数
WIDTH = 1280
HEIGHT = 720
PARTICLE_COUNT = 10
COLORS = [
    (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
    (255, 255, 0, 255), (0, 255, 255, 255), (255, 215, 0, 255)
]

class Particle:
    def __init__(self, x, y, vx, vy, size, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = size
        self.color = color
        self.age = 0
        self.flag = 1

    def update(self, w, h):
        self.x += self.vx
        self.y += self.vy
        self.age += self.flag * 50

        if self.x < 0 or self.x > w:
            self.vx = -self.vx
        if self.y < 0 or self.y > h:
            self.vy = -self.vy

        if (self.age >= 2000 and self.flag > 0) or (self.age <= 0 and self.flag < 0):
            self.flag = -self.flag

    def draw(self, drawlist):
        # 绘制当前点
        r = self.size + self.age * 0.01
        dpg.draw_circle((self.x, self.y), r, color=self.color, fill=self.color, parent=drawlist)


def init_particles(w, h):
    particles = []
    for _ in range(PARTICLE_COUNT):
        x = random.uniform(0, w)
        y = random.uniform(0, h)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(3, 5)
        vx = speed * math.cos(angle)
        vy = speed * math.sin(angle)
        size = random.uniform(30, 40)
        color = random.choice(COLORS)
        p = Particle(x, y, vx, vy, size, color)
        particles.append(p)
    return particles

def on_resize():
    vp_w = dpg.get_viewport_client_width()
    vp_h = dpg.get_viewport_client_height()
    dpg.configure_item("main_window", width=vp_w, height=vp_h)
    dpg.configure_item("drawlist", width=vp_w, height=vp_h)
    # 重新绘制背景（可选）
    dpg.delete_item("drawlist", children_only=True)
    dpg.draw_rectangle((0, 0), (vp_w, vp_h), fill=(0, 0, 0, 255), parent="drawlist")
    # 更新粒子的世界边界（可选）
    global WIDTH, HEIGHT
    WIDTH, HEIGHT = vp_w, vp_h

def main():
    dpg.create_context()
    dpg.create_viewport(title="Particle Demo", width=1280, height=720, decorated=False)
    dpg.setup_dearpygui()

    vp_w = dpg.get_viewport_width()
    vp_h = dpg.get_viewport_height()

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
            dpg.draw_rectangle((0, 0), (vp_w, vp_h), fill=(0, 0, 0, 255))

    dpg.show_viewport()

    # ========== 获取窗口句柄并输出 ==========
    try:
        hwnd = win32gui.FindWindow(None, "Particle Demo")
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
    particles = init_particles(vp_w, vp_h)

    last_time = dpg.get_total_time()
    while dpg.is_dearpygui_running():
        current_time = dpg.get_total_time()
        dt = current_time - last_time
        if dt > 0.1:
            dt = 0.016
        last_time = current_time

        for p in particles:
            p.update(WIDTH, HEIGHT)

        dpg.delete_item("drawlist", children_only=True)
        for p in particles:
            p.draw("drawlist")

        dpg.render_dearpygui_frame()

    dpg.destroy_context()

if __name__ == "__main__":
    main()