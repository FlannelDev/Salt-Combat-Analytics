"""Windows launcher for Salt Combat Analytics. Built with PyInstaller on Windows."""
import os, sys, runpy, threading, time, traceback
from pathlib import Path

def main():
    base = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent / 'app'
    os.chdir(base)
    sys.path.insert(0, str(base))
    # Run snapshot sync in-process; no Python installation required on target PCs.
    def snapshot_worker():
        from snapshot_sync import synchronize
        last_error = None
        while True:
            try:
                config = base / 'wow_path.txt'
                if config.exists():
                    wow = Path(config.read_text(encoding='utf-8-sig').strip().strip('"'))
                    if wow.is_dir():
                        synchronize(wow, quiet=True)
                last_error = None
            except Exception as exc:
                if str(exc) != last_error:
                    print('Snapshot sync warning:', exc, flush=True)
                    last_error = str(exc)
            time.sleep(3)
    threading.Thread(target=snapshot_worker, daemon=True, name='HCS-Snapshot-Sync').start()
    print('Salt Combat Analytics | By Flannel')
    print('Local-only dashboard: http://127.0.0.1:8765')
    print('To stop the application, close this window.')
    try:
        runpy.run_path(str(base / 'server.py'), run_name='__main__')
    except OSError as exc:
        print('Startup failed:', exc)
        print('If port 8765 is already in use, close the old analyzer before restarting.')
        input('Press Enter to exit...')
        raise

if __name__ == '__main__':
    main()
