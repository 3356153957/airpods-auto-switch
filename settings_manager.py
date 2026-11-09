"""Local settings shared by the tray process and settings window."""
import copy
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)
DEFAULT_SETTINGS = {
    'DEVICE_NAME': '',
    'AUTO_CONNECT_ENABLED': False,
    'NOTIFICATIONS_ENABLED': True,
    'TRAY_HINT_ENABLED': True,
    'AUDIO_THRESHOLD': 0.001,
    'AUDIO_START_DELAY': 1.0,
    'APP_BLACKLIST': ['explorer.exe', 'wallpaper32.exe', 'wallpaper64.exe'],
}
SETTINGS_DIR = Path(os.environ.get('AIRPODS_SWITCH_DATA_DIR', Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AirPodsSwitchLocal'))
SETTINGS_FILE = SETTINGS_DIR / 'settings.json'
STATUS_FILE = SETTINGS_DIR / 'status.json'
COMMAND_DIR = SETTINGS_DIR / 'commands'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(6):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                # A reader or antivirus may briefly hold a handle without delete sharing.
                if attempt == 5:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)


class SettingsManager:
    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._values = copy.deepcopy(DEFAULT_SETTINGS)
        self._mtime = None
        if not self.path.exists():
            write_json(self.path, self._values)
        self.snapshot()

    def snapshot(self):
        with self._lock:
            try:
                stamp = self.path.stat().st_mtime_ns
                if stamp != self._mtime:
                    values = json.loads(self.path.read_text(encoding='utf-8'))
                    if not isinstance(values, dict):
                        raise ValueError('Settings must be an object')
                    self._values = copy.deepcopy(DEFAULT_SETTINGS) | values
                    self._mtime = stamp
            except (OSError, ValueError):
                log.warning('Could not reload settings; retaining last valid values.', exc_info=True)
            return copy.deepcopy(self._values)

    def get(self, key, default=None):
        return self.snapshot().get(key, default)

    def update(self, values):
        with self._lock:
            merged = self.snapshot() | values
            write_json(self.path, merged)
            self._mtime = None
            self.snapshot()

    def set(self, key, value):
        self.update({key: value})


def send_command(action):
    write_json(COMMAND_DIR / (uuid.uuid4().hex + '.json'), {'action': action})


settings = SettingsManager()
