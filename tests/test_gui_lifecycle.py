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


def _contrast(a, b):
    def luminance(color):
        channels = [int(color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class PaletteTests(unittest.TestCase):
    def test_switch_off_track_meets_non_text_contrast(self):
        from ui_styles import SURFACE, SWITCH_OFF
        # WCAG 1.4.11: the "off" track must stay visible on the white card.
        self.assertGreaterEqual(_contrast(SWITCH_OFF, SURFACE), 3.0)


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop UI')
class FirstRunFeedbackTests(unittest.TestCase):
    def feedback_for(self, saved_device, paired):
        from settings_manager import DEFAULT_SETTINGS
        from gui import SettingsGUI
        cfg = copy.deepcopy(DEFAULT_SETTINGS) | {'DEVICE_NAME': saved_device, 'TRAY_HINT_ENABLED': False}
        fake = SimpleNamespace(snapshot=lambda: cfg.copy(), get=lambda key, default=None: cfg.get(key, default))
        with tempfile.TemporaryDirectory() as folder, patch('gui.settings', fake), \
                patch('gui.SETTINGS_DIR', Path(folder)), patch('gui.STATUS_FILE', Path(folder) / 'status.json'), \
                patch('gui.BluetoothManager.paired_devices', return_value=paired):
            panel = SettingsGUI(preview=True)
            try:
                panel.update_idletasks()
                return panel.feedback.cget('text')
            finally:
                panel.destroy()

    def test_auto_selected_device_explains_it_still_needs_saving(self):
        text = self.feedback_for('', ['AirPods Pro'])
        self.assertIn('AirPods Pro', text)
        self.assertIn('保存', text)
        self.assertNotEqual(text, '有未保存的更改')

    def test_saved_device_reports_saved_state(self):
        self.assertEqual(self.feedback_for('AirPods Pro', ['AirPods Pro']), '设置保存在本机')
