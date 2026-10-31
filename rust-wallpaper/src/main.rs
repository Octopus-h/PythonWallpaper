#![windows_subsystem = "windows"]

mod hook;
mod state;
mod ui;
mod wallpaper;
mod worker_w;
mod func;

use std::{path::Path, thread, time::Duration};

use crossbeam_channel::{bounded, Sender};
use flexi_logger::{Cleanup, Criterion, FileSpec, Logger, Naming, WriteMode};
use ldtray::{Menu, MenuItem, Tray, TrayConfig};
use log::{error, info, warn};

use crate::{
    state::STATE,
    wallpaper::{WallpaperManager, CONFIG_FILE, INFO_TEXT_PATH},
};

use windows::Win32::{
    UI::HiDpi::*,
    UI::WindowsAndMessaging::*,
};

/// 菜单动作枚举
#[derive(Clone, Copy)]
enum MenuAction {
    ToggleAutostart,
    SelectPythonWallpaper,
    SelectExeWallpaper,
    SelectVideoWallpaper,
    ShowAbout,
    ShowSettings,
    Exit,
}

/// 菜单项
#[derive(Clone)]
enum MenuEntry {
    Item { id: u32, label: String, action: MenuAction },
    Separator,
}

static CMD_CHAN: std::sync::OnceLock<Sender<(String, String, String)>> = std::sync::OnceLock::new();

fn build_menu_config(autostart_enabled: bool) -> Vec<MenuEntry> {
    vec![
        MenuEntry::Item {
            id: 1,
            label: if autostart_enabled {
                "开机自启✔".to_string()
            } else {
                "开机自启".to_string()
            },
            action: MenuAction::ToggleAutostart,
        },
        MenuEntry::Separator,
        MenuEntry::Item {
            id: 2,
            label: "切换壁纸(Python)".to_string(),
            action: MenuAction::SelectPythonWallpaper,
        },
        MenuEntry::Item {
            id: 3,
            label: "切换壁纸(exe)".to_string(),
            action: MenuAction::SelectExeWallpaper,
        },
        MenuEntry::Item {
            id: 4,
            label: "切换壁纸(mp4)".to_string(),
            action: MenuAction::SelectVideoWallpaper,
        },
        MenuEntry::Separator,
        MenuEntry::Item {
            id: 5,
            label: "关于".to_string(),
            action: MenuAction::ShowAbout,
        },
        MenuEntry::Item {
            id: 6,
            label: "设置".to_string(),
            action: MenuAction::ShowSettings,
        },
        MenuEntry::Separator,
        MenuEntry::Item {
            id: 7,
            label: "退出".to_string(),
            action: MenuAction::Exit,
        },
    ]
}

fn build_ldtray_menu(entries: &[MenuEntry]) -> Menu {
    let mut menu = Menu::new();
    for entry in entries {
        match entry {
            MenuEntry::Item { id, label, .. } => {
                menu = menu.item(MenuItem::button(*id, label.clone()));
            }
            MenuEntry::Separator => {
                menu = menu.item(MenuItem::separator());
            }
        }
    }
    menu
}

fn action_for_id(entries: &[MenuEntry], id: u32) -> Option<MenuAction> {
    entries.iter().find_map(|entry| {
        if let MenuEntry::Item {
            id: item_id,
            action,
            ..
        } = entry
        {
            if *item_id == id {
                Some(*action)
            } else {
                None
            }
        } else {
            None
        }
    })
}

fn dispatch_action(action: MenuAction) {
    match action {
        MenuAction::ToggleAutostart => tray_callback_autostart(),
        MenuAction::SelectPythonWallpaper => tray_callback_select_py(),
        MenuAction::SelectExeWallpaper => tray_callback_select_exe(),
        MenuAction::SelectVideoWallpaper => tray_callback_select_video(),
        MenuAction::ShowAbout => tray_callback_about(),
        MenuAction::ShowSettings => tray_callback_settings(),
        MenuAction::Exit => tray_callback_exit(),
    }
}

fn select_file(file_type: &str, extension: &str) -> Option<String> {
    let path = rfd::FileDialog::new()
        .set_title("请选择一个文件")
        .add_filter(file_type, &[extension])
        .pick_file();

    path.map(|p| p.to_string_lossy().to_string())
}

fn tray_callback_select_py() {
    if let Some(path) = select_file("Python文件", "py") {
        let _ = WallpaperManager::update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = WallpaperManager::update_json(CONFIG_FILE, "type", &serde_json::json!("py"));
        WallpaperManager::new().change_wallpaper(&path, "py");
    }
}

fn tray_callback_select_exe() {
    if let Some(path) = select_file("可执行文件", "exe") {
        let _ = WallpaperManager::update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = WallpaperManager::update_json(CONFIG_FILE, "type", &serde_json::json!("exe"));
        WallpaperManager::new().change_wallpaper(&path, "exe");
    }
}

fn tray_callback_select_video() {
    if let Some(path) = select_file("MP4文件", "mp4") {
        let _ = WallpaperManager::update_json(CONFIG_FILE, "last_wallpaper_path", &serde_json::json!(path));
        let _ = WallpaperManager::update_json(CONFIG_FILE, "type", &serde_json::json!("video"));
        WallpaperManager::new().change_wallpaper(&path, "video");
    }
}

fn tray_callback_about() {
    let _ = CMD_CHAN
        .get()
        .unwrap()
        .send(("about".to_string(), String::new(), String::new()));
}

fn tray_callback_settings() {
    let _ = CMD_CHAN
        .get()
        .unwrap()
        .send(("settings".to_string(), String::new(), String::new()));
}

fn tray_callback_exit() {
    STATE.running.store(true, std::sync::atomic::Ordering::Relaxed);
    let _ = CMD_CHAN
        .get()
        .unwrap()
        .send(("quit".to_string(), String::new(), String::new()));
}

fn tray_callback_autostart() {
    let enabled = WallpaperManager::is_auto_start_enabled();
    WallpaperManager::set_auto_start(!enabled);
    let _ = CMD_CHAN
        .get()
        .unwrap()
        .send(("autostart_toggle".to_string(), String::new(), String::new()));
}

fn setup_panic_hook() {
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        let payload = panic_info.payload();
        let msg = if let Some(s) = payload.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = payload.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic".to_string()
        };

        let location = panic_info
            .location()
            .map(|loc| format!("{}:{}", loc.file(), loc.line()))
            .unwrap_or_else(|| "unknown location".to_string());

        error!("Panic occurred at {}: {}", location, msg);

        let bt = std::backtrace::Backtrace::force_capture().to_string();
        if !bt.is_empty() {
            error!("Backtrace:\n{}", bt);
        }

        default_hook(panic_info);
    }));
}

fn init_logging() {
    Logger::try_with_str("info")
        .unwrap()
        .format(|w, now, record| {
            write!(
                w,
                "[{}] [{}] [{}] {}",
                now.now().format("%Y-%m-%d %H:%M:%S%.3f"),
                record.level(),
                record.target(),
                record.args()
            )
        })
        .log_to_file(FileSpec::default().basename("lastlog").suffix("log"))
        .append()
        .write_mode(WriteMode::BufferAndFlush)
        .rotate(
            Criterion::Size(256 * 1024),
            Naming::Timestamps,
            Cleanup::KeepLogFiles(3),
        )
        .start()
        .unwrap();
}

fn load_icon_from_path(path: &str) -> anyhow::Result<ldtray::Icon> {
    let img = image::open(path)
        .map_err(|e| anyhow::anyhow!("加载图片失败: {}", e))?;
    let rgba = img.to_rgba8();
    let (width, height) = rgba.dimensions();
    let pixels: Vec<u8> = rgba.into_raw();
    ldtray::Icon::from_rgba(width, height, pixels)
        .map_err(|e| anyhow::anyhow!("创建图标失败: {}", e))
}

fn run() -> anyhow::Result<()> {
    unsafe {
        let result = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        if result.is_err() {
            let result2 = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_SYSTEM_AWARE);
            if result2.is_err() {
                SetProcessDPIAware();
            }
        }
    }

    // 读取关于文本
    {
        let mut txt = STATE.info_text.lock().unwrap();
        if Path::new(INFO_TEXT_PATH).exists() {
            if let Ok(content) = std::fs::read_to_string(INFO_TEXT_PATH) {
                *txt = content.trim().to_string();
            }
        }
    }

    // 创建命令通道
    let (cmd_sender, cmd_receiver) = bounded::<(String, String, String)>(100);
    CMD_CHAN.set(cmd_sender).expect("CMD_CHAN 已存在");

    // 加载图标并启动 UI
    let icon = load_icon_from_path("resources/icons/icon.ico")?;
    ui::start_ui_thread();

    // 创建托盘菜单
    let menu_config = build_menu_config(WallpaperManager::is_auto_start_enabled());
    let menu = build_ldtray_menu(&menu_config);
    let tray = Tray::new(TrayConfig::new(icon).tooltip("PythonWallpaper").menu(menu))?;
    let handle = tray.handle();

    thread::spawn(move || {
        let config = menu_config;
        let _ = tray.run(move |event| {
            if let ldtray::Event::Menu(id) = event {
                if let Some(action) = action_for_id(&config, id.0) {
                    dispatch_action(action);
                }
            }
        });
    });

    WallpaperManager::new().load_last_wallpaper();

    while STATE.running.load(std::sync::atomic::Ordering::Relaxed) {
        while let Ok((cmd, _, _)) = cmd_receiver.try_recv() {
            match cmd.as_str() {
                "autostart_toggle" => {
                    let enabled = WallpaperManager::is_auto_start_enabled();
                    let new_config = build_menu_config(enabled);
                    let new_menu = build_ldtray_menu(&new_config);
                    if let Err(e) = handle.set_menu(new_menu) {
                        error!("更新菜单失败: {}", e);
                    }
                }
                "about" => {
                    let text = {
                        let txt = STATE.info_text.lock().unwrap();
                        if txt.is_empty() {
                            warn!("关于文本缺失");
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
                    ui::show_about(text);
                }
                "settings" => {
                    // 这里后续填充设置逻辑
                }
                "quit" => {
                    STATE.running.store(false, std::sync::atomic::Ordering::Relaxed);
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
        let _ = SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, None, SPIF_SENDCHANGE);
    }

    info!("程序终止");
    Ok(())
}

fn main() {
    // 确保运行目录为 exe 所在目录
    func::ensure_runtime_working_directory();

    // 初始化日志
    init_logging();

    // 设置 panic 钩子
    setup_panic_hook();

    // 启动前检查关键资源是否存在
    let resources_ok = func::validate_required_resources();
    if !resources_ok {
        warn!("部分资源缺失，程序可能无法正常工作，继续启动...");
    }

    if !WallpaperManager::prevent_multiple_instances("PythonWallpaper") {
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