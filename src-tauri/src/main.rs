#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{fs::OpenOptions,io::{self,BufRead,BufReader,Write},path::{Path,PathBuf},process::{Child,ChildStdin,ChildStdout,Command,Stdio},sync::{Arc,Mutex,mpsc::{sync_channel,SyncSender,Sender,channel}},time::Duration};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use tauri::{Manager,menu::{Menu,MenuItem},tray::TrayIconBuilder};
use tauri_plugin_notification::NotificationExt;
use serde_json::Value;
mod startup;

/// One request for the Python sidecar.
struct Job{method:String,args:Value,reply:Sender<Result<Value,String>>}

/// Requests are queued and served by a single worker thread.
///
/// If a reply never arrives (a desynced pipe cannot be recovered in place) the
/// engine is killed and respawned, and the caller gets an actionable error.
struct Engine{
 tx:Mutex<SyncSender<Job>>,
 child:Mutex<Child>,
 dir:PathBuf,
 restarting:Mutex<()>,
}

fn launch(dir:&Path)->io::Result<(Child,ChildStdin,ChildStdout)>{
 let executable=std::env::current_exe()?.parent().unwrap().join(if cfg!(windows){"monitor-core.exe"}else{"monitor-core"});
 #[cfg(debug_assertions)]
 let mut command={
  let root=Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
  let python=root.join(if cfg!(windows){".venv/Scripts/python.exe"}else{".venv/bin/python"});
  if python.exists(){let mut c=Command::new(python);c.args(["-m","core.app"]).current_dir(root);c}
  else if executable.exists(){Command::new(executable)}
  else{return Err(io::Error::new(io::ErrorKind::NotFound,"缺少开发环境和内置监控程序"));}
 };
 #[cfg(not(debug_assertions))]
 let mut command=if executable.exists(){Command::new(executable)}
  else{return Err(io::Error::new(io::ErrorKind::NotFound,"缺少内置监控程序，请重新安装"));};
 #[cfg(windows)] {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
 // Keep stderr: a crashed or stuck sidecar is otherwise invisible.
 // Append: a restart must not wipe the evidence of what got stuck.
 let log=OpenOptions::new().create(true).append(true).open(dir.join("monitor-core.log")).map(Stdio::from).unwrap_or_else(|_|Stdio::null());
 #[cfg(unix)]
 command.process_group(0);
 let mut child=command.env("STOCK_MONITOR_DATA",dir).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(log).spawn()?;
 let input=child.stdin.take().unwrap();let output=child.stdout.take().unwrap();
 Ok((child,input,output))
}

/// Write one request, retrying on EINTR.
///
/// Treating `Interrupted` as fatal is what desynced the pipe before: the write
/// or read would abort while the other side was mid-message, and every later
/// reply would belong to the previous request.
fn write_request(input:&mut ChildStdin,text:&str)->io::Result<()>{
 let mut remaining=text.as_bytes();
 while !remaining.is_empty(){
  match input.write(remaining){
   Ok(0)=>return Err(io::Error::new(io::ErrorKind::WriteZero,"写入 0 字节")),
   Ok(n)=>{remaining=&remaining[n..];}
   Err(error) if error.kind()==io::ErrorKind::Interrupted=>continue,
   Err(error)=>return Err(error),
  }
 }
 loop{
  match input.flush(){
   Err(error) if error.kind()==io::ErrorKind::Interrupted=>continue,
   other=>return other,
  }
 }
}

/// Read one line, retrying on EINTR so a signal never strands a reply.
fn read_reply(output:&mut BufReader<ChildStdout>,line:&mut String)->io::Result<usize>{
 loop{
  line.clear();
  match output.read_line(line){
   Ok(size)=>return Ok(size),
   Err(error) if error.kind()==io::ErrorKind::Interrupted=>continue,
   Err(error)=>return Err(error),
  }
 }
}

fn spawn_worker(mut input:ChildStdin,output:ChildStdout)->SyncSender<Job>{
 let (tx,rx)=sync_channel::<Job>(32);
 std::thread::spawn(move||{
  let mut output=BufReader::new(output);
  for job in rx{
   let mut payload=serde_json::json!({"method":job.method,"args":job.args}).to_string();
   payload.push('\n');
   if let Err(error)=write_request(&mut input,&payload){
    let _=job.reply.send(Err(format!("连接监控进程失败：{error}")));
    continue;
   }
   let mut line=String::new();
   match read_reply(&mut output,&mut line){
    Ok(0)=>{let _=job.reply.send(Err("监控进程已退出；涉及券商委托时请先核对执行记录和券商委托".to_string()));}
    Ok(_)=>{
     let result=serde_json::from_str::<Value>(&line)
      .map_err(|_|"监控进程返回异常".to_string())
      .and_then(|value|if value["ok"]==true{Ok(value["data"].clone())}else{Err(value["error"].as_str().unwrap_or("操作失败").to_string())});
     let _=job.reply.send(result);
    }
    Err(error)=>{let _=job.reply.send(Err(format!("读取监控进程失败：{error}")));}
   }
  }
 });
 tx
}

impl Engine{
 fn new(dir:PathBuf,child:Child,input:ChildStdin,output:ChildStdout)->Engine{
  Engine{tx:Mutex::new(spawn_worker(input,output)),child:Mutex::new(child),dir,restarting:Mutex::new(())}
 }

 fn request(&self,method:&str,args:Value,timeout:Duration,restart_on_timeout:bool)->Result<Value,String>{
  let (reply,rx)=channel();
  {
   let tx=self.tx.lock().map_err(|_|"监控队列异常，请重启客户端".to_string())?;
   tx.try_send(Job{method:method.to_string(),args,reply})
    .map_err(|_|"监控进程繁忙，请稍后重试".to_string())?;
  }
  match rx.recv_timeout(timeout){
   Ok(result)=>result,
   Err(_)=>{
    if restart_on_timeout{
     let _=self.restart();
     Err("监控进程无响应，已自动重启；若涉及券商委托，请先核对执行记录和券商委托，勿直接重试".to_string())
    }else{
     Err("监控进程响应超时".to_string())
    }
   }
  }
 }

 /// Kill the current sidecar and start a fresh one.
 fn restart(&self)->Result<(),String>{
  let _guard=self.restarting.lock().map_err(|_|"重启锁异常".to_string())?;
  self.kill_tree();
  let (child,input,output)=launch(&self.dir).map_err(|e|e.to_string())?;
  let tx=spawn_worker(input,output);
  *self.tx.lock().map_err(|_|"监控队列异常".to_string())?=tx;
  *self.child.lock().map_err(|_|"监控进程异常".to_string())?=child;
  Ok(())
 }
}

impl Engine{
 /// PyInstaller's onefile mode leaves a child process behind; killing only the
 /// launcher orphans the Python side, which keeps the database locked.
 fn kill_tree(&self){
  if let Ok(mut child)=self.child.lock(){
   let pid=child.id();
   #[cfg(unix)]
   {let _=Command::new("sh").arg("-c").arg(format!("kill -9 -{pid} 2>/dev/null")).status();}
   let _=child.kill();
   let _=child.wait();
  }
 }
}

impl Drop for Engine{fn drop(&mut self){self.kill_tree();}}

type Shared=Arc<Engine>;
const CALL_TIMEOUT:Duration=Duration::from_secs(25);
const POLL_TIMEOUT:Duration=Duration::from_secs(20);

#[tauri::command]
async fn rpc(engine:tauri::State<'_,Shared>,method:String,args:Value)->Result<Value,String>{
 let engine=engine.inner().clone();
 tauri::async_runtime::spawn_blocking(move||engine.request(&method,args,CALL_TIMEOUT,true)).await.map_err(|e|e.to_string())?
}

#[tauri::command]
async fn restart_core(engine:tauri::State<'_,Shared>)->Result<bool,String>{
 let engine=engine.inner().clone();
 tauri::async_runtime::spawn_blocking(move||engine.restart()).await.map_err(|e|e.to_string())??;
 Ok(true)
}

fn main(){
 tauri::Builder::default()
 .plugin(tauri_plugin_single_instance::init(|app,_,_|{if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}}))
 .plugin(tauri_plugin_notification::init())
 .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent,None))
 .on_page_load(|webview,payload|{
  if webview.label()=="main" { if let Some(startup)=webview.try_state::<startup::Startup>() {
   startup.log(match payload.event(){tauri::webview::PageLoadEvent::Started=>"page_started",tauri::webview::PageLoadEvent::Finished=>"page_finished"});
  }}
 })
 .setup(|app|{
  let dir=app.path().app_data_dir()?;std::fs::create_dir_all(&dir)?;
  let startup=startup::Startup::new(dir.clone());startup.log("native_setup");app.manage(startup);
  startup::arm_fallback(app.handle().clone());
  let (child,input,output)=launch(&dir)?;
  let engine=Arc::new(Engine::new(dir,child,input,output));
  app.manage(engine.clone());
  let show=MenuItem::with_id(app,"show","打开观量",true,None::<&str>)?;
  let quit=MenuItem::with_id(app,"quit","退出并停止监控",true,None::<&str>)?;
  let menu=Menu::with_items(app,&[&show,&quit])?;
  TrayIconBuilder::new().icon(app.default_window_icon().unwrap().clone()).menu(&menu).tooltip("观量 · 后台股票监控")
   .on_menu_event(|app,event|match event.id.as_ref(){"show"=>{if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}},"quit"=>{let engine=app.state::<Shared>();engine.kill_tree();app.exit(0);},_=>{}}).build(app)?;
  let handle=app.handle().clone();
  std::thread::spawn(move||{
   let mut disconnected=false;
   loop {
    std::thread::sleep(Duration::from_secs(2));
    match engine.request("local_pending",serde_json::json!({}),POLL_TIMEOUT,false){
     Ok(s)=>{disconnected=false;if let Some(events)=s["events"].as_array(){for e in events{
      let key=e["key"].as_str().unwrap_or("");
      if engine.request("local_claim",serde_json::json!({"key":key}),POLL_TIMEOUT,false).ok()!=Some(serde_json::json!(true)){continue;}
      let test=e["kind"]=="NOTIFICATION_TEST";
      let title=e["notification_title"].as_str().unwrap_or(if test{"观量 · 后台通知测试（非卖点信号）"}else{"观量 · 卖点规则提醒"});
      let body=if let Some(body)=e["notification_body"].as_str(){body.to_string()}else if test{"本机通知链路测试。这不是股票交易信号。".to_string()}else{format!("{} {} · 候选 {} · 请手动判断交易",e["symbol"].as_str().unwrap_or(""),e["event_label"].as_str().unwrap_or(""),e["candidate_time"].as_str().unwrap_or(""))};
      let mut n=handle.notification().builder().title(title).body(body);
      if s["sound"]!=false {n=n.sound("default");}
      let visible=handle.get_webview_window("main").and_then(|w|w.is_visible().ok()).unwrap_or(false);
      let result=n.show();
      let status=if result.is_ok(){"accepted"}else{"failed"};
      let detail=format!("系统通知{}；发送时窗口{}。不代表用户已阅读。",if result.is_ok(){"请求已接受"}else{"提交失败"},if visible{"显示"}else{"隐藏"});
      let _=engine.request("local_finish",serde_json::json!({"key":key,"status":status,"detail":detail}),POLL_TIMEOUT,false);
     }}}
     Err(_)=>{if !disconnected {let _=handle.notification().builder().title("观量 · 监控已中断").body("监控进程无响应。请打开观量点击“重启监控进程”，或重启客户端。这不是卖点信号。").show();disconnected=true;}}
    }
   }
  });
  Ok(())
 })
 .on_window_event(|window,event|{if let tauri::WindowEvent::CloseRequested{api,..}=event{api.prevent_close();let _=window.hide();}})
 .invoke_handler(tauri::generate_handler![rpc,restart_core,startup::frontend_ready])
 .build(tauri::generate_context!()).expect("客户端启动失败")
 .run(|app,event|{
  #[cfg(target_os="macos")]
  if let tauri::RunEvent::Reopen{..}=event {if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}}
  if let tauri::RunEvent::Exit=event {if let Some(engine)=app.try_state::<Shared>() {if let Ok(mut child)=engine.child.lock(){let _=child.kill();}}}
 });
}
