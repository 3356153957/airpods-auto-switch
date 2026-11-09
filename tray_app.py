"""Native tray icon, custom light menu, and Windows connection notifications."""
import ctypes
from ctypes import wintypes
import logging
import threading
import pystray
from pystray._util import win32
from PIL import ImageDraw
from settings_manager import settings, send_command
from state_machine import State
from ui_styles import app_icon

log = logging.getLogger(__name__)
COLORS = {State.DISABLED: '#8A99A8', State.IDLE: '#3479CE', State.CONNECTING: '#D49A36', State.CONNECTED: '#14946F', State.YIELDED: '#8A99A8', State.FAILED: '#D16068'}


def make_icon(state=State.IDLE):
    image = app_icon(128)
    d = ImageDraw.Draw(image)
    d.ellipse((85, 85, 126, 126), fill='white')
    d.ellipse((91, 91, 120, 120), fill=COLORS[state])
    return image


def open_settings():
    send_command('show_settings')


class PanelIcon(pystray.Icon):
    def __init__(self, *args, panel=None, **kwargs):
        self.panel = panel
        super().__init__(*args, **kwargs)

    def _on_notify(self, wparam, lparam):
        if lparam == win32.WM_RBUTTONUP:
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            self.panel.dispatch('tray_menu', point.x, point.y)
        elif lparam == win32.WM_LBUTTONUP:
            self.panel.dispatch('show_settings')
        else:
            super()._on_notify(wparam, lparam)


class TrayApp:
    def __init__(self, engine, panel):
        self.engine = engine
        self.panel = panel
        engine.on_state_change = self._on_state_change
        engine.on_notice = self.notify
        engine.on_ui_action = panel.dispatch
        panel.engine = engine
        panel.on_background_request = lambda: engine.request_mode(True)
        self._icon = PanelIcon('AirPodsSwitchLocal', make_icon(engine.state), 'AirPods · '+engine.state.value, panel=panel)
        panel.tray = self
        self.ready = threading.Event()

    def notify(self, title, message):
        if self.ready.is_set():
            try:
                self._icon.notify(message, title)
            except Exception:
                log.exception('Windows notification could not be sent')

    def _on_state_change(self, state):
        self._icon.icon = make_icon(state)
        self._icon.title = 'AirPods · ' + state.value

    def _setup(self, icon):
        icon.visible = True
        self.ready.set()
        self.engine.start()

    def run(self):
        if getattr(self.panel, 'headless', False):
            try:
                self._icon.run(setup=self._setup)
            finally:
                self.engine.stop()
                self.ready.clear()
            return
        self._icon.run_detached(setup=self._setup)
        try:
            self.panel.mainloop()
        finally:
            self.engine.stop()
            self.ready.clear()
            self._icon.stop()


class HeadlessPanel:
    headless = True
    def dispatch(self, action, *args):
        if action == 'show_settings':
            self.engine.request_mode(False)
        elif action == 'tray_menu':
            from app_lifecycle import launch_menu
            launch_menu(*args)
        elif action == 'quit':
            self.engine._stop.set()
            self.tray._icon.stop()
        elif action == 'relaunch':
            from app_lifecycle import launch_replacement
            launch_replacement(args[0])
            self.tray._icon.stop()
