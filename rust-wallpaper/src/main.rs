//! Rust 壁纸切换工具
//! 支持 Python 脚本、EXE、视频（ffplay）作为动态壁纸，
//! 并嵌入桌面底层（WorkerW），支持鼠标/键盘事件转发。

#![windows_subsystem = "windows"]  // 无控制台窗口（发布时可注释掉以调试）

mod worker_w; // 引入独立的 WorkerW 嵌入模块
mod hook;     // 引入钩子模块
mod ui;       // 引入 UI 模块（macroquad 关于窗口）

use std::{
    env, fs::{self, File}, io::{BufRead, BufReader}, os::windows::process::CommandExt, path::Path, process::{Child, Command, Stdio}, sync::{
        Mutex, atomic::{AtomicBool, AtomicIsize, Ordering},
    }, thread, time::{Duration, Instant},
};

use chrono::Local;
use crossbeam_channel::{Sender, bounded};
use log::{error, info, warn};
use serde_json::{Value, Map};
use simplelog::{Config, WriteLogger};
use ldtray::{Tray, TrayConfig, Icon, Menu, MenuItem};
use rfd::FileDialog;
use windows::{
    core::*,
    Win32::{
        Foundation::*,
        System::{
            Registry::*,
            Threading::*,
        },
        UI::{
            HiDpi::*,
            WindowsAndMessaging::*,
        },
    },
};

// ---- 常量 ----
const CONFIG_FILE: &str = "resources/config.json";
const FFPLAY_PATH: &str = "resources/ffmpeg/ffplay.exe";
const PY_ENV_PATH: &str = "resources/pyenv/pythonw.exe";
const ICON_PATH: &str = "resources/icons/icon.ico";
const INFO_TEXT_PATH: &str = "resources/text.toml";
const AUTO_START_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const APP_REGISTRY_NAME: &str = "PythonWallpaper";

// ---- 菜单 ID 结构 ----
struct MenuIds {
    autostart: u32,
    py: u32,
    exe: u32,
    vid: u32,
    about: u32,
    exit: u32,
}

// ---- 类型 ----
#[derive(Clone, Copy, PartialEq, Eq)]
enum WallpaperType {
    Py,
    Exe,
    Video,
    Nil,
}

// ---- 全局状态（线程安全） ----
pub struct AppState {
    pub running: AtomicBool,
    pub wallpaper_type: AtomicIsize,
    pub wallpaper_hwnd: AtomicIsize,
    pub hook_thread_running: AtomicBool,
    pub hook_thread_handle: Mutex<Option<thread::JoinHandle<()>>>,
    pub mouse_hook: AtomicIsize,
    pub keyboard_hook: AtomicIsize,
    pub last_move_time: Mutex<u64>,
    pub current_child: Mutex<Option<Child>>,
    pub info_text: Mutex<String>,
}

// 这些类型需要 Send + Sync，因为它们会被跨线程共享
unsafe impl Send for AppState {}
unsafe impl Sync for AppState {}
// ---- 托盘回调（通过通道发送 ID） ----
// 我们使用一个全局通道将菜单点击事件从托盘线程发送到主循环

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

// ---- 全局通道 ----
use std::sync::OnceLock;
static CMD_CHAN: OnceLock<Sender<(String, String, String)>> = OnceLock::new();

fn setup_panic_hook() {
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        // 获取 panic 信息
        let payload = panic_info.payload();
        let msg = if let Some(s) = payload.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = payload.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };

        let location = panic_info.location().map(|loc| format!("{}:{}", loc.file(), loc.line()))
            .unwrap_or_else(|| "unknown location".to_string());

        // 记录到日志
        error!("Panic occurred at {}: {}", location, msg);

        // 如果有 backtrace，记录
        let bt = std::backtrace::Backtrace::force_capture().to_string();
        if !bt.is_empty() {
            error!("Backtrace:\n{}", bt);
        }

        // 调用默认钩子（通常会输出到 stderr）
        default_hook(panic_info);
    }));
}

// ---- 日志初始化 ----
fn init_logging() {
    let log_file = "lastlog.log";
    // 日志轮转逻辑
    if Path::new(log_file).exists() {
        if let Ok(meta) = fs::metadata(log_file) {
            if meta.len() > 256 * 1024 {
                let _ = fs::rename(log_file, format!("{}.baka", log_file));
            }
        }
    }
    // 使用 WriteLogger 将日志写入文件
    WriteLogger::init(
        log::LevelFilter::Info,
        Config::default(),
        File::create(log_file).expect("创建日志文件失败"),
    )
    .expect("初始化日志失败");
}

// ---- 辅助：防止多实例 ----
pub fn prevent_multiple_instances(app_name: &str) -> bool {
    let mutex_name = format!("Global\\{}", app_name);
    let wide_name: Vec<u16> = mutex_name.encode_utf16().chain(Some(0)).collect();

    // SAFETY: CreateMutexW 是标准 Windows API，参数合法：
    // - lpMutexAttributes = None：使用默认安全属性
    // - bInitialOwner = false：不立即拥有互斥体
    // - lpName = PCWSTR(wide_name.as_ptr())：指向有效的以 null 结尾的 UTF-16 字符串
    // 返回 Result<HANDLE>，我们通过 match 安全地提取。
    let handle = match unsafe { CreateMutexW(None, false, PCWSTR(wide_name.as_ptr())) } {
        Ok(h) => h,
        Err(_) => {
            // 创建失败（可能由于权限不足等），保守策略允许运行
            return true;
        }
    };

    // SAFETY: GetLastError 读取线程最后的错误码，不会导致未定义行为。
    let already_exists = match unsafe { GetLastError() } {
        Ok(()) => false,
        Err(e) => e.code().0 == ERROR_ALREADY_EXISTS.0 as i32,
    };

    // SAFETY: IsInvalid 是 HANDLE 的方法，检查是否为 INVALID_HANDLE_VALUE。
    if handle.is_invalid() {
        // 句柄无效，保守允许运行
        return true;
    }

    if already_exists {
        // SAFETY: CloseHandle 关闭有效句柄，handle 由 CreateMutexW 返回且未被关闭。
        unsafe { let _ = CloseHandle(handle); };
        false // 已有实例
    } else {
        // 成功创建新互斥体，保持句柄打开（进程退出时自动释放）
        true
    }
}

// 将十六进制字符串解析为 u64，支持带或不带 "0x"/"0X" 前缀
fn parse_hex(s: &str) -> Option<u64> {
    let s = s.trim();
    // 去掉前缀（如果有）
    let s = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")).unwrap_or(s);
    // 如果字符串以 # 开头（例如 #123），也去掉
    // let s = s.strip_prefix('#').unwrap_or(s);
    u64::from_str_radix(s, 16).ok()
}

// ---- JSON 更新（键路径用 '.' 分隔） ----
fn update_json(file_path: &str, key_path: &str, value: &Value) -> bool {
    let mut root = if Path::new(file_path).exists() {
        fs::read_to_string(file_path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_else(|| Value::Object(Map::new()))
    } else {
        Value::Object(Map::new())
    };

    if let Value::Object(ref mut map) = root {
        let keys: Vec<&str> = key_path.split('.').collect();
        if keys.is_empty() {
            return false;
        }

        let mut current_map = map;
        for &key in &keys[0..keys.len() - 1] {
            let entry = current_map.entry(key.to_string()).or_insert_with(|| Value::Object(Map::new()));
            if !entry.is_object() {
                *entry = Value::Object(Map::new());
            }
            if let Value::Object(ref mut next_map) = entry {
                current_map = next_map;
            } else {
                return false;
            }
        }

        let last_key = keys.last().unwrap();
        current_map.insert(last_key.to_string(), value.clone());
    } else {
        return false;
    }

    if let Ok(json_str) = serde_json::to_string_pretty(&root) {
        fs::write(file_path, json_str).is_ok()
    } else {
        false
    }
}

// ---- 获取子进程第一个输出 ----
fn get_first_line(child: &mut Child, timeout_ms: u64) -> Option<String> {
    let stdout = child.stdout.take()?;
    let mut reader = BufReader::new(stdout);
    let start = Instant::now();
    let mut line = String::new();

    while start.elapsed().as_millis() < timeout_ms.into() {
        // 尝试读取一行（非阻塞）
        match reader.read_line(&mut line) {
            Ok(0) => break, // EOF
            Ok(_) => {
                let trimmed = line.trim();
                if !trimmed.is_empty() {
                    info!("读取内容：{}", trimmed.to_string());
                    return Some(trimmed.to_string());
                }
                line.clear(); // 清空用于下一行
            }
            Err(e) => error!("读取内容错误：{}", e),
        }
        // 检查子进程是否退出
        if let Ok(Some(_)) = child.try_wait() {
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }
    None
}

// ---- 切换壁纸 ----
fn change_wallpaper(path_casual: &str, typ_casual: &str) {
    let mut path = path_casual.to_string();
    let mut typ = typ_casual.to_string();
    if !Path::new(&path).exists() {
        warn!("文件不存在: {}, 使用默认壁纸", path);
        path = "resources/example.py".to_string();
        typ = "py".to_string();
    }

    let (run_app_path, args) = match typ.as_str() {
        "py" => (PY_ENV_PATH.to_string(), vec![path.clone()]),
        "exe" => (path.clone(), vec![]),
        "video" => {
            let args = vec![
                "-x".to_string(), "1920".to_string(),
                "-y".to_string(), "1080".to_string(),
                "-loop".to_string(), "0".to_string(),
                "-noborder".to_string(),
                "-fs".to_string(),
                "-window_title".to_string(), format!("FFPLAY_WALLPAPER_{}", Path::new(&path).file_name().unwrap().to_string_lossy()),
                "-an".to_string(),
                "-loglevel".to_string(), "quiet".to_string(),
                "-i".to_string(), path.clone(),
            ];
            (FFPLAY_PATH.to_string(), args)
        }
        _ => (PY_ENV_PATH.to_string(), vec!["resources/example.py".to_string()]),
    };

    info!("启动新进程: {} {:?}", run_app_path, args);
    let child = {
        let mut cmd = Command::new(&run_app_path);
        cmd.args(&args)
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .stdin(Stdio::null())
            .creation_flags(0x08000000);// CREATE_NO_WINDOW
        cmd.spawn().expect("启动子进程失败")
    };

    {
        let mut old = STATE.current_child.lock().unwrap();
        if let Some(mut old_child) = old.take() {
            info!("终止旧进程");
            let _ = old_child.kill();
            let start = Instant::now();
            while old_child.try_wait().unwrap().is_none() && start.elapsed().as_secs() < 3 {
                thread::sleep(Duration::from_millis(50));
            }
            let _ = old_child.wait();
        }
        *old = Some(child);
    }

    let mut hwnd = HWND(0);
    match typ.as_str() {
        "py" => {
            let mut child_ref = STATE.current_child.lock().unwrap();
            if let Some(child) = child_ref.as_mut() {
                if let Some(text) = get_first_line(child, 3000) {
                    if let Some(hex) = parse_hex(&text) {
                        hwnd = HWND(hex as isize);
                    } else {error!("hwnd无效：{}", text)}
                }
            }
        }
        "exe" => {
            let base_name = Path::new(&path).file_stem().unwrap().to_string_lossy();
            let start = Instant::now();
            while start.elapsed().as_millis() < 1000 {
                unsafe {
                    // SAFETY: FindWindowW 通过窗口标题查找，base_name 为有效 UTF-16 字符串。
                    hwnd = FindWindowW(None, PCWSTR(base_name.encode_utf16().collect::<Vec<u16>>().as_ptr()));
                    if hwnd.0 != 0 { break; }
                }
                thread::sleep(Duration::from_millis(50));
            }
            if hwnd.0 == 0 {
                let mut child_ref = STATE.current_child.lock().unwrap();
                if let Some(child) = child_ref.as_mut() {
                    if let Some(text) = get_first_line(child, 3000) {
                        if let Some(hex) = parse_hex(&text) {
                            hwnd = HWND(hex as isize);
                        } else {error!("hwnd无效：{}", text)}
                    }
                }
            }
        }
        "video" => {
            let title = format!("FFPLAY_WALLPAPER_{}", Path::new(&path).file_name().unwrap().to_string_lossy());
            let wide_title: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();
            let start = Instant::now();
            while start.elapsed().as_millis() < 3000 {
                unsafe {
                    // SAFETY: FindWindowW 通过窗口标题查找，wide_title 有效。
                    hwnd = FindWindowW(None, PCWSTR(wide_title.as_ptr()));
                    if hwnd.0 != 0 { break; }
                }
                thread::sleep(Duration::from_millis(50));
            }
        }
        _ => {}
    }

    // 使用 workerw 模块嵌入
    hwnd = worker_w::embed_to_workerw(hwnd);
    let wt = match typ.as_str() {
        "py" => WallpaperType::Py,
        "exe" => WallpaperType::Exe,
        "video" => WallpaperType::Video,
        _ => WallpaperType::Nil,
    };
    STATE.wallpaper_type.store(wt as isize, Ordering::Relaxed);

    if hwnd.0 != 0 {
        hook::start_input_thread(hwnd);
    }

    let now = Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
    let _ = update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
    let _ = update_json(CONFIG_FILE, "type", &serde_json::json!(typ));
    let _ = update_json(CONFIG_FILE, "update_time", &serde_json::json!(now));
}

// ---- 加载上次壁纸 ----
fn load_last_wallpaper() {
    if Path::new(CONFIG_FILE).exists() {
        if let Ok(content) = fs::read_to_string(CONFIG_FILE) {
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
                if let (Some(path), Some(typ)) = (
                    json.get("last_wallpaper_path").and_then(|v| v.as_str()),
                    json.get("type").and_then(|v| v.as_str()),
                ) {
                    info!("恢复上次壁纸: {} 类型: {}", path, typ);
                    change_wallpaper(path, typ);
                    return;
                }
            }
        }
        warn!("配置文件解析失败，使用默认壁纸");
    } else {
        info!("配置文件不存在，使用默认壁纸");
    }
    change_wallpaper("resources/example.py", "py");
    let _ = update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!("resources/example.py"));
    let _ = update_json(CONFIG_FILE, "type", &serde_json::json!("py"));
}

// ---- 开机自启 ----
pub fn set_auto_start(enable: bool) {
    // 手动构造宽字符串
    let key_path_wide: Vec<u16> = AUTO_START_KEY.encode_utf16().chain(Some(0)).collect();
    let value_name_wide: Vec<u16> = APP_REGISTRY_NAME.encode_utf16().chain(Some(0)).collect();
    let key_path = PCWSTR(key_path_wide.as_ptr());
    let value_name = PCWSTR(value_name_wide.as_ptr());

    let mut hkey = HKEY(0);
    let open_ok = unsafe {
        // SAFETY: RegOpenKeyExW 打开注册表键，参数合法。
        RegOpenKeyExW(HKEY_CURRENT_USER, key_path, 0, KEY_WRITE, &mut hkey).is_ok()
    };
    if !open_ok {
        warn!("无法打开注册表键");
        return;
    }

    if enable {
        let exe_path = match env::current_exe() {
            Ok(p) => p,
            Err(e) => {
                warn!("获取可执行文件路径失败: {}", e);
                unsafe { let _ = RegCloseKey(hkey); }
                return;
            }
        };
        let exe_path_wide: Vec<u16> = exe_path.to_string_lossy().encode_utf16().chain(Some(0)).collect();
        let data_bytes = unsafe {
            // SAFETY: exe_path_wide 有效，转为字节切片。
            std::slice::from_raw_parts(exe_path_wide.as_ptr() as *const u8, exe_path_wide.len() * 2)
        };
        let set_ok = unsafe {
            // SAFETY: RegSetValueExW 设置值，hkey 有效。
            RegSetValueExW(hkey, value_name, 0, REG_SZ, Some(data_bytes)).is_ok()
        };
        if !set_ok {
            warn!("设置开机自启失败");
        }
    } else {
        let del_ok = unsafe {
            // SAFETY: RegDeleteValueW 删除值，hkey 有效。
            RegDeleteValueW(hkey, value_name).is_ok()
        };
        if !del_ok {
            warn!("删除开机自启失败");
        }
    }

    unsafe {
        // SAFETY: RegCloseKey 关闭键。
        let _ = RegCloseKey(hkey);
    }
}

pub fn is_auto_start_enabled() -> bool {
    // 手动构造宽字符串
    let key_path_wide: Vec<u16> = AUTO_START_KEY.encode_utf16().chain(Some(0)).collect();
    let value_name_wide: Vec<u16> = APP_REGISTRY_NAME.encode_utf16().chain(Some(0)).collect();
    let key_path = PCWSTR(key_path_wide.as_ptr());
    let value_name = PCWSTR(value_name_wide.as_ptr());

    let mut hkey = HKEY(0);
    let open_ok = unsafe {
        RegOpenKeyExW(HKEY_CURRENT_USER, key_path, 0, KEY_READ, &mut hkey).is_ok()
    };
    if !open_ok {
        return false;
    }

    let mut buffer = [0u16; 1024];
    let mut buf_size = buffer.len() as u32;
    let query_ok = unsafe {
        RegQueryValueExW(
            hkey,
            value_name,
            None,
            None,
            Some(buffer.as_mut_ptr() as *mut u8),
            Some(&mut buf_size),
        ).is_ok()
    };

    unsafe { let _ = RegCloseKey(hkey); }
    query_ok
}

// ---- 文件选择器 ----
fn select_file(file_type: &str, extension: &str) -> Option<String> {
    let path = FileDialog::new()
        .set_title("请选择一个文件")
        .add_filter(file_type, &[extension])
        .pick_file();
    path.map(|p| p.to_string_lossy().to_string())
}

// ---- 托盘回调 ----
fn tray_callback_select_py() {
    if let Some(path) = select_file("Python文件", "py") {
        let _ = update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = update_json(CONFIG_FILE, "type", &serde_json::json!("py"));
        let _ = CMD_CHAN.get().unwrap().send(("change".to_string(), path, "py".to_string()));
    }
}

fn tray_callback_select_exe() {
    if let Some(path) = select_file("可执行文件", "exe") {
        let _ = update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = update_json(CONFIG_FILE, "type", &serde_json::json!("exe"));
        let _ = CMD_CHAN.get().unwrap().send(("change".to_string(), path, "exe".to_string()));
    }
}

fn tray_callback_select_video() {
    if let Some(path) = select_file("MP4文件", "mp4") {
        let _ = update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = update_json(CONFIG_FILE, "type", &serde_json::json!("video"));
        let _ = CMD_CHAN.get().unwrap().send(("change".to_string(), path, "video".to_string()));
    }
}

fn tray_callback_about() {
    // 显示关于窗口
    let _ = CMD_CHAN.get().unwrap().send(("about".to_string(), String::new(), String::new()));
}

fn tray_callback_exit() {
    STATE.running.store(false, Ordering::Relaxed);
    let _ = CMD_CHAN.get().unwrap().send(("quit".to_string(), String::new(), String::new()));
}

fn tray_callback_autostart() {
    let enabled = is_auto_start_enabled();
    set_auto_start(!enabled);
    let _ = CMD_CHAN.get().unwrap().send(("autostart_toggle".to_string(), String::new(), String::new()));
}

// ---- 构建菜单 ----
fn build_menu(ids: &MenuIds, autostart_enabled: bool) -> Menu {
    Menu::new()
        .item(MenuItem::button(
            ids.autostart,
            if autostart_enabled { "开机自启✔" } else { "开机自启" },
        ))
        .item(MenuItem::separator())
        .item(MenuItem::button(ids.py, "切换壁纸(Python)"))
        .item(MenuItem::button(ids.exe, "切换壁纸(exe)"))
        .item(MenuItem::button(ids.vid, "切换壁纸(mp4)"))
        .item(MenuItem::separator())
        .item(MenuItem::button(ids.about, "关于"))
        .item(MenuItem::separator())
        .item(MenuItem::button(ids.exit, "退出"))
}

// ---- 加载图标 ----
fn load_icon_from_path(path: &str) -> anyhow::Result<Icon> {
    let img = image::open(path)
        .map_err(|e| anyhow::anyhow!("加载图片失败: {}", e))?;
    let rgba = img.to_rgba8();
    let (width, height) = rgba.dimensions();
    let pixels: Vec<u8> = rgba.into_raw();
    Icon::from_rgba(width, height, pixels)
        .map_err(|e| anyhow::anyhow!("创建图标失败: {}", e))
}

// ---- 主函数 ----
fn run() -> anyhow::Result<()> {
    // ===== 高 DPI 感知（尝试最佳配置，自动降级） =====
    unsafe {
        let result = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        if result.is_err() {
            let result2 = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_SYSTEM_AWARE);
            if result2.is_err() {
                SetProcessDPIAware();
            }
        }
    }

    // 读取关于文本（缓存到 STATE）
    {
        let mut txt = STATE.info_text.lock().unwrap();
        if Path::new(INFO_TEXT_PATH).exists() {
            if let Ok(content) = fs::read_to_string(INFO_TEXT_PATH) {
                *txt = content.trim().to_string();
            }
        }
    }

    // 创建通道并设为全局
    let (cmd_sender, cmd_receiver) = bounded::<(String, String, String)>(100);
    CMD_CHAN.set(cmd_sender).expect("CMD_CHAN 已存在");
    // 加载图标
    let icon = load_icon_from_path(ICON_PATH)?;
    // ui通道
    let ui_sender=ui::start_ui_thread();

    // ---------- 创建托盘菜单 ----------
    // 菜单 ID
    let ids = MenuIds {
        autostart: 1,
        py: 2,
        exe: 3,
        vid: 4,
        about: 5,
        exit: 6,
    };
    // 构建菜单
    let menu = build_menu(&ids, is_auto_start_enabled());
    let tray = Tray::new(TrayConfig::new(icon).tooltip("PythonWallpaper").menu(menu))?;
    let handle = tray.handle();

    // 启动托盘事件循环（在独立线程）
    thread::spawn(move || {
        let _ = tray.run(move |event| {
            if let ldtray::Event::Menu(id) = event {
                // 直接处理事件，无需通道
                if id.0 == ids.autostart {
                    tray_callback_autostart();
                } else if id.0 == ids.py {
                    tray_callback_select_py();
                } else if id.0 == ids.exe {
                    tray_callback_select_exe();
                } else if id.0 == ids.vid {
                    tray_callback_select_video();
                } else if id.0 == ids.about {
                    tray_callback_about();
                } else if id.0 == ids.exit {
                    tray_callback_exit();
                }
            }
        });
    });

    load_last_wallpaper();

    while STATE.running.load(Ordering::Relaxed) {
        while let Ok((cmd, path, typ)) = cmd_receiver.try_recv() {
            match cmd.as_str() {
                "change" => {
                    change_wallpaper(&path, &typ);
                }
                "autostart_toggle" => {
                    let enabled = is_auto_start_enabled();
                    let new_menu = build_menu(&ids, enabled);
                    if let Err(e) = handle.set_menu(new_menu) {
                        error!("更新菜单失败: {}", e);
                    }
                }
                "about" => {
                    let text = {
                        let txt = STATE.info_text.lock().unwrap();
                        if txt.is_empty() {
                            "默认关于文本".to_string()
                        } else {
                            if let Ok(value) = toml::from_str::<toml::Value>(&txt) {
                                if let Some(about) = value.get("about").and_then(|v| v.as_str()) {
                                    about.to_string()
                                } else {
                                    txt.clone()
                                }
                            } else {
                                txt.clone()
                            }
                        }
                    };
                    let _ = ui_sender.send(ui::UiCommand::ShowAbout(text));
                }
                "quit" => {
                    STATE.running.store(false, Ordering::Relaxed);
                    break;
                }
                _ => warn!("未知命令: {}", cmd),
            }
        }
        thread::sleep(Duration::from_millis(50));
    }

    // 清理
    {
        let mut child = STATE.current_child.lock().unwrap();
        if let Some(mut c) = child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
    hook::stop_input_thread();

    unsafe {
        // SAFETY: SystemParametersInfoW 恢复壁纸。
        let _ = SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, None, SPIF_SENDCHANGE);
    }

    info!("程序终止");
    Ok(())
}

fn main() {

    init_logging();
    setup_panic_hook();

    if !prevent_multiple_instances("PythonWallpaper") {
        info!("已有实例运行，退出");
        return;
    }

    if let Err(e) = run() {
        error!("程序异常终止: {}", e);
        error!("{:?}", e);
        log::logger().flush();
        std::process::exit(1);
    }
}