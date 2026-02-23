#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import turtle

# 不支持其他库
NOT_USE_WX = True

# 您猜怎么着，它会创建4个窗口
# 其中一个没有简易方法获取
# 会留下一个黑框

# 创建 turtle 屏幕
screen = turtle.Screen()
screen.bgcolor("black")                   # 背景色黑色
screen.setup(width=1.0, height=1.0)       # 全屏模式

# 获取底层 tkinter 窗口并设置为无边框
root = screen.getcanvas().master
# 移除标题栏和边框
root.overrideredirect(True)                # type: ignore 

# 绑定 ESC 键退出程序
def exit_program(event):
    root.quit()                            # 退出主循环
    root.destroy()                         # 销毁窗口

root.bind('<Escape>', exit_program)

#必须实现：get_hwnd()
def get_hwnd():# 返回窗口句柄(int)
    return root.winfo_id()

#必须实现：main()
def main():
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
    print("hwnd:",hex(screen.getcanvas().winfo_toplevel().winfo_id()))
    main()