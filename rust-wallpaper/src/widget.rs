use macroquad::prelude::*;
use macroquad::input::{get_char_pressed, is_key_pressed, KeyCode};
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::UI::WindowsAndMessaging::{
    SetWindowPos, GetWindowRect, GetCursorPos,
    SWP_NOSIZE, SWP_NOZORDER,
};

// 颜色常量（可被外部覆盖）
pub const BG: Color = Color::from_rgba(30, 30, 30, 255);
pub const TITLE_BG: Color = Color::from_rgba(16, 58, 143, 255);
pub const SCROLLBAR_BG: Color = Color::from_rgba(70, 70, 70, 180);
pub const SCROLLBAR_THUMB: Color = Color::from_rgba(160, 160, 160, 220);
pub const TEXT_COLOR: Color = Color::from_rgba(131, 169, 230, 255);
pub const TEXT_COLOR_GREEN: Color = Color::from_rgba(131, 169, 230, 255);
pub const CLOSE_COLOR: Color = TEXT_COLOR;

// 尺寸常量
pub const TITLE_H: f32 = 45.0;
pub const LINE_H: f32 = 32.0;
pub const PADDING_X: f32 = 35.0;
pub const PADDING_Y: f32 = 20.0;
pub const SCROLLBAR_WIDTH: f32 = 8.0;
pub const SCROLLBAR_MARGIN: f32 = 18.0;
pub const CLOSE_BTN_WIDTH: f32 = 40.0;
pub const FONT_SIZE: u16 = 22;

/// 窗口拖动状态（由外部持有）
#[derive(Default)]
pub struct TitleBarDragState {
    pub dragging: bool,
    pub drag_start_mouse: POINT,
    pub drag_start_window: (i32, i32),
}

/// 绘制自定义标题栏并处理拖动逻辑。
/// 返回 `true` 表示用户点击了关闭按钮。
/// 所有输入均为外部提供，不依赖任何全局状态。
pub fn draw_title_bar(
    font: &Font,
    title: &str,
    win_w: f32,
    hwnd: HWND,
    state: &mut TitleBarDragState,
) -> bool {
    let close_x = win_w - CLOSE_BTN_WIDTH;
    let (mx, my) = mouse_position();

    // 开始拖动
    if is_mouse_button_pressed(MouseButton::Left) && my < TITLE_H && mx < close_x {
        state.dragging = true;
        unsafe {
            let mut cursor = POINT::default();
            let _ = GetCursorPos(&mut cursor);
            state.drag_start_mouse = cursor;

            let mut rect = RECT::default();
            let _ = GetWindowRect(hwnd, &mut rect);
            state.drag_start_window = (rect.left, rect.top);
        }
    }

    // 拖动中
    if is_mouse_button_down(MouseButton::Left) && state.dragging {
        unsafe {
            let mut cursor = POINT::default();
            let _ = GetCursorPos(&mut cursor);
            let dx = cursor.x - state.drag_start_mouse.x;
            let dy = cursor.y - state.drag_start_mouse.y;
            let _ = SetWindowPos(
                hwnd,
                HWND(0),
                state.drag_start_window.0 + dx,
                state.drag_start_window.1 + dy,
                0, 0,
                SWP_NOSIZE | SWP_NOZORDER,
            );
        }
    } else {
        state.dragging = false;
    }

    // 绘制
    draw_rectangle(0.0, 0.0, win_w, TITLE_H, TITLE_BG);
    draw_text_ex(title, 20.0, 30.0, TextParams {
        font: Some(font),
        font_size: FONT_SIZE,
        color: TEXT_COLOR,
        ..Default::default()
    });
    draw_text_ex("×", close_x, 32.0, TextParams {
        font: Some(font),
        font_size: 28,
        color: CLOSE_COLOR,
        ..Default::default()
    });

    // 检查关闭按钮点击
    if is_mouse_button_pressed(MouseButton::Left) {
        let (mx_btn, my_btn) = mouse_position();
        if mx_btn > close_x && my_btn < TITLE_H {
            return true;
        }
    }
    false
}

/// 绘制滚动条（位置与尺寸由参数指定）。
/// 返回新的滚动值（如果用户正在拖动），否则返回 `None`。
pub fn draw_scrollbar_at(
    bar_x: f32,
    bar_y: f32,
    bar_h: f32,
    total_height: f32,
    max_scroll: f32,
    scroll: f32,
) -> Option<f32> {
    draw_rectangle(bar_x, bar_y, SCROLLBAR_WIDTH, bar_h, SCROLLBAR_BG);
    let ratio = (bar_h / total_height).min(1.0);
    let mut slider_h = bar_h * ratio;
    if slider_h < 20.0 { slider_h = 20.0; }
    let slider_y = bar_y + (scroll / max_scroll) * (bar_h - slider_h);
    draw_rectangle(bar_x, slider_y, SCROLLBAR_WIDTH, slider_h, SCROLLBAR_THUMB);

    if is_mouse_button_down(MouseButton::Left) {
        let (mx, my) = mouse_position();
        if mx > bar_x - 10.0 && mx < bar_x + SCROLLBAR_WIDTH + 2.0 {
            let percent = ((my - bar_y - slider_h / 2.0) / (bar_h - slider_h)).clamp(0.0, 1.0);
            return Some(percent * max_scroll);
        }
    }
    None
}

/// 绘制一个单行文本输入框，返回新输入内容
/// `text`: 当前文本
/// `cursor_pos`: 游标位置（字节索引）
/// `focused`: 是否获得焦点
/// 返回 `(new_text, new_cursor_pos)` 如果用户操作了，否则原样返回
pub fn draw_text_input(
    font: &Font,
    x: f32,
    y: f32,
    width: f32,
    text: &mut String,
    cursor_pos: &mut usize,
    focused: bool,
) {
    let height = 30.0;
    // 背景
    draw_rectangle(x, y, width, height, if focused { Color::from_rgba(60, 60, 60, 255) } else { Color::from_rgba(50, 50, 50, 255) });
    // 文本
    draw_text_ex(text.clone(), x + 5.0, y + height / 2.0 + FONT_SIZE as f32 * 0.3, TextParams {
        font: Some(font),
        font_size: FONT_SIZE,
        color: WHITE,
        ..Default::default()
    });
    // 游标 (如果聚焦)
    if focused {
        let text_before_cursor = &text[..*cursor_pos];
        let cursor_x = x + 5.0 + measure_text(text_before_cursor, Some(font), FONT_SIZE, 1.0).width;
        draw_line(cursor_x, y + 5.0, cursor_x, y + height - 5.0, 2.0, WHITE);
    }

    if focused {
        // 接收键盘输入
        while let Some(c) = get_char_pressed() {
            if c == '\u{8}' { // backspace
                if *cursor_pos > 0 {
                    text.remove(*cursor_pos - 1);
                    *cursor_pos -= 1;
                }
            } else if c == '\u{7f}' { // delete
                if *cursor_pos < text.len() {
                    text.remove(*cursor_pos);
                }
            } else if c == '\r' || c == '\n' {
                // 回车暂不做处理（可触发确定动作，由调用者处理）
            } else if c.is_ascii_graphic() || c == ' ' {
                text.insert(*cursor_pos, c);
                *cursor_pos += 1;
            }
        }
        // 左右方向键移动游标
        if is_key_pressed(KeyCode::Left) && *cursor_pos > 0 {
            *cursor_pos -= 1;
        }
        if is_key_pressed(KeyCode::Right) && *cursor_pos < text.len() {
            *cursor_pos += 1;
        }
        // Home / End
        if is_key_pressed(KeyCode::Home) {
            *cursor_pos = 0;
        }
        if is_key_pressed(KeyCode::End) {
            *cursor_pos = text.len();
        }
    }
}