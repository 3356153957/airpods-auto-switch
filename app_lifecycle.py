"""Replace the UI process with a small tray process while keeping engine state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from settings_manager import SETTINGS_DIR, write_json

RESUME_FILE = SETTINGS_DIR / 'runtime-resume.json'


def save_runtime(state):
    write_json(RESUME_FILE, {'time': time.time(), 'state': state})


def load_runtime():
    try:
        value = json.loads(RESUME_FILE.read_text(encoding='utf-8'))
        state = value['state']
        required = {'state', 'enabled', 'device_name', 'last_connected', 'lost_since', 'armed', 'started', 'silent_since'}
        if isinstance(state, dict) and required <= state.keys() and state['state'] in {'DISABLED','IDLE','CONNECTING','CONNECTED','YIELDED','FAILED'}:
            return state if time.time()-value['time'] < 60 else None
        return None
    except (OSError, ValueError, KeyError):
        return None
    finally:
        RESUME_FILE.unlink(missing_ok=True)


def _command():
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    return [str(pythonw if pythonw.exists() else sys.executable), str(Path(__file__).with_name('main.py'))]


def launch_replacement(background):
    return subprocess.Popen(_command() + (['--background'] if background else []) + ['--wait-parent', str(os.getpid())], creationflags=0x08000000)


def launch_menu(x, y):
    return subprocess.Popen(_command() + ['--quick-menu', str(x), str(y)], creationflags=0x08000000)


def wait_for_parent():
    if '--wait-parent' not in sys.argv:
        return
    import psutil
    pid = int(sys.argv[sys.argv.index('--wait-parent')+1])
    try:
        psutil.Process(pid).wait(timeout=35)
    except psutil.NoSuchProcess:
        pass
