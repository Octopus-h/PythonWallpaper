//! WorkerW 桌面嵌入模块
//! 提供将任意窗口嵌入桌面底层（WorkerW/Progman）的功能。

use std::thread;
use std::time::Duration;

use log::{error, info, warn};
use windows::{
    core::*,
    Win32::{
        Foundation::*,
        UI::{
            WindowsAndMessaging::*,
        },
    },
};

// ---- 常量 ----
const WS_EX_NOREDIRECTIONBITMAP: i32 = 0x00200000;
const WS_EX_LAYERED: i32 = 0x00080000;

// ---- 获取 WorkerW ----
pub fn get_workerw() -> HWND {
    let progman = unsafe {
        // SAFETY: FindWindowW 接受一个类名和一个窗口名，如果传入 NULL（这里是 None），
        // 则查找任意顶级窗口。我们传入 "Progman" 类名，这个类名是 Windows 桌面窗口的类名，
        // 总是存在的。返回的 HWND 可能为 0 表示未找到，我们随后检查并处理。
        FindWindowW(w!("Progman"), None)
    };
    if progman.0 == 0 {
        error!("未找到 Progman 窗口");
        return HWND(0);
    }
    unsafe {
        // SAFETY: 向 Progman 窗口发送 0x052C 消息以触发 WorkerW 创建。
        // 该消息是 Windows 内部使用的，已知不会产生副作用，且我们传入的 HWND 是有效的。
        SendMessageTimeoutW(
            progman,
            0x052C,
            None,
            None,
            SMTO_NORMAL,
            1000,
            None,
        );
    }

    let mut found = HWND(0);
    unsafe {
        // SAFETY: EnumWindows 枚举所有顶级窗口，并调用回调函数 enum_windows_proc。
        // 我们传递了 found 的地址作为 LPARAM，该地址在回调执行期间是有效的（因为 found 在栈上，
        // 且在 EnumWindows 返回前不会释放）。回调函数只会在当前线程同步调用，不会有数据竞争。
        // enum_windows_proc 是一个安全的 FFI 回调，它只读取窗口类名并可能修改 found，
        // 修改是安全的因为它是我们自己的地址，且只被该回调使用。
        let _ = EnumWindows(Some(enum_windows_proc), LPARAM(&mut found as *mut _ as isize));
    }
    found
}

/// 枚举窗口的回调函数，用于查找父窗口为 Progman 的 WorkerW 窗口。
/// 这是 `EnumWindows` 的回调，必须具有 `extern "system"` 签名。
/// 整体函数是 unsafe 的，因为其调用者（EnumWindows）要求满足特定合约，但我们对传入的参数有约束。
unsafe extern "system" fn enum_windows_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
    // SAFETY: lparam 是我们传入的 `&mut found` 的地址，类型是 *mut HWND，保证在回调执行期间有效。
    // 由于 EnumWindows 是同步调用，且回调在本线程执行，不存在并发问题。
    let p_found = lparam.0 as *mut HWND;

    let mut class = [0u16; 256];
    // SAFETY: GetClassNameW 要求传入有效的 HWND 和足够大小的缓冲区。
    // hwnd 来自 EnumWindows，必然是有效的顶层窗口句柄；缓冲区大小 256 足够容纳类名。
    let len = unsafe { GetClassNameW(hwnd, &mut class) };
    if len == 0 {
        return TRUE;
    }
    // String::from_utf16_lossy 是安全的，它处理无效 UTF-16 序列，不会导致未定义行为。
    let class_name = String::from_utf16_lossy(&class[..len as usize]);
    if class_name != "WorkerW" {
        return TRUE;
    }

    // SAFETY: GetParent 接受有效的 HWND，返回父窗口句柄或 NULL。
    let parent = unsafe { GetParent(hwnd) };
    if parent.0 == 0 {
        return TRUE;
    }

    let mut parent_class = [0u16; 256];
    // SAFETY: 与上述相同，parent 有效，缓冲区足够。
    let len2 = unsafe { GetClassNameW(parent, &mut parent_class) };
    if len2 > 0 && String::from_utf16_lossy(&parent_class[..len2 as usize]) == "Progman" {
        // SAFETY: p_found 是有效的可写指针，我们写入 HWND 值，所有权不转移。
        unsafe { *p_found = hwnd };
        return FALSE;
    }
    TRUE
}

// ---- 嵌入窗口到桌面 ----
pub fn set_windows_to_workerw(hwnd: HWND) -> bool {
    // 1. 查找 Progman
    let progman = unsafe {
        // SAFETY: FindWindowW 是标准 API，传入固定类名，如果失败返回 NULL，我们立即检查。
        FindWindowW(w!("Progman"), None)
    };
    if progman.0 == 0 {
        error!("未找到 Progman 窗口");
        return false;
    }

    // 2. 获取 Progman 的扩展样式（用于判断是否为 Win11 24H2 新模式）
    let desktop_ex_style = unsafe {
        // SAFETY: progman 是有效窗口句柄，GWL_EXSTYLE 是合法索引。
        GetWindowLongW(progman, GWL_EXSTYLE)
    };
    let is_raised_desktop = (desktop_ex_style & WS_EX_NOREDIRECTIONBITMAP) != 0;

    // 3. 验证目标窗口有效性
    if hwnd.0 == 0 {
        error!("无效窗口句柄，{}", hwnd.0);
        return false;
    }
    // SAFETY: IsWindow 检查句柄是否有效，无效时返回 FALSE，我们立即处理。
    if unsafe { IsWindow(hwnd).as_bool() } == false {
        error!("IsWindow：无效窗口句柄，{}", hwnd.0);
        return false;
    }

    // 4. 获取 WorkerW（可能不存在）
    let workerw = get_workerw(); // 此函数内部已封装安全性

    // 5. 根据模式执行不同的嵌入策略
    if is_raised_desktop {
        info!("检测到 Windows 11 24H2 新模式，使用适配嵌入");

        // 查找 SHELLDLL_DefView 子窗口
        let shell_defview = unsafe {
            // SAFETY: FindWindowExW 要求 progman 有效，子类名已知，可能返回 NULL。
            FindWindowExW(progman, None, w!("SHELLDLL_DefView"), None)
        };
        if shell_defview.0 == 0 {
            error!("未找到 SHELLDLL_DefView");
            return false;
        }
        if workerw.0 != 0 {
            info!("找到 WorkerW 子窗口，将置于底层");
        }

        // 设置窗口扩展样式（分层）
        unsafe {
            let mut ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE);
            ex_style |= WS_EX_LAYERED;
            // SAFETY: 设置窗口样式，hwnd 有效，样式值合法。
            SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style);
            // SAFETY: 设置分层属性，颜色值 0，透明度 255，标志 LWA_ALPHA。
            let _ = SetLayeredWindowAttributes(hwnd, COLORREF(0), 255, LWA_ALPHA);
        }

        // 父窗口设为 Progman
        unsafe {
            // SAFETY: SetParent 需要两个有效句柄，hwnd 和 progman 均有效。
            SetParent(hwnd, progman);
        }

        // 调整 Z 序：置于 SHELLDLL_DefView 之下
        unsafe {
            // SAFETY: SetWindowPos 参数正确，hwnd 有效，flags 合理。
            let _ = SetWindowPos(hwnd, shell_defview, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }

        if workerw.0 != 0 {
            unsafe {
                // SAFETY: 将 WorkerW 置于 Z 序最底层。
                let _ = SetWindowPos(workerw, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            }
        }
    } else {
        // 传统模式：直接嵌入 WorkerW
        if workerw.0 == 0 {
            error!("未找到 WorkerW");
            return false;
        }
        unsafe {
            // SAFETY: SetParent 需要两个有效句柄。
            SetParent(hwnd, workerw);
        }
    }

    // 修改窗口样式
    unsafe {
        let mut style = GetWindowLongW(hwnd, GWL_STYLE);
        style |= (WS_CHILD | WS_VISIBLE).0 as i32;
        SetWindowLongW(hwnd, GWL_STYLE, style);
    }

    unsafe {
        let mut ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE);
        ex_style &= !((WS_EX_DLGMODALFRAME | WS_EX_WINDOWEDGE).0 as i32);
        SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style);
    }

    // 获取屏幕尺寸并调整窗口位置大小
    let screen_w = unsafe { GetSystemMetrics(SM_CXSCREEN) };
    let screen_h = unsafe { GetSystemMetrics(SM_CYSCREEN) };
    unsafe {
        // SAFETY: SetWindowPos 将窗口设为全屏，hwnd 有效，flags 正确。
        let _ = SetWindowPos(hwnd, None, 0, 0, screen_w, screen_h, SWP_NOZORDER | SWP_FRAMECHANGED);
        // SAFETY: ShowWindow 显示窗口，hwnd 有效。
        ShowWindow(hwnd, SW_SHOW);
    }

    info!("窗口嵌入成功，尺寸：{}x{}", screen_w, screen_h);
    true
}

/// 尝试多次嵌入，成功返回窗口句柄，否则返回 0
pub fn embed_to_workerw(target: HWND) -> HWND {
    for attempt in 0..20 {
        if set_windows_to_workerw(target) {
            info!("窗口已嵌入 WorkerW");
            return target;
        }
        warn!("第 {} 次嵌入失败，重试...", attempt + 1);
        thread::sleep(Duration::from_millis(50));
    }
    error!("嵌入失败");
    HWND(0)
}