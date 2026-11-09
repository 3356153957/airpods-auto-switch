"""Inspect playback only: exclude microphones, system sounds and muted sessions."""
import logging
import threading
import comtypes
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
from pycaw.api.audiopolicy import IAudioSessionControl2, IAudioSessionManager2
from pycaw.constants import EDataFlow
from pycaw.utils import AudioSession
from settings_manager import settings
from audio_endpoints import render_endpoints

log = logging.getLogger(__name__)


def eligible_session(process_name, active, muted, volume, blacklist):
    system_hosts = {'shellexperiencehost.exe', 'startmenuexperiencehost.exe'}
    return bool(process_name and active and not muted and volume > 0 and process_name.casefold() not in blacklist | system_hosts)


class AudioMonitor:
    def __init__(self):
        self._local = threading.local()
        self.last_source = ''

    def _init_com(self):
        if not getattr(self._local, 'ready', False):
            comtypes.CoInitialize()
            self._local.ready = True

    def get_peak_level(self):
        self._init_com()
        peak = 0.0
        source = ''
        cfg = settings.snapshot()
        blacklist = {p.strip().casefold() for p in cfg['APP_BLACKLIST']}
        try:
            for device in render_endpoints():
                try:
                    manager = device.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
                    sessions = manager.GetSessionEnumerator()
                    for index in range(sessions.GetCount()):
                        try:
                            session = AudioSession(sessions.GetSession(index).QueryInterface(IAudioSessionControl2))
                            process = session.Process
                            name = process.name() if process else None
                            volume = session.SimpleAudioVolume
                            if not eligible_session(name, session.State == 1, volume.GetMute(), volume.GetMasterVolume(), blacklist):
                                continue
                            value = session._ctl.QueryInterface(IAudioMeterInformation).GetPeakValue()
                            if value > peak:
                                peak, source = value, name
                        except Exception:
                            continue
                except Exception:
                    log.debug('Playback endpoint is transitioning', exc_info=True)
        except Exception:
            log.warning('Cannot inspect Windows playback', exc_info=True)
        self.last_source = source
        return peak

    def is_audio_playing(self):
        return self.get_peak_level() > float(settings.get('AUDIO_THRESHOLD', 0.001))

    def cleanup(self):
        if getattr(self._local, 'ready', False):
            self._local.ready = False
            comtypes.CoUninitialize()
