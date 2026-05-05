import threading
import time
import os
from typing import List, Tuple, Union
import win32gui
import dearpygui.dearpygui as dpg

from WorkerW import get_screen_size
from FileEdit import wallpaper_logger

class WallpaperFrame:
    def __init__(self, update_func, init_func=None, draw_func=None, width=None, height=None, target_fps=60):
        self._running = True
        self.update_func = update_func
        self.draw_func = draw_func
        self.init_func = init_func

        self.canvas_tag = "dpg_canvas"
        self.window_tag = "dpg_win"
        self.font_tag = "main_chs_font"
        self.viewport_title = "WallpaperFrame"

        self.width, self.height = (width, height) if width and height else get_screen_size()

        self._draw_interval = 1.0 / target_fps if target_fps > 0 else 0
        self._last_update_time = 0
        self._last_draw_time = 0

        self._mutex = threading.Lock()
        self.data = {}

        self._setup_ui()

        if callable(self.init_func):
            self.init_func(self)

        dpg.set_frame_callback(dpg.get_frame_count() + 1, self._on_frame)

        dpg.create_viewport(title=self.viewport_title, width=self.width, height=self.height, decorated=False)

    def GetHandle(self):
        for _ in range(30):
            hwnd = win32gui.FindWindow(None, self.viewport_title)
            if hwnd:
                wallpaper_logger.debug(f"获取到句柄{hwnd}")
                return hwnd
            else:
                wallpaper_logger.warning(f"未获取到句柄")
            time.sleep(0.05)
        return None

    def _setup_ui(self):
        with dpg.window(tag=self.window_tag, width=self.width, height=self.height,
                    pos=(0, 0),
                    no_title_bar=True,
                    no_scrollbar=True,
                    no_scroll_with_mouse=True,
                    no_resize=True,
                    no_move=True,
                    autosize=False,
                    no_collapse=True,
                    no_close=True):
            dpg.add_drawlist(width=self.width, height=self.height, tag=self.canvas_tag)

    def _on_frame(self):
        if not self._running:
            return
        now = time.time()

        if now - self._last_update_time >= self._draw_interval:
            self._last_update_time = now
            if callable(self.update_func):
                self.update_func(self)

        if self._draw_interval == 0 or (now - self._last_draw_time) >= self._draw_interval:
            self._last_draw_time = now
            with self._mutex:
                dpg.delete_item(self.canvas_tag, children_only=True)
                if callable(self.draw_func):
                    self.draw_func(self)

        dpg.set_frame_callback(dpg.get_frame_count() + 1, self._on_frame)

    def stop(self):
        self._running = False

    def Close(self):
        self._running = False

    # ======================== 常用绘图 API 封装 ========================
    def draw_line(self, p1: Tuple[float, float], p2: Tuple[float, float],
                  color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                  thickness: float = 1.0):
        """绘制直线"""
        dpg.draw_line(p1, p2, color=color, thickness=thickness, parent=self.canvas_tag)

    def draw_circle(self, center: Tuple[float, float], radius: float,
                    color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                    fill: Tuple[int, int, int, int] = (0, 0, 0, -255),
                    thickness: float = 1.0, segments: int = 0):
        """绘制圆形"""
        dpg.draw_circle(center, radius, color=color, fill=fill,
                        thickness=thickness, segments=segments, parent=self.canvas_tag)

    def draw_rectangle(self, pmin: Tuple[float, float], pmax: Tuple[float, float],
                       color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                       fill: Tuple[int, int, int, int] = (0, 0, 0, -255),
                       multicolor: bool = False,
                       rounding: float = 0.0, thickness: float = 1.0):
        """绘制矩形（支持圆角）"""
        dpg.draw_rectangle(pmin, pmax, color=color, fill=fill,
                           multicolor=multicolor,
                           rounding=rounding, thickness=thickness, parent=self.canvas_tag)

    def draw_polygon(self, points: List[list[float]],
                     color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                     fill: Tuple[int, int, int, int] = (0, 0, 0, -255),
                     thickness: float = 1.0):
        """绘制多边形"""
        dpg.draw_polygon(points, color=color, fill=fill, thickness=thickness, parent=self.canvas_tag)

    def draw_polyline(self, points: List[list[float]],
                      color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                      thickness: float = 1.0, closed: bool = False):
        """绘制折线/多边形轮廓"""
        dpg.draw_polyline(points, color=color, thickness=thickness, closed=closed, parent=self.canvas_tag)

    def draw_text(self, pos: Tuple[float, float], text: str,
                  color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                  size: float = 18):
        """绘制文本"""
        dpg.draw_text(pos, text, color=color, size=size, parent=self.canvas_tag)

    def draw_arrow(self, p1: Tuple[float, float], p2: Tuple[float, float],
                   color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                   thickness: float = 1.0, size: int = 4):
        """绘制箭头"""
        dpg.draw_arrow(p1, p2, color=color, thickness=thickness, size=size, parent=self.canvas_tag)

    def draw_ellipse(self, pmin: Tuple[float, float], pmax: Tuple[float, float],
                     color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                     fill: Tuple[int, int, int, int] = (0, 0, 0, -255),
                     thickness: float = 1.0, segments: int = 32):
        """绘制椭圆（由外接矩形定义）"""
        dpg.draw_ellipse(pmin, pmax, color=color, fill=fill,
                         thickness=thickness, segments=segments, parent=self.canvas_tag)

    def draw_quad(self, p1: Tuple[float, float], p2: Tuple[float, float],
                  p3: Tuple[float, float], p4: Tuple[float, float],
                  color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                  fill: Tuple[int, int, int, int] = (0, 0, 0, -255),
                  thickness: float = 1.0):
        """绘制四边形"""
        dpg.draw_quad(p1, p2, p3, p4, color=color, fill=fill, thickness=thickness, parent=self.canvas_tag)

    def draw_triangle(self, p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float],
                      color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                      fill: Tuple[int, int, int, int] = (0, 0, 0, -255),
                      thickness: float = 1.0):
        """绘制三角形"""
        dpg.draw_triangle(p1, p2, p3, color=color, fill=fill, thickness=thickness, parent=self.canvas_tag)

    def draw_image(self, texture_tag: Union[int, str], pmin: Tuple[float, float], pmax: Tuple[float, float],
                   uv_min: Tuple[float, float] = (0.0, 0.0), uv_max: Tuple[float, float] = (1.0, 1.0),
                   color: Tuple[int, int, int, int] = (255, 255, 255, 255)):
        """绘制图像（需预先注册纹理）"""
        dpg.draw_image(texture_tag, pmin, pmax, uv_min=uv_min, uv_max=uv_max,
                       color=color, parent=self.canvas_tag)

    def draw_bezier_cubic(self, p1: Tuple[float, float], p2: Tuple[float, float],
                          p3: Tuple[float, float], p4: Tuple[float, float],
                          color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                          thickness: float = 1.0, segments: int = 0):
        """绘制三次贝塞尔曲线"""
        dpg.draw_bezier_cubic(p1, p2, p3, p4, color=color,
                              thickness=thickness, segments=segments, parent=self.canvas_tag)

    def draw_bezier_quadratic(self, p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float],
                              color: Tuple[int, int, int, int] = (255, 255, 255, 255),
                              thickness: float = 1.0, segments: int = 0):
        """绘制二次贝塞尔曲线"""
        dpg.draw_bezier_quadratic(p1, p2, p3, color=color,
                                  thickness=thickness, segments=segments, parent=self.canvas_tag)


# ================= 测试代码：使用 dpg 帧率显示 =================
rect = {
    'x': 100.0,
    'y': 100.0,
    'vx': 3.0,
    'vy': 4.0,
    'radius': 40,
    'color': (0, 150, 255, 255)
}

def init(target: WallpaperFrame):
    pass

def update(target: WallpaperFrame):
    rect['x'] += rect['vx']
    rect['y'] += rect['vy']
    if rect['x'] - rect['radius'] < 0 or rect['x'] + rect['radius'] > target.width:
        rect['vx'] *= -1
    if rect['y'] - rect['radius'] < 0 or rect['y'] + rect['radius'] > target.height:
        rect['vy'] *= -1

def draw(target: WallpaperFrame):
    if not dpg.does_item_exist(target.canvas_tag):
        return
    target.draw_circle((rect['x'], rect['y']), rect['radius'],
                    color=rect['color'], fill=rect['color'],
                    thickness=2)
    # 使用 dpg.get_frame_rate() 显示帧率（返回浮点数）
    fps = dpg.get_frame_rate()
    target.draw_text((20, 20), f"FPS: {fps:.1f}\nPos: ({rect['x']:.1f}, {rect['y']:.1f})",
                  color=(240, 240, 240, 255), size=18)

if __name__ == "__main__":
    WallpaperFrame(update, init, draw, target_fps=60)