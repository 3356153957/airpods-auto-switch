"""Connect a paired headset, then verify its actual Windows playback endpoint."""

import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import time
import sys
from pathlib import Path

from settings_manager import settings

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────
BLUETOOTH_MAX_NAME_SIZE   = 248
ERROR_SUCCESS             = 0
INVALID_HANDLE_VALUE      = wintypes.HANDLE(-1).value

# ── C Structures (for device discovery only) ───────────────────────────

class BLUETOOTH_ADDRESS(ctypes.Union):
    _fields_ = [
        ("ullLong", ctypes.c_ulonglong),
        ("rgBytes", ctypes.c_ubyte * 6),
    ]

class SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ("wYear",         ctypes.c_ushort),
        ("wMonth",        ctypes.c_ushort),
        ("wDayOfWeek",    ctypes.c_ushort),
        ("wDay",          ctypes.c_ushort),
        ("wHour",         ctypes.c_ushort),
        ("wMinute",       ctypes.c_ushort),
        ("wSecond",       ctypes.c_ushort),
        ("wMilliseconds", ctypes.c_ushort),
    ]

class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize",          ctypes.c_ulong),
        ("Address",         BLUETOOTH_ADDRESS),
        ("ulClassofDevice", ctypes.c_ulong),
        ("fConnected",      wintypes.BOOL),
        ("fRemembered",     wintypes.BOOL),
        ("fAuthenticated",  wintypes.BOOL),
        ("stLastSeen",      SYSTEMTIME),
        ("stLastUsed",      SYSTEMTIME),
        ("szName",          ctypes.c_wchar * BLUETOOTH_MAX_NAME_SIZE),
    ]

    def __init__(self):
        super().__init__()
        self.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)

class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize",              ctypes.c_ulong),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered",    wintypes.BOOL),
        ("fReturnUnknown",       wintypes.BOOL),
        ("fReturnConnected",     wintypes.BOOL),
        ("fIssueInquiry",        wintypes.BOOL),
        ("cTimeoutMultiplier",   ctypes.c_ubyte),
        ("hRadio",               wintypes.HANDLE),
    ]

    def __init__(self):
        super().__init__()
        self.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS)

class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong)]

    def __init__(self):
        super().__init__()
        self.dwSize = ctypes.sizeof(BLUETOOTH_FIND_RADIO_PARAMS)


# ── Load bthprops.cpl ─────────────────────────────────────────────────

try:
    _bth = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
except OSError:
    log.error("Could not load bthprops.cpl — is Bluetooth available?")
    _bth = None


def _bind_functions():
    if _bth is None:
        return

    _bth.BluetoothFindFirstRadio.restype  = wintypes.HANDLE
    _bth.BluetoothFindFirstRadio.argtypes = [
        ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS),
        ctypes.POINTER(wintypes.HANDLE),
    ]
    _bth.BluetoothFindRadioClose.restype  = wintypes.BOOL
    _bth.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]

    _bth.BluetoothFindFirstDevice.restype  = wintypes.HANDLE
    _bth.BluetoothFindFirstDevice.argtypes = [
        ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS),
        ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
    ]
    _bth.BluetoothFindNextDevice.restype  = wintypes.BOOL
    _bth.BluetoothFindNextDevice.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
    ]
    _bth.BluetoothFindDeviceClose.restype  = wintypes.BOOL
    _bth.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]


_bind_functions()


# ── BluetoothManager ──────────────────────────────────────────────────

class BluetoothManager:
    """Manages connection lifecycle for a paired Bluetooth audio device."""

    def __init__(self, device_name: str = None):
        self._device_name_override = device_name
        self._pnp_instance_id = None  # cached on first lookup

    @property
    def device_name(self):
        return self._device_name_override or settings.get("DEVICE_NAME", "AirPods")

    # ── Public API ────────────────────────────────────────────────────

    @staticmethod
    def _normalize(name):
        return (
            name.lower()
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201C", '"')
            .replace("\u201D", '"')
        )

    def is_available(self) -> bool:
        return _bth is not None

    def find_device(self) -> "BLUETOOTH_DEVICE_INFO | None":
        """Search paired/remembered devices for the target by name."""
        if not self.is_available():
            return None

        radio = self._get_radio()
        if radio is None:
            return None

        try:
            search_params = BLUETOOTH_DEVICE_SEARCH_PARAMS()
            search_params.fReturnAuthenticated = True
            search_params.fReturnRemembered    = True
            search_params.fReturnConnected     = True
            search_params.fReturnUnknown       = False
            search_params.fIssueInquiry        = False
            search_params.cTimeoutMultiplier   = 0
            search_params.hRadio               = radio

            device_info = BLUETOOTH_DEVICE_INFO()
            search_handle = _bth.BluetoothFindFirstDevice(
                ctypes.byref(search_params), ctypes.byref(device_info)
            )

            if not search_handle or search_handle == INVALID_HANDLE_VALUE:
                log.debug("No Bluetooth devices found.")
                return None

            try:
                while True:
                    name = device_info.szName
                    if self._normalize(name) == self._normalize(self.device_name):
                        log.debug(f"Target device found: {name} (connected={bool(device_info.fConnected)})")
                        return device_info

                    device_info = BLUETOOTH_DEVICE_INFO()
                    if not _bth.BluetoothFindNextDevice(search_handle, ctypes.byref(device_info)):
                        break
            finally:
                _bth.BluetoothFindDeviceClose(search_handle)

        finally:
            ctypes.windll.kernel32.CloseHandle(radio)

        log.debug(f"Device '{self.device_name}' not found among paired devices.")
        return None

    def is_connected(self) -> bool:
        return self.active_endpoint() is not None

    def active_endpoint(self):
        from audio_endpoints import find_active_endpoint
        return find_active_endpoint(self._normalize(self.device_name), self._normalize)

    def is_default_output(self):
        from audio_endpoints import default_output_name
        try:
            return self._normalize(self.device_name) in self._normalize(default_output_name())
        except Exception:
            return False

    @staticmethod
    def paired_devices():
        params = BLUETOOTH_DEVICE_SEARCH_PARAMS()
        params.fReturnAuthenticated = True
        params.fReturnRemembered = True
        info = BLUETOOTH_DEVICE_INFO()
        if not _bth:
            return []
        handle = _bth.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
        if not handle or handle == INVALID_HANDLE_VALUE:
            return []
        names = []
        try:
            while True:
                if 'airpods' in info.szName.casefold():
                    names.append(info.szName)
                info = BLUETOOTH_DEVICE_INFO()
                if not _bth.BluetoothFindNextDevice(handle, ctypes.byref(info)):
                    break
        finally:
            _bth.BluetoothFindDeviceClose(handle)
        return sorted(set(names))

    def _get_bttools_exe(self) -> str:
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        return str(base / 'vendor' / 'BluetoothDevicePairing.exe')

    def connect(self, cancel=None, automatic=False) -> bool:
        """Connect AirPods using BluetoothDevicePairing CLI tool."""
        mac = self._get_mac_address()
        if not mac:
            log.warning("Cannot connect: Device MAC not found.")
            return False

        exe = self._get_bttools_exe()
        if not Path(exe).is_file():
            log.error('Bluetooth tool missing: %s', exe)
            return False
        
        log.info(f"Connecting {self.device_name} (MAC: {mac})...")
        try:
            if not self.is_connected():
                result = subprocess.run(
                    [exe, 'pair-by-mac', '--mac', mac, '--type', 'Bluetooth'],
                    capture_output=True, text=True, timeout=12,
                    creationflags=0x08000000,
                )
                log.info('Connection tool exit=%s: %s %s', result.returncode, result.stdout.strip(), result.stderr.strip())
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if cancel and cancel.is_set():
                    return False
                if automatic and not settings.get('AUTO_CONNECT_ENABLED', False):
                    return False
                endpoint = self.active_endpoint()
                if endpoint:
                    from pycaw.pycaw import AudioUtilities
                    from pycaw.constants import ERole
                    # Only playback defaults; leave the user's microphone selection alone.
                    AudioUtilities.SetDefaultDevice(endpoint.id, [ERole.eConsole, ERole.eMultimedia])
                    if self.is_default_output():
                        log.info('Verified active AirPods playback endpoint and default output.')
                        return True
                if cancel:
                    cancel.wait(0.35)
                else:
                    time.sleep(0.35)
            log.warning('No usable AirPods playback endpoint after connection attempt.')
            return False
        except Exception as e:
            log.error(f"Connect exception: {e}")
            return False

    def disconnect(self, cancel=None) -> bool:
        """Disconnect AirPods using BluetoothDevicePairing CLI tool."""
        if not self.is_connected():
            return True
        mac = self._get_mac_address()
        if not mac:
            log.warning("Cannot disconnect: Device MAC not found.")
            return False

        exe = self._get_bttools_exe()
        
        log.info(f"Disconnecting {self.device_name} (MAC: {mac})...")
        try:
            result = subprocess.run(
                [exe, "disconnect-bluetooth-audio-device-by-mac", "--mac", mac, "--type", "Bluetooth"],
                capture_output=True, text=True, timeout=15,
                creationflags=0x08000000
            )
            log.info('Disconnect tool exit=%s: %s %s', result.returncode, result.stdout.strip(), result.stderr.strip())
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if not self.is_connected():
                    return True
                if cancel and cancel.wait(0.35):
                    return False
                if cancel is None:
                    time.sleep(0.35)
            return False
        except Exception as e:
            log.error(f"Disconnect exception: {e}")
            return False

    # ── Internal ──────────────────────────────────────────────────────

    def _get_mac_address(self) -> str:
        device = self.find_device()
        if not device:
            return None
        bytes_array = list(device.Address.rgBytes)
        hex_mac = ":".join(f"{b:02X}" for b in reversed(bytes_array))
        return hex_mac
        
    def _get_radio(self) -> "wintypes.HANDLE | None":
        """Get a handle to the first Bluetooth radio."""
        params = BLUETOOTH_FIND_RADIO_PARAMS()
        radio_handle = wintypes.HANDLE()
        find_handle = _bth.BluetoothFindFirstRadio(
            ctypes.byref(params), ctypes.byref(radio_handle)
        )
        if not find_handle or find_handle == INVALID_HANDLE_VALUE:
            log.warning("No Bluetooth radio found.")
            return None
        _bth.BluetoothFindRadioClose(find_handle)
        return radio_handle.value
