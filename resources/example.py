import math
import random
import time

try:
    from WallpaperFrame import WallpaperFrame
except:
    pass


class Meteor:
    def __init__(self, x, y, vx, vy, size):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = size
        self.history = []          # 存储历史位置 (x, y)
        self.max_history = 10      # 拖尾长度

    def add_history(self):
        self.history.append((self.x, self.y))
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def update(self, w, h):
        self.x += self.vx
        self.y += self.vy
        if self.y > h + 20 or self.x < -20 or self.x > w + 20:
            # 超出屏幕边界则重置到顶部边缘
            self.x = random.uniform(0, w)
            self.y = random.uniform(-h * 0.3, -10)
            angle = -math.pi/4
            speed = random.uniform(8, 15)
            self.vx = speed * math.sin(angle)
            self.vy = speed * math.cos(angle)
            self.size = random.uniform(4, 8)   # 流星头大小
            self.history.clear()
            # 预填充历史，使拖尾一开始就有长度
            for i in range(self.max_history):
                self.history.append((self.x - self.vx * i * 0.1,
                                     self.y - self.vy * i * 0.1))
        else:
            self.add_history()

    def draw(self, frame: WallpaperFrame):
        """绘制流星及其拖尾（渐变效果）"""
        hist_len = len(self.history)
        for idx, (x, y) in enumerate(self.history):
            # 拖尾：越旧越淡越小
            t = idx / max(1, hist_len - 1)   # 0=旧, 1=新
            alpha = int(80 + 175 * t)
            radius = self.size * (0.3 + 0.7 * t)
            # 颜色从淡蓝渐变到白色
            color = (255, 255, int(50 + 55 * t), alpha)
            frame.draw_circle((x, y), radius, fill=color, color=color)
        # 流星头（最亮最大）
        head_color = (255, 255, 255, 255)
        frame.draw_circle((self.x, self.y), self.size * 1.3, fill=head_color, color=head_color)


# ==================== 全局数据 ====================
particles = []
fps_display = 0
last_fps_time = 0
frame_counter = 0

def init(target: WallpaperFrame):
    global particles
    w, h = target.width, target.height
    for _ in range(20):   # 流星数量
        x = random.uniform(0, w)
        y = random.uniform(-h * 0.5, 0)
        angle = -math.pi/4
        speed = random.uniform(8, 15)
        vx = speed * math.sin(angle)
        vy = speed * math.cos(angle)
        size = random.uniform(4, 8)
        p = Meteor(x, y, vx, vy, size)
        # 预填充历史
        for i in range(p.max_history):
            p.history.append((x - vx * i * 0.1, y - vy * i * 0.1))
        particles.append(p)

def update(target: WallpaperFrame):
    global frame_counter, last_fps_time, fps_display
    w, h = target.width, target.height
    for p in particles:
        p.update(w, h)

    # 计算帧率（简单估算）
    frame_counter += 1
    now = time.time()
    if now - last_fps_time > 0.5:
        fps_display = frame_counter / (now - last_fps_time)
        frame_counter = 0
        last_fps_time = now

def draw(target: WallpaperFrame):
    # 直接绘制流星
    for p in particles:
        p.draw(target)
    # 显示帧率