use std::{
    env,
    fs::{self},
    io::{BufRead, BufReader},
    os::windows::process::CommandExt,
    path::Path,
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use chrono::Local;
use log::{error, info, warn};
use serde_json::{Map, Value};
use windows::{
    Win32::{
        Foundation::*,
        System::{Registry::*, Threading::*},
        UI::WindowsAndMessaging::*,
    }, core::*
};

use crate::{
    hook,
    state::{AppState, WallpaperType, STATE},
    worker_w,
};

/// 配置文件路径，保持和原项目一致
pub const CONFIG_FILE: &str = "resources/config.json";
pub const FFPLAY_PATH: &str = "resources/ffmpeg/ffplay.exe";
pub const PY_ENV_PATH: &str = "resources/pyenv/pythonw.exe";
pub const INFO_TEXT_PATH: &str = "resources/text.toml";
pub const AUTO_START_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
pub const APP_REGISTRY_NAME: &str = "PythonWallpaper";

/// 壁纸管理器
///
/// 作用：
/// - 负责启动/停止壁纸进程
/// - 负责查找窗口句柄
/// - 负责嵌入 WorkerW
/// - 负责配置持久化
/// - 负责开机自启状态管理
pub struct WallpaperManager {
    state: &'static AppState,
}

impl WallpaperManager {
    pub fn new() -> Self {
        Self { state: &STATE }
    }

    /// 解析 16 进制窗口句柄字符串
    pub fn parse_hex(s: &str) -> Option<u64> {
        let s = s.trim();
        let s = s
            .strip_prefix("0x")
            .or_else(|| s.strip_prefix("0X"))
            .unwrap_or(s);

        u64::from_str_radix(s, 16).ok()
    }

    /// 更新 JSON 配置（支持多层 key_path）
    pub fn update_json(file_path: &str, key_path: &str, value: &Value) -> bool {
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
                let entry = current_map
                    .entry(key.to_string())
                    .or_insert_with(|| Value::Object(Map::new()));
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

        if let Ok(json) = serde_json::to_string_pretty(&root) {
            fs::write(file_path, json).is_ok()
        } else {
            false
        }
    }

    /// 从子进程 stdout 读取第一行文本（用于读取 Python/EXE 输出的 hwnd）
    pub fn get_first_line(child: &mut Child, timeout_ms: u64) -> Option<String> {
        let stdout = child.stdout.take()?;
        let mut reader = BufReader::new(stdout);
        let start = Instant::now();
        let mut line = String::new();

        while start.elapsed().as_millis() < timeout_ms.into() {
            match reader.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() {
                        info!("读取内容：{}", trimmed);
                        return Some(trimmed.to_string());
                    }
                    line.clear();
                }
                Err(e) => error!("读取内容错误：{}", e),
            }

            if let Ok(Some(_)) = child.try_wait() {
                break;
            }

            thread::sleep(Duration::from_millis(50));
        }

        None
    }

    /// 切换壁纸：支持 Python / EXE / 视频
    pub fn change_wallpaper(&self, path_casual: &str, typ_casual: &str) {
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
                    "-x".to_string(),
                    "1920".to_string(),
                    "-y".to_string(),
                    "1080".to_string(),
                    "-loop".to_string(),
                    "0".to_string(),
                    "-noborder".to_string(),
                    "-fs".to_string(),
                    "-window_title".to_string(),
                    format!(
                        "FFPLAY_WALLPAPER_{}",
                        Path::new(&path)
                            .file_name()
                            .unwrap()
                            .to_string_lossy()
                    ),
                    "-an".to_string(),
                    "-loglevel".to_string(),
                    "quiet".to_string(),
                    "-i".to_string(),
                    path.clone(),
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
                .creation_flags(0x08000000); // CREATE_NO_WINDOW
            cmd.spawn().expect("启动子进程失败")
        };

        {
            let mut old = self.state.current_child.lock().unwrap();
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
                let mut child_ref = self.state.current_child.lock().unwrap();
                if let Some(child) = child_ref.as_mut() {
                    if let Some(text) = Self::get_first_line(child, 3000) {
                        if let Some(hex) = Self::parse_hex(&text) {
                            hwnd = HWND(hex as isize);
                        } else {
                            error!("hwnd无效：{}", text);
                        }
                    }
                }
            }
            "exe" => {
                let base_name = Path::new(&path).file_stem().unwrap().to_string_lossy();
                let start = Instant::now();

                while start.elapsed().as_millis() < 1000 {
                    unsafe {
                        hwnd = FindWindowW(None, PCWSTR(base_name.encode_utf16().collect::<Vec<u16>>().as_ptr()));
                        if hwnd.0 != 0 {
                            break;
                        }
                    }
                    thread::sleep(Duration::from_millis(50));
                }

                if hwnd.0 == 0 {
                    let mut child_ref = self.state.current_child.lock().unwrap();
                    if let Some(child) = child_ref.as_mut() {
                        if let Some(text) = Self::get_first_line(child, 3000) {
                            if let Some(hex) = Self::parse_hex(&text) {
                                hwnd = HWND(hex as isize);
                            } else {
                                error!("hwnd无效：{}", text);
                            }
                        }
                    }
                }
            }
            "video" => {
                let title = format!(
                    "FFPLAY_WALLPAPER_{}",
                    Path::new(&path).file_name().unwrap().to_string_lossy()
                );
                let wide_title: Vec<u16> = title.encode_utf16().chain(Some(0)).collect();
                let start = Instant::now();

                while start.elapsed().as_millis() < 3000 {
                    unsafe {
                        hwnd = FindWindowW(None, PCWSTR(wide_title.as_ptr()));
                        if hwnd.0 != 0 {
                            break;
                        }
                    }
                    thread::sleep(Duration::from_millis(50));
                }
            }
            _ => {}
        }

        // 嵌入桌面底层 WorkerW
        hwnd = worker_w::embed_to_workerw(hwnd);

        let wt = match typ.as_str() {
            "py" => WallpaperType::Py,
            "exe" => WallpaperType::Exe,
            "video" => WallpaperType::Video,
            _ => WallpaperType::Nil,
        };

        self.state.wallpaper_type.store(wt as isize, std::sync::atomic::Ordering::Relaxed);
        self.state.wallpaper_hwnd.store(hwnd.0, std::sync::atomic::Ordering::Relaxed);

        if hwnd.0 != 0 {
            hook::start_input_thread(hwnd);
        }

        let now = Local::now().format("%Y-%m-%d %H:%M:%S").to_string();

        // 更新配置
        let _ = Self::update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = Self::update_json(CONFIG_FILE, "type", &serde_json::json!(typ));
        let _ = Self::update_json(CONFIG_FILE, "update_time", &serde_json::json!(now));
    }

    /// 加载上次壁纸
    pub fn load_last_wallpaper(&self) {
        if Path::new(CONFIG_FILE).exists() {
            if let Ok(content) = fs::read_to_string(CONFIG_FILE) {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let (Some(path), Some(typ)) = (
                        json.get("last_wallpaper_path").and_then(|v| v.as_str()),
                        json.get("type").and_then(|v| v.as_str()),
                    ) {
                        info!("恢复上次壁纸: {} 类型: {}", path, typ);
                        self.change_wallpaper(path, typ);
                        return;
                    }
                }
            }
            warn!("配置文件解析失败，使用默认壁纸");
        } else {
            info!("配置文件不存在，使用默认壁纸");
        }

        self.change_wallpaper("resources/example.py", "py");
        let _ = Self::update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!("resources/example.py"));
        let _ = Self::update_json(CONFIG_FILE, "type", &serde_json::json!("py"));
    }

    /// 设置开机自启
    pub fn set_auto_start(enable: bool) {
        let key_path_wide: Vec<u16> = AUTO_START_KEY.encode_utf16().chain(Some(0)).collect();
        let value_name_wide: Vec<u16> = APP_REGISTRY_NAME.encode_utf16().chain(Some(0)).collect();
        let key_path = PCWSTR(key_path_wide.as_ptr());
        let value_name = PCWSTR(value_name_wide.as_ptr());

        let mut hkey = HKEY(0);

        let open_ok = unsafe {
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

            let quoted_exe_path = format!("\"{}\"", exe_path.to_string_lossy());
            let exe_path_wide: Vec<u16> = quoted_exe_path.encode_utf16().chain(Some(0)).collect();
            let data_bytes = unsafe {
                std::slice::from_raw_parts(
                    exe_path_wide.as_ptr() as *const u8,
                    exe_path_wide.len() * 2,
                )
            };

            let set_ok = unsafe {
                RegSetValueExW(hkey, value_name, 0, REG_SZ, Some(data_bytes)).is_ok()
            };
            if !set_ok {
                warn!("设置开机自启失败");
            }
        } else {
            let del_ok = unsafe { RegDeleteValueW(hkey, value_name).is_ok() };
            if !del_ok {
                warn!("删除开机自启失败");
            }
        }

        unsafe {
            let _ = RegCloseKey(hkey);
        }
    }

    /// 判断开机自启是否启用
    pub fn is_auto_start_enabled() -> bool {
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
            )
            .is_ok()
        };

        unsafe {
            let _ = RegCloseKey(hkey);
        }

        query_ok
    }

    /// 防止重复实例
    pub fn prevent_multiple_instances(app_name: &str) -> bool {
        let mutex_name = format!("Global\\{}", app_name);
        let wide_name: Vec<u16> = mutex_name.encode_utf16().chain(Some(0)).collect();

        let already_exists = unsafe {
            match OpenMutexW(MUTEX_ALL_ACCESS, false, PCWSTR(wide_name.as_ptr())) {
                Ok(h) => {
                    let _ = CloseHandle(h);
                    true
                }
                Err(_) => false,
            }
        };

        if already_exists {
            return false;
        }

        let handle = match unsafe { CreateMutexW(None, false, PCWSTR(wide_name.as_ptr())) } {
            Ok(h) => h,
            Err(_) => {
                warn!("创建失败，保守允许运行");
                return true;
            }
        };

        if handle.is_invalid() {
            warn!("句柄无效，保守允许运行");
        }

        true
    }
}