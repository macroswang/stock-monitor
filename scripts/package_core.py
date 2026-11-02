"""Build the per-platform Python binary; execute on the target OS."""
import os,platform,subprocess,sys,shutil
from pathlib import Path
root=Path(__file__).resolve().parent.parent
os.chdir(root)


def _has_pyinstaller(python):
    return subprocess.run(
        [str(python), "-c", "import PyInstaller"], capture_output=True
    ).returncode == 0


def _venv_python():
    for rel in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe"):
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


if not _has_pyinstaller(sys.executable):
    # `npm run package` invokes the system python3, but PyInstaller usually
    # lives in the project venv; re-exec instead of failing with a traceback.
    alternative = _venv_python()
    if alternative is None:
        raise SystemExit(
            "PyInstaller 未安装：请先 pip install -r requirements.txt，或创建 .venv"
        )
    raise SystemExit(subprocess.call([str(alternative), __file__, *sys.argv[1:]]))

if os.environ.get('PACKAGE_SKIP_BUILD')!='1':
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name','monitor-core',
        '--paths',str(root),'--add-data',f'{root / "fixtures"}{os.pathsep}fixtures',
        '--collect-all','keyring','--collect-all','tzdata','--collect-submodules','executor','--distpath','build/core','core/entry.py'],check=True)


def host_triple():
    """Rust target triple used by Tauri's sidecar naming.

    Prefer rustc, but do not require it: on machines where cargo lives outside
    PATH the packaging step should still be able to name the binary.  Note that
    Rust spells Apple silicon ``aarch64`` while ``platform.machine()`` says
    ``arm64``, so the fallback has to translate it.
    """
    try:
        return subprocess.check_output(['rustc','-vV'],text=True).split('host: ')[1].splitlines()[0]
    except (OSError,subprocess.CalledProcessError,IndexError):
        machine=platform.machine()
        system=platform.system()
        if system=='Darwin':
            arch='aarch64' if machine=='arm64' else machine
            return f'{arch}-apple-darwin'
        if system=='Windows':
            return f'{machine}-pc-windows-msvc'
        return f'{machine}-unknown-linux-gnu'


triple=host_triple()
ext='.exe' if os.name=='nt' else ''
target=root/'src-tauri/binaries'/f'monitor-core-{triple}{ext}'
target.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'build/core'/f'monitor-core{ext}',target)
print('Built embedded core for',triple)
