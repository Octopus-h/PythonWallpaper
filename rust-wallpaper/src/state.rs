use std::process::Child;
use std::sync::{
    atomic::{AtomicBool, AtomicIsize, Ordering},
    Mutex,
};
use std::thread;

/// 壁纸类型
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum WallpaperType {
    Py,
    Exe,
    Video,
    Nil,
}

/// 统一的应用状态对象
///
/// 目的：
/// 1. 把原先分散在多个 Atomic / Mutex 中的状态归并到一个对象
/// 2. 让跨线程共享状态更清晰，便于后续扩展和维护
/// 3. 减少“状态分散导致的竞态和定位困难”
pub struct AppState {
    /// 程序是否运行
    pub running: AtomicBool,

    /// 当前壁纸类型
    pub wallpaper_type: AtomicIsize,

    /// 当前壁纸窗口句柄
    pub wallpaper_hwnd: AtomicIsize,

    /// 输入钩子线程是否在跑
    pub hook_thread_running: AtomicBool,

    /// 钩子线程持有句柄
    pub hook_thread_handle: Mutex<Option<thread::JoinHandle<()>>>,

    /// 鼠标/键盘 hook 句柄
    pub mouse_hook: AtomicIsize,
    pub keyboard_hook: AtomicIsize,

    /// 最近鼠标动作时间
    pub last_move_time: Mutex<u64>,

    /// 当前子进程
    pub current_child: Mutex<Option<Child>>,

    /// 关于/说明文本缓存
    pub info_text: Mutex<String>,
}

unsafe impl Send for AppState {}
unsafe impl Sync for AppState {}

lazy_static::lazy_static! {
    pub static ref STATE: AppState = AppState {
        running: AtomicBool::new(true),
        wallpaper_type: AtomicIsize::new(WallpaperType::Nil as isize),
        wallpaper_hwnd: AtomicIsize::new(0),
        hook_thread_running: AtomicBool::new(false),
        hook_thread_handle: Mutex::new(None),
        mouse_hook: AtomicIsize::new(0),
        keyboard_hook: AtomicIsize::new(0),
        last_move_time: Mutex::new(0),
        current_child: Mutex::new(None),
        info_text: Mutex::new(String::new()),
    };
}

/// 便捷读取: 当前壁纸类型
impl AppState {
    pub fn current_wallpaper_type(&self) -> WallpaperType {
        match self.wallpaper_type.load(Ordering::Relaxed) {
            x if x == WallpaperType::Py as isize => WallpaperType::Py,
            x if x == WallpaperType::Exe as isize => WallpaperType::Exe,
            x if x == WallpaperType::Video as isize => WallpaperType::Video,
            _ => WallpaperType::Nil,
        }
    }

    pub fn current_wallpaper_hwnd(&self) -> isize {
        self.wallpaper_hwnd.load(Ordering::Relaxed)
    }
}