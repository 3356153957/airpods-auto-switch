"""One-way, opt-in takeover. No media keys and no disconnect on silence."""
import enum
import json
import logging
import queue
import threading
import time
from settings_manager import settings, COMMAND_DIR, STATUS_FILE, write_json

log = logging.getLogger(__name__)


class State(enum.Enum):
    DISABLED = '自动接管已关闭'
    IDLE = '等待电脑播放'
    CONNECTING = '正在连接 AirPods'
    CONNECTED = '已连接到电脑'
    YIELDED = '已让出连接，等待下次播放'
    FAILED = '连接未成功'


class PlaybackTrigger:
    """Debounce playback and require silence before reclaiming a lost connection."""
    def __init__(self):
        self.armed = True
        self.started = None
        self.silent_since = None

    def reset(self, armed=True):
        self.armed, self.started, self.silent_since = armed, None, None

    def update(self, playing, now, delay):
        if not playing:
            self.started = None
            if self.silent_since is None:
                self.silent_since = now
            if now - self.silent_since >= 1:
                self.armed = True
            return False
        self.silent_since = None
        if self.started is None:
            self.started = now
        if self.armed and now - self.started >= delay:
            self.armed = False
            return True
        return False


class AutoSwitchEngine:
    def __init__(self, audio_monitor, bt_manager, on_state_change=None, on_notice=None, resume=None):
        self.audio = audio_monitor
        self.bt = bt_manager
        self.on_state_change = on_state_change
        self.on_notice = on_notice
        self.on_ui_action = None
        self.state = State.DISABLED
        self._commands = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread = None
        self._trigger = PlaybackTrigger()
        self._last_enabled = None
        self._device_name = None
        self._lost_since = None
        self._last_connected = False
        if resume:
            self.state = State[resume['state']]
            self._last_enabled = resume['enabled']
            self._device_name = resume['device_name']
            self._last_connected = resume['last_connected']
            self._lost_since = resume['lost_since']
            self._trigger.armed = resume['armed']
            self._trigger.started = resume['started']
            self._trigger.silent_since = resume['silent_since']

    def export_runtime(self):
        return {'state': self.state.name, 'enabled': self._last_enabled, 'device_name': self._device_name,
                'last_connected': self._last_connected, 'lost_since': self._lost_since,
                'armed': self._trigger.armed, 'started': self._trigger.started, 'silent_since': self._trigger.silent_since}

    def request_mode(self, background):
        self._commands.put('background_mode' if background else 'window_mode')

    def _set_state(self, value):
        if self.state != value:
            log.info('State: %s -> %s', self.state.value, value.value)
            self.state = value
            self._publish_status()
            if self.on_state_change:
                self.on_state_change(value)

    def _publish_status(self):
        try:
            write_json(STATUS_FILE, {'state': self.state.value, 'time': time.time(), 'source': self.audio.last_source})
        except OSError:
            log.warning('Status file is busy; next update will retry.')

    def notice(self, title, message, force=False):
        log.info('Notice: %s | %s', title, message)
        if self.on_notice and (force or settings.get('NOTIFICATIONS_ENABLED', True)):
            self.on_notice(title, message)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='AirPodsEngine', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=18)

    def manual_connect(self):
        self._commands.put('connect')

    def manual_disconnect(self):
        self._commands.put('disconnect')

    def _connect(self, automatic=False):
        self._set_state(State.CONNECTING)
        if automatic:
            self.notice('正在切换到电脑', f'检测到 {self.audio.last_source or "电脑"} 播放音频，正在连接耳机。')
        if self.bt.connect(cancel=self._stop, automatic=automatic):
            self._last_connected = True
            self._lost_since = None
            self._set_state(State.CONNECTED)
            self.notice('AirPods 已切换到电脑', '电脑音频现已输出到耳机。')
        else:
            self._set_state(State.FAILED)
            if not self._stop.is_set() and (not automatic or settings.get('AUTO_CONNECT_ENABLED')):
                self.notice('AirPods 连接未成功', '请确认耳机已取出且在附近。可在托盘菜单中选择“立即连接”。')

    def _read_commands(self):
        COMMAND_DIR.mkdir(parents=True, exist_ok=True)
        for path in sorted(COMMAND_DIR.glob('*.json')):
            try:
                self._commands.put(json.loads(path.read_text(encoding='utf-8'))['action'])
            except (ValueError, KeyError, OSError):
                log.warning('Invalid local command %s', path.name)
            finally:
                path.unlink(missing_ok=True)
        while not self._commands.empty() and not self._stop.is_set():
            action = self._commands.get()
            if action == 'connect':
                self._connect()
            elif action == 'disconnect':
                settings.set('AUTO_CONNECT_ENABLED', False)
                if self.bt.disconnect(cancel=self._stop):
                    self.notice('已断开电脑连接', '自动接管已关闭，可在手机上连接耳机。')
                else:
                    self.notice('自动接管已关闭', '未能确认耳机已断开，请检查 Windows 蓝牙连接。')
                self._set_state(State.DISABLED)
            elif action == 'test_notification':
                self.notice('AirPods 提示测试', '连接结果会在右下角显示；Windows 勿扰模式可能会隐藏提示。', force=True)
            elif action in ('show_settings', 'hide_settings', 'quit') and self.on_ui_action:
                self.on_ui_action(action)
            elif action in ('background_mode', 'window_mode') and self.on_ui_action:
                from app_lifecycle import save_runtime
                save_runtime(self.export_runtime())
                self._stop.set()
                self.on_ui_action('relaunch', action == 'background_mode')

    def _tick(self):
        cfg = settings.snapshot()
        enabled = bool(cfg['AUTO_CONNECT_ENABLED'])
        name = cfg['DEVICE_NAME']
        if enabled != self._last_enabled or name != self._device_name:
            self._trigger.reset()
            self._last_enabled, self._device_name = enabled, name
            self._lost_since = None
            self._last_connected = False
            self._set_state(State.IDLE if enabled else State.DISABLED)
        if not enabled:
            return
        now = time.monotonic()
        playing = self.audio.is_audio_playing()
        connected = self.bt.is_connected()
        is_default = connected and self.bt.is_default_output()
        if is_default:
            self._last_connected = True
            self._lost_since = None
            self._set_state(State.CONNECTED)
            self._trigger.reset(armed=False)
            return
        if self._last_connected:
            if self._lost_since is None:
                self._lost_since = now
            if now - self._lost_since < 3:
                return
            self._last_connected = False
            self._trigger.reset(armed=False)
            self._set_state(State.YIELDED)
            self.notice('AirPods 已离开电脑', '当前播放期间暂停接管；电脑静音后，下次播放会再次尝试连接。')
        if self._trigger.update(playing, now, float(cfg['AUDIO_START_DELAY'])):
            self._connect(automatic=True)

    def _loop(self):
        import comtypes
        comtypes.CoInitialize()
        try:
            while not self._stop.is_set():
                try:
                    self._read_commands()
                    if self._stop.is_set():
                        break
                    self._tick()
                    self._publish_status()
                except Exception:
                    log.exception('Engine cycle failed')
                self._stop.wait(0.35)
        finally:
            self.audio.cleanup()
            comtypes.CoUninitialize()
            write_json(STATUS_FILE, {'state': '程序已退出', 'time': 0, 'source': ''})
