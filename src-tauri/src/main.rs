#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{BufRead,BufReader,Write},process::{Child,ChildStdin,ChildStdout,Command,Stdio},sync::{Arc,Mutex}};
use tauri::{Manager,menu::{Menu,MenuItem},tray::TrayIconBuilder};
use tauri_plugin_notification::NotificationExt;
struct Engine {child:Child,input:ChildStdin,output:BufReader<ChildStdout>}
impl Engine {
 fn call(&mut self, method:&str,args:serde_json::Value)->Result<serde_json::Value,String>{
  writeln!(self.input,"{}",serde_json::json!({"method":method,"args":args})).map_err(|_|"监控进程不可用，请重启客户端".to_string())?;
  self.input.flush().map_err(|e|e.to_string())?;
  let mut line=String::new(); self.output.read_line(&mut line).map_err(|e|e.to_string())?;
  let result:serde_json::Value=serde_json::from_str(&line).map_err(|_|"监控进程已退出或返回异常".to_string())?;
  if result["ok"]==true {Ok(result["data"].clone())} else {Err(result["error"].as_str().unwrap_or("操作失败").to_string())}
 }
}
impl Drop for Engine {fn drop(&mut self){let _=self.child.kill();}}
type Shared=Arc<Mutex<Engine>>;
#[tauri::command]
async fn rpc(engine:tauri::State<'_,Shared>,method:String,args:serde_json::Value)->Result<serde_json::Value,String>{
 let engine=engine.inner().clone();
 tauri::async_runtime::spawn_blocking(move||engine.lock().map_err(|_|"监控锁异常".to_string())?.call(&method,args)).await.map_err(|e|e.to_string())?
}
fn main(){
 tauri::Builder::default()
 .plugin(tauri_plugin_single_instance::init(|app,_,_|{if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}}))
 .plugin(tauri_plugin_notification::init())
 .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent,None))
 .setup(|app|{
  let dir=app.path().app_data_dir()?;std::fs::create_dir_all(&dir)?;
  let executable=std::env::current_exe()?.parent().unwrap().join(if cfg!(windows){"monitor-core.exe"}else{"monitor-core"});
  let mut command=if executable.exists(){Command::new(executable)}else{
   #[cfg(debug_assertions)] {
    let root=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    let python=root.join(if cfg!(windows){".venv/Scripts/python.exe"}else{".venv/bin/python"});
    let mut c=Command::new(python);c.args(["-m","core.app"]).current_dir(root);c
   }
   #[cfg(not(debug_assertions))] {return Err("缺少内置监控程序，请重新安装".into());}
  };
  #[cfg(windows)] {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
  let mut child=command.env("STOCK_MONITOR_DATA",dir).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn()?;
  let input=child.stdin.take().unwrap();let output=BufReader::new(child.stdout.take().unwrap());
  let engine=Arc::new(Mutex::new(Engine{child,input,output}));app.manage(engine.clone());
  let show=MenuItem::with_id(app,"show","打开观量",true,None::<&str>)?;
  let quit=MenuItem::with_id(app,"quit","退出并停止监控",true,None::<&str>)?;
  let menu=Menu::with_items(app,&[&show,&quit])?;
  TrayIconBuilder::new().icon(app.default_window_icon().unwrap().clone()).menu(&menu).tooltip("观量 · 后台股票监控")
   .on_menu_event(|app,event|match event.id.as_ref(){"show"=>{if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}},"quit"=>{let engine=app.state::<Shared>();if let Ok(mut e)=engine.lock(){let _=e.child.kill();}app.exit(0);},_=>{}}).build(app)?;
  let handle=app.handle().clone();
  std::thread::spawn(move||{
   let mut disconnected=false;
   loop {
    std::thread::sleep(std::time::Duration::from_secs(2));
    let result=engine.lock().unwrap().call("local_pending",serde_json::json!({}));
    match result {
     Ok(s)=>{disconnected=false;if let Some(events)=s["events"].as_array(){for e in events{
      let key=e["key"].as_str().unwrap_or("");
      if engine.lock().unwrap().call("local_claim",serde_json::json!({"key":key})).ok()!=Some(serde_json::json!(true)){continue;}
      let test=e["kind"]=="NOTIFICATION_TEST";
      let title=e["notification_title"].as_str().unwrap_or(if test{"观量 · 后台通知测试（非卖点信号）"}else{"观量 · 卖点规则提醒"});
      let body=if let Some(body)=e["notification_body"].as_str(){body.to_string()}else if test{"本机通知链路测试。这不是股票交易信号。".to_string()}else{format!("{} {} · 候选 {} · 请手动判断交易",e["symbol"].as_str().unwrap_or(""),e["event_label"].as_str().unwrap_or(""),e["candidate_time"].as_str().unwrap_or(""))};
      let mut n=handle.notification().builder().title(title).body(body);
      if s["sound"]!=false {n=n.sound("default");}
      let visible=handle.get_webview_window("main").and_then(|w|w.is_visible().ok()).unwrap_or(false);
      let result=n.show();
      let status=if result.is_ok(){"accepted"}else{"failed"};
      let detail=format!("系统通知{}；发送时窗口{}。不代表用户已阅读。",if result.is_ok(){"请求已接受"}else{"提交失败"},if visible{"显示"}else{"隐藏"});
      let _=engine.lock().unwrap().call("local_finish",serde_json::json!({"key":key,"status":status,"detail":detail}));
     }}}
     Err(_)=>{if !disconnected {let _=handle.notification().builder().title("观量 · 监控已中断").body("监控进程不可用，请重新启动客户端。这不是卖点信号。").show();disconnected=true;}}
    }
   }
  });
  Ok(())
 })
 .on_window_event(|window,event|{if let tauri::WindowEvent::CloseRequested{api,..}=event{api.prevent_close();let _=window.hide();}})
 .invoke_handler(tauri::generate_handler![rpc])
 .build(tauri::generate_context!()).expect("客户端启动失败")
 .run(|app,event|{
  #[cfg(target_os="macos")]
  if let tauri::RunEvent::Reopen{..}=event {if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}}
  if let tauri::RunEvent::Exit=event {if let Some(engine)=app.try_state::<Shared>() {if let Ok(mut e)=engine.lock(){let _=e.child.kill();}}}
 });
}
