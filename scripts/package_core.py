"""Build the per-platform Python binary; execute on the target OS."""
import os,subprocess,sys,shutil
from pathlib import Path
root=Path(__file__).resolve().parent.parent
os.chdir(root)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name','monitor-core',
    '--paths',str(root),'--add-data',f'{root / "fixtures"}{os.pathsep}fixtures',
    '--collect-all','keyring','--collect-all','tzdata','--distpath','build/core','core/entry.py'],check=True)
triple=subprocess.check_output(['rustc','-vV'],text=True).split('host: ')[1].splitlines()[0]
ext='.exe' if os.name=='nt' else ''
target=root/'src-tauri/binaries'/f'monitor-core-{triple}{ext}'
target.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'build/core'/f'monitor-core{ext}',target)
print('Built embedded core for',triple)
