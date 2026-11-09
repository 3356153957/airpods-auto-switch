import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop UI')
class WindowLifecycleTests(unittest.TestCase):
    def test_explicit_hide_is_not_undone_by_delayed_startup_show(self):
        from settings_manager import DEFAULT_SETTINGS
        from gui import SettingsGUI
        cfg = copy.deepcopy(DEFAULT_SETTINGS) | {'DEVICE_NAME': 'AirPods Pro', 'TRAY_HINT_ENABLED': False}
        fake = SimpleNamespace(snapshot=lambda: cfg.copy(), get=lambda key, default=None: cfg.get(key, default))
        with tempfile.TemporaryDirectory() as folder, patch('gui.settings', fake), \
                patch('gui.SETTINGS_DIR', Path(folder)), patch('gui.STATUS_FILE', Path(folder) / 'status.json'), \
                patch('gui.BluetoothManager.paired_devices', return_value=['AirPods Pro']):
            panel = SettingsGUI()
            observations = []
            def inspect():
                observations.append((panel._hidden, bool(panel.winfo_viewable())))
                panel.destroy()
            panel.after(100, panel._hide)
            panel.after(600, inspect)
            panel.mainloop()
        self.assertEqual(observations, [(True, False)])
