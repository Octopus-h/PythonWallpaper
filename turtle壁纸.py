#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import turtle

def run_turtle_wallpaper():
    # 创建 turtle 屏幕
    screen = turtle.Screen()
    screen.title("Turtle Wallpaper")          # 设置窗口标题
    screen.bgcolor("black")                   # 背景色黑色
    screen.setup(width=1.0, height=1.0)       # 全屏模式

    # 创建海龟
    t = turtle.Turtle()
    t.speed(0)
    t.color("cyan")

    def draw_spiral():
        """绘制螺旋线动画"""
        t.clear()
        t.penup()
        t.goto(0, 0)
        t.pendown()
        length = 5
        for _ in range(200):
            t.forward(length)
            t.left(89)
            length += 2
        screen.ontimer(draw_spiral, 50)        # 50ms 后重绘

    # 启动动画
    draw_spiral()

    # 进入主循环（会阻塞，直到窗口关闭）
    turtle.done()

if __name__ == "__main__":
    run_turtle_wallpaper()