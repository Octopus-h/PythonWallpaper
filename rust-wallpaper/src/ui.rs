use macroquad::prelude::*;
use windows::Win32::Foundation::{HWND};
use windows::Win32::UI::WindowsAndMessaging::{
    ShowWindow,
    SW_HIDE,
    SW_SHOW,
    FindWindowW,
    GWL_EXSTYLE, GWL_STYLE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED,
    SetWindowLongPtrW, SetWindowPos,
};
use windows::core::*;
use std::sync::{
    atomic::{AtomicBool, Ordering},
};
use std::cell::RefCell;

use crossbeam_channel::{Sender, Receiver, bounded};

use crate::widget::*;

pub enum UiCommand {
    ShowAbout(String),
    ShowError {
        title: String,
        message: String,
    },
    ShowSettings,
    Hide,
    Exit,
}

static UI_RUNNING: AtomicBool = AtomicBool::new(false);
const FONT_PATH: &str = "resources/LXGWWenKaiMonoLite-Medium.ttf";
const FOUND_BUG_PNG: &str = "resources/icons/found_bug.png";

thread_local! {
    static CACHED_LINES: RefCell<Option<(String, Vec<String>)>> = const { RefCell::new(None) };
}

#[cfg(target_os="windows")]
fn get_hwnd() -> Option<HWND> {
    let hwnd = unsafe{ FindWindowW(None, w!("PythonWallpaperWindow")) };
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

/// 绘制关于窗口，返回是否点击了关闭按钮（`bool`）
fn draw_about(
    font: &Font,
    text: &str,
    win_w: f32,
    win_h: f32,
    hwnd: HWND,
    drag_state: &mut TitleBarDragState,
    scroll: &mut f32,
) -> bool {
    // 背景
    draw_rectangle(0.0, 0.0, win_w, win_h, BG);

    // 标题栏
    let close_clicked = draw_title_bar(font, "PythonWallpaper", win_w, hwnd, drag_state);
    if close_clicked {
        return true;
    }

    // 内容区域
    let content_x = PADDING_X;
    let content_y = TITLE_H + PADDING_Y;
    let content_w = win_w - PADDING_X * 2.0;
    let lines = wrap_cn_text(text, font, FONT_SIZE, content_w);
    let total_h = lines.len() as f32 * LINE_H;

    // 滚轮
    let wheel = mouse_wheel().1;
    if wheel != 0.0 { *scroll -= wheel * 1.5; }

    let visible_h = win_h - TITLE_H - 30.0;
    let max_scroll = (total_h - visible_h).max(0.0);
    *scroll = scroll.clamp(0.0, max_scroll);

    // 绘制文本
    let clip_top = TITLE_H + 5.0;  // 留出5像素空白，避免紧贴标题栏
    let bottom_clip = win_h - 20.0;
    let mut y = content_y - *scroll;
    for line in &lines {
        let line_top = y - FONT_SIZE as f32; // 文字顶部大致位置
        let line_bottom = y + LINE_H * 0.3;   // 文字底部（descender部分）
        if line_top > clip_top && line_bottom < bottom_clip {
            draw_text_ex(line, content_x, y, TextParams {
                font: Some(font),
                font_size: FONT_SIZE,
                color: TEXT_COLOR,
                ..Default::default()
            });
        }
        y += LINE_H;
    }

    // 滚动条
    if total_h > visible_h {
        if let Some(new_scroll) = draw_scrollbar_at(
            win_w - SCROLLBAR_MARGIN,
            TITLE_H,
            visible_h,
            total_h,
            max_scroll,
            *scroll,
        ) {
            *scroll = new_scroll;
        }
    }

    // 底部版本
    draw_text_ex("Rust + Macroquad", 20.0, win_h - 15.0, TextParams {
        font: Some(font),
        font_size: 16,
        color: GRAY,
        ..Default::default()
    });

    false
}

/// 绘制错误窗口，返回是否点击了关闭按钮（`bool`）
fn draw_error(
    font: &Font,
    icon: &Texture2D,
    title: &str,
    message: &str,
    win_w: f32,
    win_h: f32,
    hwnd: HWND,
    drag_state: &mut TitleBarDragState,
    scroll: &mut f32,
) -> bool {
    draw_rectangle(0.0, 0.0, win_w, win_h, BG);

    let close_clicked = draw_title_bar(font, "不好，程序里冒出一只Bug",
                                            win_w, hwnd, drag_state);
    if close_clicked {
        return true;
    }

    let content_y = TITLE_H + PADDING_Y;
    let content_h = win_h - TITLE_H - PADDING_Y - 20.0;
    let left_padding = PADDING_X;
    let gap = 20.0;

    // 左侧图标：竖直填充
    let icon_height = content_h - 40.0;
    let icon_width = icon.width() * icon_height / icon.height();
    draw_texture_ex(
        icon,
        left_padding,
        content_y,
        WHITE,
        DrawTextureParams {
            dest_size: Some(Vec2::new(icon_width, icon_height)),
            ..Default::default()
        },
    );

    let text_x = left_padding + icon_width + gap;
    let text_max_w = win_w - text_x - PADDING_X;

    // 标题
    let title_size = measure_text(title, Some(font), 26, 1.0);
    draw_text_ex(title, text_x, content_y, TextParams {
        font: Some(font), font_size: 26, color: TEXT_COLOR, ..Default::default()
    });

    // 消息
    let msg_y = content_y + title_size.height + 10.0;
    let msg_area_h = content_h - title_size.height - 10.0;
    let lines = wrap_cn_text(message, font, FONT_SIZE, text_max_w);
    let total_text_h = lines.len() as f32 * LINE_H;

    let wheel = mouse_wheel().1;
    if wheel != 0.0 { *scroll -= wheel * 1.5; }
    let max_scroll = (total_text_h - msg_area_h).max(0.0);
    *scroll = scroll.clamp(0.0, max_scroll);

    let clip_top = msg_y; // 直接用 msg_y，因为上面还有标题，已经安全
    let clip_bottom = content_y + content_h;
    let mut y = msg_y - *scroll;
    for line in &lines {
        let line_top = y - FONT_SIZE as f32;
        let line_bottom = y + LINE_H * 0.3;
        if line_top > clip_top && line_bottom < clip_bottom {
            draw_text_ex(line, text_x, y, TextParams {
                font: Some(font),
                font_size: FONT_SIZE,
                color: TEXT_COLOR,
                ..Default::default()
            });
        }
        y += LINE_H;
    }

    if total_text_h > msg_area_h {
        if let Some(new_scroll) = draw_scrollbar_at(
            win_w - SCROLLBAR_MARGIN,
            msg_y,
            msg_area_h,
            total_text_h,
            max_scroll,
            *scroll,
        ) {
            *scroll = new_scroll;
        }
    }

    draw_text_ex("Rust + Macroquad [lastlog.log内查找更多]", 20.0, win_h - 15.0, TextParams {
        font: Some(font),
        font_size: 20,
        color: TEXT_COLOR_GREEN,
        ..Default::default()
    });

    false
}

fn draw_settings(
    font: &Font,
    win_w: f32,
    win_h: f32,
    hwnd: HWND,
    drag_state: &mut TitleBarDragState,
    cursor_pos: &mut usize,
    scroll: &mut f32,
) -> bool {
    draw_rectangle(0.0, 0.0, win_w, win_h, BG);

    let close_clicked = draw_title_bar(font, "设置", win_w, hwnd, drag_state);
    if close_clicked {
        return true;
    }

    let left = PADDING_X;
    let y_start = TITLE_H + 20.0;
    let label_color = LIGHTGRAY;
    let input_width = win_w - PADDING_X * 2.0 - 140.0; // 留出按钮空间

    // 标签
    draw_text_ex("Python 解释器路径：", left, y_start + 20.0, TextParams {
        font: Some(font), font_size: FONT_SIZE, color: label_color, ..Default::default()
    });

    // 输入框
    draw_text_input(font, left, y_start + 40.0,
        input_width, &mut "".to_string(),
        cursor_pos, true,
    );

    draw_text_ex("Rust + Macroquad", 20.0, win_h - 15.0, TextParams {
        font: Some(font),
        font_size: 20,
        color: TEXT_COLOR_GREEN,
        ..Default::default()
    });

    false
}

async fn ui_loop(rx: Receiver<UiCommand>, tx: Sender<UiCommand>) {
    make_borderless();
    hide_window();

    let font = load_ttf_font(FONT_PATH).await.unwrap();
    let error_icon = load_texture(FOUND_BUG_PNG).await.unwrap();

    let mut cmd_to_execute: Option<UiCommand> = None;
    let mut about_scroll = 0.0f32;
    let mut error_scroll = 0.0f32;
    let mut settings_scroll = 0.0f32;
    let mut settings_cursor: usize = 0;
    let mut drag_state = TitleBarDragState::default();

    loop {
        if is_quit_requested() {
            prevent_quit();
            hide_window();
            cmd_to_execute = None;
        }

        clear_background(Color::from_rgba(30, 30, 30, 255));

        // 接收命令
        if let Ok(cmd) = rx.try_recv() {
            cmd_to_execute = Some(cmd);
        }

        let (win_w, win_h) = (screen_width(), screen_height());
        let hwnd = get_hwnd().unwrap_or(HWND(0));

        // 处理当前命令
        if let Some(ref cmd) = cmd_to_execute {
            match cmd {
                UiCommand::ShowAbout(t) => {
                    if draw_about(&font, t, win_w, win_h, hwnd, &mut drag_state, &mut about_scroll) {
                        // 用户点击了关闭按钮
                        hide_window();
                        cmd_to_execute = None;
                    } else {
                        show_window();
                    }
                },
                UiCommand::ShowError { title, message } => {
                    // 日志记录由外部负责
                    if draw_error(&font, &error_icon, title, message,
                                  win_w, win_h, hwnd,
                                  &mut drag_state, &mut error_scroll) {
                        hide_window();
                        cmd_to_execute = None;
                    } else {
                        show_window();
                    }
                },
                UiCommand::ShowSettings  => {
                    if draw_settings(&font, win_w, win_h, hwnd, &mut drag_state,
                        &mut settings_cursor, &mut settings_scroll) {
                        // 用户点击了关闭按钮
                        hide_window();
                        cmd_to_execute = None;
                    } else {
                        show_window();
                    }
                },
                UiCommand::Hide => {
                    hide_window();
                    cmd_to_execute = None; // 清空命令，避免下一帧重复执行
                },
                UiCommand::Exit => break,
            }
        }

        next_frame().await;
    }
}

pub fn start_ui_thread() -> Sender<UiCommand> {
    let (tx, rx) = bounded::<UiCommand>(10);
    // 或 unbounded()

    if UI_RUNNING.swap(true, Ordering::SeqCst) {
        return tx;
    }

    let tx_clone = tx.clone();

    std::thread::spawn(move || {
        macroquad::Window::from_config(
            Conf {
                window_title:
                    "PythonWallpaperWindow".into(),
                window_width:1000,
                window_height:750,
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