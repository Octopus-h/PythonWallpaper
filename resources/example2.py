#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import dearpygui.dearpygui as dpg
import math
import random
import win32gui
import time, sys
import ctypes
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

# ---- 新增：鼠标交互配置 ----
MOUSE_INFLUENCE_RADIUS = 220.0    # 鼠标引力影响范围（像素）
MOUSE_ATTRACTION = 0.6            # 引力强度（正数吸引，负数排斥）
CLICK_BURST_COUNT = 12            # 每次点击生成的爆发流星数
CLICK_BURST_SPEED_MIN = 3.0
CLICK_BURST_SPEED_MAX = 8.0
CLICK_BURST_LIFE = 40             # 爆发流星存活帧数
MOUSE_GLOW_RADIUS = 60.0          # 鼠标跟随光晕半径


def lerp_color(c1, c2, t):
    """RGBA线性插值"""
    return tuple(
        int(c1[i] + (c2[i] - c1[i]) * t)
        for i in range(4)
    )

# ---- 流星类（新增鼠标引力逻辑） ----
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

    def update(self, mouse_x=None, mouse_y=None):
        self.tail.insert(0, (self.x, self.y))
        if len(self.tail) > self.tail_len:
            self.tail.pop()

        # 新增：鼠标引力影响
        if mouse_x is not None and mouse_y is not None:
            dx = mouse_x - self.x
            dy = mouse_y - self.y
            dist = math.hypot(dx, dy)
            # 仅在影响半径内生效，距离越近拉力越强
            if dist < MOUSE_INFLUENCE_RADIUS and dist > 1:
                force = MOUSE_ATTRACTION * (1 - dist / MOUSE_INFLUENCE_RADIUS)
                self.vx += (dx / dist) * force
                self.vy += (dy / dist) * force

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


# ---- 新增：点击爆发粒子类 ----
class BurstParticle:
    def __init__(self, x, y):
        # 随机360度方向发射
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(CLICK_BURST_SPEED_MIN, CLICK_BURST_SPEED_MAX)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = CLICK_BURST_LIFE
        self.max_life = CLICK_BURST_LIFE
        self.thickness = random.uniform(1.5, 3.5)
        self.tail = []
        self.tail_len = 8

    def update(self):
        self.tail.insert(0, (self.x, self.y))
        if len(self.tail) > self.tail_len:
            self.tail.pop()
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        # 速度自然衰减，模拟阻力
        self.vx *= 0.98
        self.vy *= 0.98

    def draw(self, drawlist):
        if len(self.tail) < 2:
            return
        alpha_ratio = self.life / self.max_life
        total = len(self.tail) - 1
        for i in range(total):
            p1 = self.tail[i]
            p2 = self.tail[i + 1]
            ti = i / total
            base_color = lerp_color(HEAD_COLOR, TAIL_END_COLOR, ti)
            # 随寿命逐渐透明
            color = (base_color[0], base_color[1], base_color[2], int(base_color[3] * alpha_ratio))
            thickness = max(0.5, self.thickness * (1 - ti) * alpha_ratio)
            dpg.draw_line(p1, p2, color=color, thickness=thickness, parent=drawlist)
        # 绘制粒子头部
        head_alpha = int(HEAD_COLOR[3] * alpha_ratio)
        head_color = (HEAD_COLOR[0], HEAD_COLOR[1], HEAD_COLOR[2], head_alpha)
        dpg.draw_circle(self.tail[0], radius=self.thickness, color=head_color, fill=head_color, parent=drawlist)

    @property
    def is_dead(self):
        return self.life <= 0


def on_resize():
    vp_w = dpg.get_viewport_client_width()
    vp_h = dpg.get_viewport_client_height()
    dpg.configure_item("main_window", width=vp_w, height=vp_h)
    dpg.configure_item("drawlist", width=vp_w, height=vp_h)
    # 重新绘制背景（可选）
    dpg.delete_item("drawlist", children_only=True)
    dpg.draw_rectangle((0, 0), (vp_w, vp_h), multicolor=True, parent="drawlist", corner_colors=BG_COLORS)
    # 更新粒子的世界边界
    global WIDTH, HEIGHT
    WIDTH, HEIGHT = vp_w, vp_h


def draw_text(w, h, text, size, parent, offsetx=1.0, offsety=1.0):
    # 获取实际文本像素宽高
    text_size = dpg.get_text_size(text)
    # 居中坐标
    if text_size:
        text_x = int((w - text_size[0] * size // 64) // 2 * offsetx)
        text_y = int((h - text_size[1] * size // 64) // 2 * offsety)
        dpg.draw_text((text_x, text_y), text, color=(255, 255, 255, 255), size=size, parent=parent)


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
            dpg.draw_rectangle((0, 0), (vp_w, vp_h), multicolor=True, corner_colors=BG_COLORS)

    dpg.show_viewport()

    # ========== 获取窗口句柄并输出 ==========
    try:
        hwnd = win32gui.FindWindow(None, "Dynamic Meteor Shower")
        if hwnd:
            print(f"0x{hwnd:08X}", flush=True)
        else:
            print("0xFFFFFFFF", flush=True)
    except Exception as e:
        print("0xFFFFFFFF", flush=True)
        print(f"获取句柄失败: {e}", file=sys.stderr)
    # =====================================

    dpg.set_viewport_resize_callback(lambda: on_resize())
    meteors = [Meteor() for _ in range(METEOR_COUNT)]
    burst_particles = []       # 存放点击爆发的粒子
    prev_mouse_left = False    # 记录上一帧鼠标左键状态，用于检测点击沿
    last_change_time = time.time()
    change_interval = 10.0  # 更换一次随机文本的间隔时间
    current_random_text = random.choice(RAND_TEXT)  # 初始文本

    while dpg.is_dearpygui_running():
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        # ---- 获取鼠标状态 ----
        mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
        current_mouse_left = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        # 检测左键按下瞬间（上升沿），触发爆发
        if current_mouse_left and not prev_mouse_left:
            for _ in range(CLICK_BURST_COUNT):
                burst_particles.append(BurstParticle(mouse_x, mouse_y))
        prev_mouse_left = current_mouse_left

        # 更新文本
        now = time.time()
        if now - last_change_time >= change_interval:
            current_random_text = random.choice(RAND_TEXT)
            last_change_time = now

        # 更新常规流星（传入鼠标坐标）
        for m in meteors:
            m.update(mouse_x, mouse_y)
        # 更新爆发粒子，移除已死亡的
        for p in burst_particles:
            p.update()
        burst_particles = [p for p in burst_particles if not p.is_dead]

        # 清空画布并重绘
        dpg.delete_item("drawlist", children_only=True)
        # 绘制背景
        dpg.draw_rectangle((-1, -1), (vp_w, vp_h), multicolor=True, parent="drawlist", corner_colors=BG_COLORS)
        # 绘制常规流星雨
        for m in meteors:
            m.draw("drawlist")
        # 绘制点击爆发粒子
        for p in burst_particles:
            p.draw("drawlist")

        # 绘制文字
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw_text(vp_w, vp_h, time_str, 100, "drawlist", offsety=0.3)
        draw_text(vp_w, vp_h, current_random_text, 32, "drawlist", offsety=1.1)

        dpg.render_dearpygui_frame()
        time.sleep(1.0 / FPS_TARGET)

    dpg.destroy_context()


if __name__ == "__main__":
    main()