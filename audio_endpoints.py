"""Small Core Audio views: do not copy complete device property stores each poll."""
from types import SimpleNamespace
from comtypes import GUID
from pycaw.pycaw import AudioUtilities
from pycaw.constants import EDataFlow, ERole
from pycaw.api.mmdeviceapi import PROPERTYKEY

_NAME = PROPERTYKEY(GUID('{A45C254E-DF1C-4EFD-8020-67D146A850E0}'), 14)
_DESCRIPTION = PROPERTYKEY(GUID('{A45C254E-DF1C-4EFD-8020-67D146A850E0}'), 2)


def render_endpoints():
    enumerator = AudioUtilities.GetDeviceEnumerator()
    collection = enumerator.EnumAudioEndpoints(EDataFlow.eRender.value, 1)
    for index in range(collection.GetCount()):
        yield collection.Item(index)


def endpoint_name(raw):
    store = raw.OpenPropertyStore(0)
    for key in (_NAME, _DESCRIPTION):
        value = store.GetValue(key)
        try:
            name = value.GetValue()
            if isinstance(name, str) and name:
                return name
        finally:
            value.clear()
    return ''


def find_active_endpoint(normalized_name, normalize):
    for raw in render_endpoints():
        name = endpoint_name(raw)
        if normalized_name in normalize(name):
            return SimpleNamespace(id=raw.GetId(), FriendlyName=name)
    return None


def default_output_name():
    enumerator = AudioUtilities.GetDeviceEnumerator()
    return endpoint_name(enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value))
