//! Window startup only. This never calls the monitoring or trading engine.
use std::{fs::OpenOptions, io::Write, path::PathBuf, sync::Mutex, time::{Instant, SystemTime, UNIX_EPOCH}};
use tauri::{Manager, WebviewWindow};

#[derive(Default)]
struct Presentation { ready: bool, shown: bool }

impl Presentation {
    fn ready(&mut self) -> bool { self.ready = true; self.show() }
    fn timeout(&mut self) -> bool { if self.ready { false } else { self.show() } }
    fn show(&mut self) -> bool {
        if self.shown { false } else { self.shown = true; true }
    }
}

pub struct Startup {
    started: Instant,
    log_path: PathBuf,
    presentation: Mutex<Presentation>,
}

impl Startup {
    pub fn new(dir: PathBuf) -> Self {
        Self { started: Instant::now(), log_path: dir.join("client-startup.log"), presentation: Mutex::new(Presentation::default()) }
    }

    pub fn log(&self, phase: &str) {
        // Fixed phase names only: no URLs, account data, or RPC payloads.
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&self.log_path) {
            let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
            let _ = writeln!(file, "{stamp} pid={} elapsed_ms={} {phase}", std::process::id(), self.started.elapsed().as_millis());
        }
    }

    pub fn present(&self, window: &WebviewWindow, ready: bool) -> Result<(), String> {
        let mut state = self.presentation.lock().map_err(|_| "启动窗口状态异常")?;
        let show = if ready { state.ready() } else { state.timeout() };
        if !ready && !show { return Ok(()); }
        self.log(if ready { "frontend_ready" } else { "frontend_timeout" });
        if !show { return Ok(()); }
        // Release the state lock before dispatching window work to the UI thread.
        drop(state);
        if window.show().is_err() {
            self.presentation.lock().map_err(|_| "启动窗口状态异常")?.shown = false;
            self.log("window_show_failed");
            return Err("启动窗口显示失败".into());
        }
        self.log("window_shown");
        if window.set_focus().is_err() { self.log("window_focus_failed"); }
        else { self.log("window_focused"); }
        Ok(())
    }
}

#[tauri::command]
pub fn frontend_ready(window: WebviewWindow, startup: tauri::State<'_, Startup>) -> Result<(), String> {
    if window.label() != "main" { return Err("无效的启动窗口".into()); }
    startup.present(&window, true)
}

pub fn arm_fallback(handle: tauri::AppHandle) {
    std::thread::spawn(move || {
        // A missing/broken frontend must not leave the app permanently hidden.
        // Show the HTML loading/error screen, without reloading or restarting core.
        std::thread::sleep(std::time::Duration::from_secs(10));
        if let (Some(window), Some(startup)) = (handle.get_webview_window("main"), handle.try_state::<Startup>()) {
            let _ = startup.present(&window, false);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mounted_ui_is_presented_once() {
        let mut state = Presentation::default();
        assert!(state.ready()); assert!(!state.ready()); assert!(!state.timeout());
    }
    #[test]
    fn failed_frontend_is_revealed_then_can_finish_without_stealing_focus() {
        let mut state = Presentation::default();
        assert!(state.timeout()); assert!(!state.timeout()); assert!(!state.ready()); assert!(state.ready);
    }
    #[test]
    fn log_is_local_and_contains_stage_and_pid() {
        let dir = std::env::temp_dir().join(format!("stock-monitor-startup-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let state = Startup::new(dir.clone()); state.log("page_finished");
        let log = std::fs::read_to_string(dir.join("client-startup.log")).unwrap();
        assert!(log.contains("page_finished")); assert!(log.contains("pid="));
        std::fs::remove_dir_all(dir).unwrap();
    }
}
