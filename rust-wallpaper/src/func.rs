use std::{
    env,
    path::Path,
    process::Command,
};

use log::{error, info, warn};

/// ---------------------------
/// 资源路径
/// ---------------------------
const CONFIG_FILE: &str = "resources/config.json";
const FFPLAY_PATH: &str = "resources/ffmpeg/ffplay.exe";
const PY_ENV_PATH: &str = "resources/pyenv/pythonw.exe";
const ICON_PATH: &str = "resources/icons/icon.ico";
const INFO_TEXT_PATH: &str = "resources/text.toml";

/// ---------------------------
/// 修正当前工作目录
/// ---------------------------
/// 作用：
/// - 避免注册表 Run 启动时，当前目录不是 exe 所在目录
/// - 这样 resources/... 这种相对路径不会失效
/// - 这是最常见的“注册表写入成功，但程序启动后立刻退出”的原因之一
pub fn ensure_runtime_working_directory() {
    match env::current_exe() {
        Ok(exe_path) => {
            if let Some(dir) = exe_path.parent() {
                if let Err(e) = env::set_current_dir(dir) {
                    error!("设置工作目录失败: {} -> {}", dir.display(), e);
                } else {
                    info!("已设置工作目录: {}", dir.display());
                }
            } else {
                warn!("无法获取 exe 父目录，保持默认工作目录");
            }
        }
        Err(e) => {
            error!("获取 exe 路径失败: {}", e);
        }
    }
}

/// ---------------------------
/// 检查启动所需资源
/// ---------------------------
/// 作用：
/// - 检查 resources 目录下的关键文件是否存在
/// - 缺失时输出日志，方便判断是否因为资源问题导致启动失败
pub fn validate_required_resources() -> bool {
    let required = [
        CONFIG_FILE,
        FFPLAY_PATH,
        PY_ENV_PATH,
        ICON_PATH,
        INFO_TEXT_PATH,
        "resources/example.py",
    ];

    let mut missing = Vec::new();

    for item in required {
        if !Path::new(item).exists() {
            missing.push(item.to_string());
        }
    }

    if !missing.is_empty() {
        warn!("启动前检查到缺失资源：");
        for item in &missing {
            warn!("  - {}", item);
        }
        return false;
    }

    info!("所有必需资源已就绪");
    true
}

/// ---------------------------
/// 扫描系统中可能存在的 Python 解释器
/// ---------------------------
/// 作用：
/// - 作为辅助检查，帮助发现系统中已有 Python 路径
/// - 便于排查 pythonw.exe / python 路径缺失
pub fn scan_python_environments() -> Vec<String> {
    let mut found = Vec::new();

    // 在 PATH 中查找 python / python3
    for cmd in &["python", "python3"] {
        if let Ok(output) = Command::new("where").arg(cmd).output() {
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                for line in stdout.lines() {
                    let p = line.trim();
                    if !p.is_empty() && Path::new(p).exists() {
                        found.push(p.to_string());
                    }
                }
            }
        }
    }

    // 去重
    found.sort();
    found.dedup();
    found
}