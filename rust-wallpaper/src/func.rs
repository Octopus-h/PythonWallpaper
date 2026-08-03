use std::path::PathBuf;
use std::process::Command;

/// 扫描系统上可能的 Python 解释器路径
pub fn scan_python_environments() -> Vec<String> {
    let mut found = Vec::new();

    // 在 PATH 中查找 python / python3
    for cmd in &["python", "python3"] {
        if let Ok(output) = Command::new("where").arg(cmd).output() {
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                for line in stdout.lines() {
                    let p = line.trim();
                    if !p.is_empty() && std::path::Path::new(p).exists() {
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