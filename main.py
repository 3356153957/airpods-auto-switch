"""Single-instance app: Tk owns the UI thread; audio and the tray run separately."""
import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from settings_manager import SETTINGS_DIR, send_command


def instance_lock(settings_window=False):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, 'Local\\AirPodsSwitchLocal' + ('QuickMenu' if settings_window == 'quick-menu' else 'Tray'))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle, ctypes.get_last_error() != 183


def main():
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AirPodsSwitch.Local')
    if '--ui-preview' in sys.argv:
        from gui import SettingsGUI
        SettingsGUI(preview=True).mainloop()
        return
    if '--quick-menu' in sys.argv:
        mutex, first = instance_lock('quick-menu')
        if first:
            from gui import SettingsGUI
            from ui_popups import TrayMenu
            position = sys.argv.index('--quick-menu')
            panel = SettingsGUI(background=True)
            panel.quick_menu = True
            menu = TrayMenu(panel, int(sys.argv[position+1]), int(sys.argv[position+2]))
            def check_closed():
                if menu.winfo_exists():
                    panel.after(100, check_closed)
                else:
                    panel.destroy()
            panel.after(500, check_closed)
            panel.mainloop()
        return
    from app_lifecycle import wait_for_parent, load_runtime
    wait_for_parent()
    mutex, first = instance_lock()
    if not first:
        send_command('show_settings')
        return
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [RotatingFileHandler(SETTINGS_DIR / 'airpods.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s', handlers=handlers)
    from audio_monitor import AudioMonitor
    from bluetooth_manager import BluetoothManager
    from state_machine import AutoSwitchEngine
    from tray_app import TrayApp, HeadlessPanel
    if '--background' in sys.argv:
        panel = HeadlessPanel()
    else:
        from gui import SettingsGUI
        panel = SettingsGUI()
    engine = AutoSwitchEngine(AudioMonitor(), BluetoothManager(), resume=load_runtime())
    TrayApp(engine, panel).run()


if __name__ == '__main__':
    main()
