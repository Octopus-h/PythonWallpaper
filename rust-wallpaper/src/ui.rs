use slint::{Weak, ComponentHandle};
use std::sync::OnceLock;

slint::include_modules!();

static MAIN_WINDOW: OnceLock<Weak<MainWindow>> = OnceLock::new();
static ERROR_WINDOW: OnceLock<Weak<ErrorWindow>> = OnceLock::new();

pub fn start_ui_thread() {
    std::thread::spawn(|| {
        let main_window = MainWindow::new().unwrap();
        let error_window = ErrorWindow::new().unwrap();

        main_window.hide().unwrap();
        error_window.hide().unwrap();

        // 保存弱引用，忽略可能出现的重复设置错误
        let _ = MAIN_WINDOW.set(main_window.as_weak());
        let _ = ERROR_WINDOW.set(error_window.as_weak());

        // 通过 get() 获取 Weak 再 upgrade
        main_window.on_close_requested(move || {
            if let Some(window) = MAIN_WINDOW.get().and_then(|w| w.upgrade()) {
                let _ = window.hide();
            }
        });

        error_window.on_close_requested(move || {
            if let Some(window) = ERROR_WINDOW.get().and_then(|w| w.upgrade()) {
                let _ = window.hide();
            }
        });

        slint::run_event_loop_until_quit().unwrap();
    });
}

pub fn show_about(text: String) {
    let Some(weak) = MAIN_WINDOW.get() else {
        return;
    };
    let weak = weak.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = weak.upgrade() {
            window.set_page("about".into());
            window.set_about_text(text.into());
            let _ = window.show();
        }
    })
    .unwrap();
}

pub fn show_settings() {
    let Some(weak) = MAIN_WINDOW.get() else {
        return;
    };
    let weak = weak.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = weak.upgrade() {
            window.set_page("settings".into());
            let _ = window.show();
        }
    })
    .unwrap();
}

pub fn show_error(title: String, message: String) {
    let Some(weak) = ERROR_WINDOW.get() else {
        return;
    };
    let weak = weak.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = weak.upgrade() {
            window.set_error_title(title.into());
            window.set_error_message(message.into());
            let _ = window.show();
        }
    })
    .unwrap();
}

pub fn hide_main() {
    let Some(weak) = MAIN_WINDOW.get() else {
        return;
    };
    let weak = weak.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = weak.upgrade() {
            let _ = window.hide();
        }
    })
    .unwrap();
}

pub fn hide_error() {
    let Some(weak) = ERROR_WINDOW.get() else {
        return;
    };
    let weak = weak.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = weak.upgrade() {
            let _ = window.hide();
        }
    })
    .unwrap();
}