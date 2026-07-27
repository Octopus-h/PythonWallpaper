use macroquad::prelude::*;
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::UI::WindowsAndMessaging::{
    ShowWindow,
    SW_HIDE,
    GetWindowRect,
    GetCursorPos,
    SW_SHOW,
    FindWindowW,
    GWL_EXSTYLE, GWL_STYLE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED,
    SetWindowLongPtrW, SetWindowPos,
};
use windows::core::*;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc::{Sender, Receiver},
};
use std::cell::RefCell;

pub enum UiCommand {
    ShowAbout(String),
    Hide,
    Exit,
}

static UI_RUNNING: AtomicBool = AtomicBool::new(false);
const FONT_PATH: &str = "resources/LXGWWenKaiLite-Light.ttf";

thread_local! {
    static DRAGGING: RefCell<bool> = const { RefCell::new(false) };
    static DRAG_START_MOUSE: RefCell<POINT> = const { RefCell::new(POINT { x: 0, y: 0 }) };
    static DRAG_START_WINDOW: RefCell<(i32, i32)> = const { RefCell::new((0, 0)) };
    static CACHED_LINES: RefCell<Option<(String, Vec<String>)>> = const { RefCell::new(None) };
}

#[cfg(target_os="windows")]
fn get_hwnd() -> Option<HWND> {
    let hwnd = unsafe{ FindWindowW(None, w!("关于 PythonWallpaper")) };
    if hwnd.0 == 0 {
        None
    } else {
        Some(hwnd)
    }
}

fn hide_window() {
    unsafe {
        if let Some(hwnd) = get_hwnd() {
            ShowWindow(hwnd, SW_HIDE);
        }
    }
}

fn show_window() {
    unsafe {
        if let Some(hwnd) = get_hwnd() {
            ShowWindow(hwnd, SW_SHOW);
        }
    }
}

fn make_borderless() {
    if let Some(hwnd) = get_hwnd() {
        // 窗口样式（无边框，无标题栏，但保留客户区绘制）
        // WS_POPUP       0x80000000
        // WS_VISIBLE     0x10000000
        // WS_CLIPCHILDREN 0x02000000
        // WS_CLIPSIBLINGS 0x04000000
        let borderless_draggable_style = 0x9600_0000u32 as isize;

        // 扩展样式（不在任务栏显示，Alt+Tab 不出现）
        // WS_EX_TOOLWINDOW 0x00000080
        let toolwindow_ex_style = 0x0000_0080u32 as isize;
        unsafe {
            SetWindowLongPtrW(hwnd, GWL_STYLE, borderless_draggable_style);
            SetWindowLongPtrW(hwnd, GWL_EXSTYLE, toolwindow_ex_style);
            let _ = SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED);
        }
    }
}

pub fn wrap_cn_text(text: &str, font: &Font, font_size: u16, max_width: f32,) -> Vec<String> {
    // 使用 ThreadLocal 缓存，基于文本哈希判断是否需要重新计算
    let current_text = text.to_string();
    let cached = CACHED_LINES.with(|cell| {
        let borrow = cell.borrow();
        if let Some((ref old_text, ref lines)) = *borrow {
            if old_text == &current_text {
                return Some(lines.clone());
            }
        }
        None
    });

    if let Some(lines) = cached {
        return lines;
    }

    let mut result = Vec::new();

    for paragraph in text.lines() {
        let mut line = String::new();
        for ch in paragraph.chars() {
            let mut test_line = line.clone();
            test_line.push(ch);
            let size = measure_text(&test_line, Some(font), font_size, 1.0);
            if size.width > max_width && !line.is_empty() {
                result.push(line);
                line = String::new();
                line.push(ch);
            } else {
                line = test_line;
            }
        }

        if !line.is_empty() {
            result.push(line);
        }

        // 保留原文本中的空行
        if paragraph.is_empty() {
            result.push(String::new());
        }
    }
    // 缓存结果
    CACHED_LINES.with(|cell| {
        *cell.borrow_mut() = Some((current_text, result.clone()));
    });
    result
}

fn draw_about(font: &Font, text: &str, tx: &Sender<UiCommand>, scroll: &mut f32,) {
    // 颜色常量
    const BG: Color = Color::from_rgba(30, 30, 30, 255);
    const TITLE_BG: Color = Color::from_rgba(45, 45, 45, 255);
    const SCROLLBAR_BG: Color = Color::from_rgba(70, 70, 70, 180);
    const SCROLLBAR_THUMB: Color = Color::from_rgba(160, 160, 160, 220);
    const TEXT_COLOR: Color = Color::from_rgba(224, 158, 233, 255);
    const CLOSE_COLOR: Color = TEXT_COLOR;

    // 尺寸常量
    const TITLE_H: f32 = 45.0;
    const LINE_H: f32 = 32.0;
    const PADDING_X: f32 = 35.0;
    const PADDING_Y: f32 = 20.0;
    const SCROLLBAR_WIDTH: f32 = 8.0;
    const SCROLLBAR_MARGIN: f32 = 18.0;
    const CLOSE_BTN_WIDTH: f32 = 40.0;
    const FONT_SIZE: u16 = 22;

    let (win_w, win_h) = (screen_width(), screen_height());

    let (mx, my) = mouse_position();
    let hwnd = get_hwnd().unwrap_or(HWND(0));

    // ─── 拖动逻辑：按下标题栏开始拖动 ───
    if is_mouse_button_pressed(MouseButton::Left)
        && my < TITLE_H
        && mx < win_w - CLOSE_BTN_WIDTH
    {
        DRAGGING.with(|cell| *cell.borrow_mut() = true);

        let mut cursor = POINT::default();
        let _ = unsafe { GetCursorPos(&mut cursor) };
        DRAG_START_MOUSE.with(|cell| *cell.borrow_mut() = POINT {x:cursor.x, y:cursor.y});

        let mut rect = RECT::default();
        let _ = unsafe { GetWindowRect(hwnd, &mut rect) };
        DRAG_START_WINDOW.with(|cell| *cell.borrow_mut() = (rect.left, rect.top));
    }

    // ─── 拖动中移动窗口 ───
    let dragging = DRAGGING.with(|cell| *cell.borrow());
    if is_mouse_button_down(MouseButton::Left) && dragging {
        let mut cursor = POINT::default();
        let _ = unsafe { GetCursorPos(&mut cursor) };

        let start_mouse = DRAG_START_MOUSE.with(|cell| *cell.borrow());
        let start_window = DRAG_START_WINDOW.with(|cell| *cell.borrow());

        let dx = cursor.x - start_mouse.x;
        let dy = cursor.y - start_mouse.y;
        let new_x = start_window.0 + dx;
        let new_y = start_window.1 + dy;

        let _ = unsafe { SetWindowPos(hwnd, HWND(0), new_x, new_y, 0, 0, SWP_NOSIZE | SWP_NOZORDER) };
    }

        // ─── 停止拖动 ───
        if !is_mouse_button_down(MouseButton::Left) {
            DRAGGING.with(|cell| *cell.borrow_mut() = false);
        }
    

    // ─── 背景 ───
    draw_rectangle(0.0, 0.0, win_w, win_h, BG);

    // ─── 标题栏 ───
    draw_rectangle(0.0, 0.0, win_w, TITLE_H, TITLE_BG);

    // 标题文字
    draw_text_ex("PythonWallpaper", 20.0, 30.0, TextParams {
        font: Some(font),
        font_size: FONT_SIZE,
        color: WHITE,
        ..Default::default()
    });

    // 关闭按钮
    let close_x = win_w - CLOSE_BTN_WIDTH;
    draw_text_ex("×", close_x, 32.0, TextParams {
        font: Some(font),
        font_size: 28,
        color: CLOSE_COLOR,
        ..Default::default()
    });

    if is_mouse_button_pressed(MouseButton::Left) {
        let (mx, my) = mouse_position();
        if mx > close_x && my < TITLE_H {
            let _ = tx.send(UiCommand::Hide);
            return;
        }
    }

    // ─── 内容区域 ───
    let content_x = PADDING_X;
    let content_y = TITLE_H + PADDING_Y;
    let content_w = win_w - PADDING_X * 2.0;

    // 文本换行
    let lines = wrap_cn_text(text, font, FONT_SIZE, content_w);
    let total_h = lines.len() as f32 * LINE_H;

    // 鼠标滚轮
    let wheel = mouse_wheel().1;
    if wheel != 0.0 {
        *scroll -= wheel * 1.5;
    }

    let visible_h = win_h - TITLE_H - 30.0;
    let max_scroll = (total_h - visible_h).max(0.0);
    *scroll = scroll.clamp(0.0, max_scroll);

    // 绘制文本行
    let mut y = content_y - *scroll;
    let bottom_clip = win_h - 20.0;
    for line in &lines {
        if y > TITLE_H && y < bottom_clip {
            draw_text_ex(line, content_x, y, TextParams {
                font: Some(font),
                font_size: FONT_SIZE,
                color: TEXT_COLOR,
                ..Default::default()
            });
        }
        y += LINE_H;
    }

    // ─── 滚动条 ───
    if total_h > visible_h {
        let bar_x = win_w - SCROLLBAR_MARGIN;
        let bar_h = visible_h;

        // 滚动条背景
        draw_rectangle(bar_x, TITLE_H, SCROLLBAR_WIDTH, bar_h, SCROLLBAR_BG);

        // 滑块
        let ratio = (bar_h / total_h).min(1.0);
        let mut slider_h = bar_h * ratio;
        if slider_h < 20.0 { slider_h = 20.0; }
        let slider_y = TITLE_H + (*scroll / max_scroll) * (bar_h - slider_h);

        draw_rectangle(bar_x, slider_y, SCROLLBAR_WIDTH, slider_h, SCROLLBAR_THUMB);

        // 拖动滚动条
        if is_mouse_button_down(MouseButton::Left) {
            let (mx, my) = mouse_position();
            if mx > bar_x - 10.0 && mx < bar_x + SCROLLBAR_WIDTH + 2.0 {
                let percent = ((my - TITLE_H - slider_h / 2.0) / (bar_h - slider_h)).clamp(0.0, 1.0);
                *scroll = percent * max_scroll;
            }
        }
    }

    // ─── 底部版本信息 ───
    draw_text_ex("Rust + Macroquad", 20.0, win_h - 15.0, TextParams {
        font: Some(font),
        font_size: 16,
        color: GRAY,
        ..Default::default()
    });
}

async fn ui_loop(rx:Receiver<UiCommand>, tx: Sender<UiCommand>,) {
    make_borderless();
    hide_window();
    let font = load_ttf_font(FONT_PATH)
        .await
        .unwrap();

    let mut cmd_to_execute: Option<UiCommand> = None;
    let mut about_scrool: f32 = 0.0;
    loop {
        clear_background(Color::from_rgba(30, 30, 30, 255));
        // 一次性收走所有待处理命令，只保留最后一条
        while let Ok(cmd) = rx.try_recv() {
            cmd_to_execute = Some(cmd);
        }

        if let Some(ref cmd) = cmd_to_execute {
            match cmd {
                UiCommand::ShowAbout(t) => {
                    draw_about(&font, &t, &tx, &mut about_scrool);
                    show_window();
                }
                UiCommand::Hide => {
                    hide_window();
                    cmd_to_execute = None
                }
                UiCommand::Exit => break,
            }
        }

        next_frame().await;
    }
}

pub fn start_ui_thread() -> Sender<UiCommand> {
    let (tx,rx)=std::sync::mpsc::channel();

    if UI_RUNNING.swap(true, Ordering::SeqCst) { return tx; }

    let tx_clone = tx.clone();

    std::thread::spawn(move || {
        macroquad::Window::from_config(
            Conf {
                window_title:
                    "关于 PythonWallpaper".into(),
                window_width:800,
                window_height:600,
                window_resizable:true,
                fullscreen:false,
                ..Default::default()
            },
            
            async move {
                ui_loop(rx, tx_clone).await;
            }
        );
    });

    tx
}