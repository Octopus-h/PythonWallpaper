//! 低级鼠标/键盘钩子模块（使用 Rust 线程实现）
//! 负责将全局鼠标/键盘事件转发给目标窗口（壁纸窗口）。

use std::sync::atomic::Ordering;
use std::thread;

use log::{error, info, warn};
use windows::{
    Win32::{
        Foundation::*,
        UI::{
            WindowsAndMessaging::*,
            Input::KeyboardAndMouse::*,
        },
        System::{
            SystemInformation::GetTickCount64,
            LibraryLoader::GetModuleHandleW,
        },
        Graphics::Gdi::MapWindowPoints,
    },
};

use crate::{STATE, WallpaperType};

// ---- 常量 ----
const LIMIT_MS: u64 = 60;
const ESCAPE_VK: u32 = 0x1B;

// ---- 鼠标事件转发 ----
fn forward_mouse_event(wparam: WPARAM, lparam: LPARAM, target_hwnd: HWND) {
    let wp = wparam.0 as u32;

    // 从 LPARAM 提取 MSLLHOOKSTRUCT
    let info = lparam.0 as *const MSLLHOOKSTRUCT;
    if info.is_null() {
        return;
    }

    // 读取结构体字段（解引用裸指针）
    let pt = unsafe { (*info).pt };
    let mouse_data = unsafe { (*info).mouseData };

    // ---- 限流 ----
    let now = unsafe { GetTickCount64() };
    let mut last_move = STATE.last_move_time.lock().unwrap();
    if wp == WM_MOUSEMOVE || wp == WM_MOUSEWHEEL || wp == WM_MOUSEHWHEEL {
        if now - *last_move < LIMIT_MS {
            return;
        }
        *last_move = now;
    }
    drop(last_move);

    // ---- 坐标转换 ----
    let pt_win = POINT { x: pt.x, y: pt.y };
    unsafe {
        // SAFETY: MapWindowPoints 将屏幕坐标转为目标窗口客户区坐标。
        // HWND_DESKTOP 是常量，target_hwnd 由调用者保证有效。
        MapWindowPoints(HWND_DESKTOP, target_hwnd, &mut [pt_win]);
    }
    let lparam_msg = ((pt_win.y << 16) | (pt_win.x & 0xFFFF)) as isize;

    // ---- 发送鼠标移动消息 ----
    unsafe {
        // SAFETY: PostMessageW 异步发送消息，target_hwnd 有效，参数合法。
        let _ = PostMessageW(target_hwnd, WM_MOUSEMOVE, WPARAM(0), LPARAM(lparam_msg));
    }

    // ---- 根据事件类型发送特定消息 ----
    let msg_id: u32 = match wp {
        WM_LBUTTONDOWN => WM_LBUTTONDOWN,
        WM_LBUTTONUP => WM_LBUTTONUP,
        WM_RBUTTONDOWN => WM_RBUTTONDOWN,
        WM_RBUTTONUP => WM_RBUTTONUP,
        WM_MBUTTONDOWN => WM_MBUTTONDOWN,
        WM_MBUTTONUP => WM_MBUTTONUP,
        WM_MOUSEWHEEL => WM_MOUSEWHEEL,
        WM_MOUSEHWHEEL => WM_MOUSEHWHEEL,
        _ => 0,
    };

    if msg_id != 0 {
        let wparam_msg = if msg_id == WM_MOUSEWHEEL || msg_id == WM_MOUSEHWHEEL {
            WPARAM((((mouse_data as u32) << 16) & 0xFFFF0000) as usize)
        } else {
            WPARAM(0)
        };
        unsafe {
            // SAFETY: 同上，发送合法消息到有效窗口。
            let _ = PostMessageW(target_hwnd, msg_id, wparam_msg, LPARAM(lparam_msg));
        }
    }
}

// ---- 键盘事件转发 ----
fn forward_keyboard_event(wparam: WPARAM, lparam: LPARAM, target_hwnd: HWND) {
    let wp = wparam.0 as u32;

    let info = lparam.0 as *const KBDLLHOOKSTRUCT;
    if info.is_null() {
        return;
    }

    let vk_code = unsafe { (*info).vkCode };
    let scan_code = unsafe { (*info).scanCode };
    let flags = unsafe { (*info).flags };

    let is_down = wp == WM_KEYDOWN || wp == WM_SYSKEYDOWN;
    let msg_id = if is_down { WM_KEYDOWN } else { WM_KEYUP };

    // 视频壁纸时屏蔽 ESC 键
    let wt = STATE.wallpaper_type.load(Ordering::Relaxed);
    if wt == WallpaperType::Video as isize && vk_code == ESCAPE_VK {
        return;
    }

    let mut lparam_msg: u32 = 1; // 重复计数
    lparam_msg |= (scan_code as u32) << 16;
    // 使用 .0 访问内部 u32 值
    if (flags.0 & LLKHF_EXTENDED.0) != 0 {
        lparam_msg |= 1 << 24;
    }
    // 检查 Alt 键是否按下
    if unsafe { GetKeyState(VK_MENU.0  as i32) < 0 } {
        lparam_msg |= 1 << 29;
    }
    if !is_down {
        lparam_msg |= 1 << 30;
        lparam_msg |= 1 << 31;
    }

    unsafe {
        // SAFETY: 发送键盘消息到有效窗口。
        let _ = PostMessageW(
            target_hwnd,
            msg_id,
            WPARAM(vk_code as usize),
            LPARAM(lparam_msg as isize),
        );
    }
}

// ---- 低级鼠标钩子回调 ----
unsafe extern "system" fn low_level_mouse_proc(ncode: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if ncode >= 0 {
        let target_hwnd = HWND(STATE.wallpaper_hwnd.load(Ordering::Relaxed) as isize);
        if target_hwnd.0 != 0 && IsWindow(target_hwnd).as_bool() {
            forward_mouse_event(wparam, lparam, target_hwnd);
        }
    }
    let mouse_hook = STATE.mouse_hook.load(Ordering::Relaxed);
    CallNextHookEx(HHOOK(mouse_hook as isize), ncode, wparam, lparam)
}

// ---- 低级键盘钩子回调 ----
unsafe extern "system" fn low_level_keyboard_proc(ncode: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if ncode >= 0 {
        let target_hwnd = HWND(STATE.wallpaper_hwnd.load(Ordering::Relaxed) as isize);
        if target_hwnd.0 != 0 && IsWindow(target_hwnd).as_bool() {
            forward_keyboard_event(wparam, lparam, target_hwnd);
        }
    }
    let keyboard_hook = STATE.keyboard_hook.load(Ordering::Relaxed);
    CallNextHookEx(HHOOK(keyboard_hook as isize), ncode, wparam, lparam)
}

// ---- 钩子线程（Rust 原生线程） ----
fn hook_thread_proc() {
    // 1. 安装钩子（unsafe 操作）
    let (mouse_hook, keyboard_hook) = unsafe {
        // SAFETY: GetModuleHandleW 获取当前模块句柄，始终成功（或返回 NULL，但 SetWindowsHookEx 会处理）。
        let hinst = GetModuleHandleW(None).unwrap_or_default();

        // SAFETY: SetWindowsHookExW 安装低级钩子，回调函数指针有效，线程 ID 为 0 表示全局钩子。
        // 这些操作是标准的 Windows 钩子安装流程，错误码会检查。
        let mouse = match SetWindowsHookExW(
            WH_MOUSE_LL,
            Some(low_level_mouse_proc),
            hinst,
            0,
        ) {
            Ok(v) => v,
            Err(e) => {
                error!("安装鼠标钩子失败: {}", e);
                return;
            }
        };
        let keyboard = match SetWindowsHookExW(
            WH_KEYBOARD_LL,
            Some(low_level_keyboard_proc),
            hinst,
            0,
        ) {
            Ok(v) => v,
            Err(e) => {
                error!("安装键盘钩子失败: {}", e);
                let _ = UnhookWindowsHookEx(mouse);
                return;
            }
        };
        (mouse, keyboard)
    };

    // 存储钩子句柄到全局状态
    STATE.mouse_hook.store(mouse_hook.0 as isize, Ordering::Relaxed);
    STATE.keyboard_hook.store(keyboard_hook.0 as isize, Ordering::Relaxed);
    STATE.hook_thread_running.store(true, Ordering::Relaxed);

    // 2. 消息循环（必须，钩子需要消息泵）
    // SAFETY: MSG 结构体是 POD（普通旧数据），全零初始化对所有字段都是有效的初始状态。
    // 后续会通过 PeekMessageW 填充有效数据。
    let mut msg: MSG = unsafe { std::mem::zeroed() };
    while STATE.hook_thread_running.load(Ordering::Relaxed) {
        unsafe {
            // SAFETY: MsgWaitForMultipleObjects 等待输入消息，无句柄等待，超时 10ms。
            // 参数正确，返回值为 WAIT_EVENT，后续会检查。
            let ret = MsgWaitForMultipleObjects(None, false, 10, QS_ALLINPUT);
            if ret == WAIT_OBJECT_0 {
                // SAFETY: PeekMessageW 从当前线程消息队列中提取消息，缓冲区足够。
                while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
                    if msg.message == WM_QUIT {
                        break;
                    }
                    // SAFETY: TranslateMessage 和 DispatchMessageW 需要合法的 MSG 结构，
                    // 消息来自 PeekMessageW，是有效的。
                    TranslateMessage(&msg);
                    DispatchMessageW(&msg);
                }
            } else if ret == WAIT_TIMEOUT {
                // 超时，继续循环检查退出标志
                continue;
            }
        }
        // 轻微 sleep 防止 CPU 空转（但 MsgWait 已经阻塞，无需额外 sleep）
    }

    // 3. 清理钩子
    unsafe {
        // SAFETY: 从全局状态取回钩子句柄，调用 UnhookWindowsHookEx 卸载钩子。
        let mh = HHOOK(STATE.mouse_hook.swap(0, Ordering::Relaxed) as isize);
        let kh = HHOOK(STATE.keyboard_hook.swap(0, Ordering::Relaxed) as isize);
        if !mh.is_invalid() {
            let _ = UnhookWindowsHookEx(mh);
        }
        if !kh.is_invalid() {
            let _ = UnhookWindowsHookEx(kh);
        }
    }
    info!("钩子线程已退出");
}

// ---- 启动钩子线程 ----
pub fn start_input_thread(target_hwnd: HWND) -> bool {
    // 设置目标窗口句柄
    STATE.wallpaper_hwnd.store(target_hwnd.0 as isize, Ordering::Relaxed);

    // 如果已有线程，先等待它结束
    {
        let mut handle = STATE.hook_thread_handle.lock().unwrap();
        if let Some(handle) = handle.take() {
            // 通知线程退出（如果还在运行）
            STATE.hook_thread_running.store(false, Ordering::Relaxed);
            // 等待线程结束
            let _ = handle.join();
        }
    }

    // 重置运行标志
    STATE.hook_thread_running.store(true, Ordering::Relaxed);

    // 启动新线程
    let join_handle = thread::spawn(|| {
        hook_thread_proc();
    });

    // 存储 JoinHandle
    *STATE.hook_thread_handle.lock().unwrap() = Some(join_handle);
    info!("钩子线程已启动");
    true
}

// ---- 停止钩子线程 ----
pub fn stop_input_thread() {
    // 通知线程退出
    STATE.hook_thread_running.store(false, Ordering::Relaxed);

    // 等待线程真正结束
    let mut handle = STATE.hook_thread_handle.lock().unwrap();
    if let Some(handle) = handle.take() {
        // 等待最多 2 秒（可选），这里直接 join，因为线程会响应 running 标志快速退出
        let _ = handle.join();
        info!("钩子线程已停止");
    }
}