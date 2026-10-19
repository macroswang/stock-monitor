"""Exercise the shipped installer against an isolated copy of real local data."""
from pathlib import Path
import tempfile,subprocess,sqlite3,os,json,plistlib
root=Path(__file__).resolve().parent.parent
source=root/'build/production-dmg/观量.app'
db=Path.home()/'Library/Application Support/com.xreddot.stockmonitor/monitor.sqlite3'
with tempfile.TemporaryDirectory(prefix='stock-upgrade-check-') as td:
 t=Path(td)
 for name in ['Applications','UserApps','data']: (t/name).mkdir()
 for src,dst in [(source,t/'观量.app'),(Path('/Applications/观量.app'),t/'Applications/观量.app'),(Path('/Applications/观量.app'),t/'UserApps/观量.app')]:
  subprocess.run(['/usr/bin/ditto',str(src),str(dst)],check=True)
 a=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True);b=sqlite3.connect(t/'data/monitor.sqlite3');a.backup(b);a.close();b.close()
 def dump():
  c=sqlite3.connect(t/'data/monitor.sqlite3');d={name:c.execute('SELECT * FROM '+name+' ORDER BY 1').fetchall() for name in ['watch','cache','events','messages']};c.close();return d
 before=dump()
 script=(root/'scripts/install-upgrade-mac.command').read_text().replace('target="/Applications/观量.app"','target="'+str(t/'Applications/观量.app')+'"').replace('old_entry="$HOME/Applications/观量.app"','old_entry="'+str(t/'UserApps/观量.app')+'"').replace('data="$HOME/Library/Application Support/com.xreddot.stockmonitor"','data="'+str(t/'data')+'"').replace('test -w /Applications','test -w "'+str(t/'Applications')+'"').replace('"$HOME/Applications"','"'+str(t/'UserApps')+'"').replace('staged="/Applications/','staged="'+str(t/'Applications')+'/')
 p=t/'安装或升级观量.command';p.write_text(script)
 r=subprocess.run(['/bin/bash',str(p)],env=dict(os.environ,STOCK_MONITOR_INSTALL_NO_LAUNCH='1'),text=True,capture_output=True,timeout=30)
 assert r.returncode==0,(r.stdout,r.stderr)
 assert before==dump(),'existing records changed'
 assert (t/'UserApps/观量.app').is_symlink(),'old entry not symlink'
 assert (t/'UserApps/观量.app').resolve()==(t/'Applications/观量.app').resolve(),'wrong symlink target'
 version=plistlib.loads((t/'Applications/观量.app/Contents/Info.plist').read_bytes())['CFBundleShortVersionString']
 assert version=='0.4.3',('wrong version',version)
 backups=list((t/'data/upgrade-backups').iterdir());assert len(backups)==1,'backup count'
 assert (backups[0]/'monitor.sqlite3').exists(),'no DB backup'
 assert (backups[0]/'previous-system-app.disabled').exists(),'no previous system app'
 assert (backups[0]/'previous-user-app.disabled').exists(),'no previous user app'
 report=dict(passed=True,existing_records_exactly_preserved={k:len(v) for k,v in before.items()},old_entry_redirected=True,old_apps_backed_up=True,database_backup_integrity='ok',version=version)
 (root/'docs/0.4.3/upgrade-isolated-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
