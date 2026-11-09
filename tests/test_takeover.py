import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from state_machine import AutoSwitchEngine, State
from audio_monitor import eligible_session
from settings_manager import SettingsManager, write_json


class FakeSettings:
    def __init__(self, enabled=True):
        self.values = {'AUTO_CONNECT_ENABLED': enabled, 'DEVICE_NAME': 'AirPods', 'AUDIO_START_DELAY': 1., 'NOTIFICATIONS_ENABLED': True}
    def snapshot(self):
        return self.values.copy()
    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeAudio:
    last_source = 'music.exe'
    playing = True
    def is_audio_playing(self):
        return self.playing


class FakeBluetooth:
    connected = False
    default = False
    succeed = True
    attempts = 0
    def is_connected(self):
        return self.connected
    def is_default_output(self):
        return self.default
    def connect(self, **kwargs):
        self.attempts += 1
        self.connected = self.default = self.succeed
        return self.succeed


class TakeoverTests(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeSettings()
        self.audio = FakeAudio()
        self.bt = FakeBluetooth()
        self.engine = AutoSwitchEngine(self.audio, self.bt)
        self.clock = 100.
        self.addCleanup(patch.stopall)
        patch('state_machine.settings', self.cfg).start()
        patch('state_machine.write_json').start()
        patch('state_machine.time.monotonic', lambda: self.clock).start()

    def tick(self, elapsed=0):
        self.clock += elapsed
        self.engine._tick()

    def test_sustained_playback_connects_once(self):
        self.tick()
        self.tick(.4)
        self.assertEqual(self.bt.attempts, 0)
        self.tick(.7)
        self.assertEqual(self.bt.attempts, 1)
        self.tick(20)
        self.assertEqual(self.bt.attempts, 1)

    def test_short_sound_does_not_connect(self):
        self.tick()
        self.tick(.4)
        self.audio.playing = False
        self.tick(.1)
        self.tick(4)
        self.assertEqual(self.bt.attempts, 0)

    def test_disabling_preserves_current_connection(self):
        self.tick()
        self.tick(1.1)
        self.cfg.values['AUTO_CONNECT_ENABLED'] = False
        self.tick(1)
        self.assertTrue(self.bt.connected)
        self.assertEqual(self.engine.state, State.DISABLED)
        self.bt.connected = False
        self.tick(30)
        self.assertEqual(self.bt.attempts, 1)

    def test_phone_takeover_does_not_start_connection_fight(self):
        self.tick()
        self.tick(1.1)
        self.bt.connected = self.bt.default = False
        self.tick(.1)
        self.tick(4)
        self.tick(10)
        self.assertEqual(self.bt.attempts, 1)
        self.audio.playing = False
        self.tick(.1)
        self.tick(1.1)
        self.audio.playing = True
        self.tick(.1)
        self.tick(1.1)
        self.assertEqual(self.bt.attempts, 2)

    def test_failure_does_not_loop_or_spam(self):
        self.bt.succeed = False
        self.tick()
        self.tick(1.1)
        self.tick(30)
        self.assertEqual(self.bt.attempts, 1)
        self.assertEqual(self.engine.state, State.FAILED)

    def test_notification_preference_and_explicit_test(self):
        notices = []
        self.engine.on_notice = lambda *args: notices.append(args)
        self.cfg.values['NOTIFICATIONS_ENABLED'] = False
        self.engine.notice('title', 'body')
        self.assertEqual(notices, [])
        self.engine.notice('test', 'body', force=True)
        self.assertEqual(len(notices), 1)

    def test_process_handoff_preserves_yield_to_phone(self):
        self.tick()
        self.tick(1.1)
        self.bt.connected = self.bt.default = False
        self.tick(.1)
        self.tick(4)
        resumed = AutoSwitchEngine(self.audio, self.bt, resume=self.engine.export_runtime())
        resumed._tick()
        self.assertEqual(resumed.state, State.YIELDED)
        self.assertEqual(self.bt.attempts, 1)

    def test_process_handoff_preserves_failed_attempt_debounce(self):
        self.bt.succeed = False
        self.tick()
        self.tick(1.1)
        resumed = AutoSwitchEngine(self.audio, self.bt, resume=self.engine.export_runtime())
        resumed._tick()
        self.assertEqual(resumed.state, State.FAILED)
        self.assertEqual(self.bt.attempts, 1)

    def test_system_muted_and_wallpaper_sessions_are_ignored(self):
        self.assertFalse(eligible_session(None, True, False, 1, set()))
        self.assertFalse(eligible_session('music.exe', True, True, 1, set()))
        self.assertFalse(eligible_session('music.exe', True, False, 0, set()))
        self.assertFalse(eligible_session('WALLPAPER64.EXE', True, False, 1, {'wallpaper64.exe'}))
        self.assertFalse(eligible_session('ShellExperienceHost.exe', True, False, 1, set()))
        self.assertTrue(eligible_session('music.exe', True, False, 1, set()))

    def test_settings_saved_in_one_process_are_reloaded_in_another(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            first, second = SettingsManager(path), SettingsManager(path)
            first.set('DEVICE_NAME', '测试耳机')
            second.set('AUTO_CONNECT_ENABLED', True)
            self.assertEqual(first.get('DEVICE_NAME'), '测试耳机')
            self.assertTrue(first.get('AUTO_CONNECT_ENABLED'))

    def test_short_windows_file_sharing_conflict_is_retried(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'status.json'
            original = os.replace
            attempts = []
            def replace(source, target):
                attempts.append(1)
                if len(attempts) < 3:
                    raise PermissionError('temporary Windows sharing conflict')
                return original(source, target)
            with patch('settings_manager.os.replace', side_effect=replace):
                write_json(path, {'state': 'connected'})
            self.assertIn('connected', path.read_text(encoding='utf-8'))
            self.assertEqual(len(attempts), 3)


if __name__ == '__main__':
    unittest.main()
