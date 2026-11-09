# Third-party notices

## Upstream source

This repository is a GitHub fork of [DvivekD/airpods-auto-switch](https://github.com/DvivekD/airpods-auto-switch), based on commit `77535fdcfad3f2ea6b07fee2bf2989b145878622`. Original authorship and history are preserved. The upstream repository did not include a root license as checked on 2026-11-09. No MIT or other blanket license is asserted over that upstream work by this fork.

## BluetoothDevicePairing

`vendor/BluetoothDevicePairing.exe` is the unmodified Windows tool from [PolarGoose/BluetoothDevicePairing v12.0](https://github.com/PolarGoose/BluetoothDevicePairing/releases/tag/v12.0), by PolarGoose. It is used to connect/disconnect an already paired Bluetooth audio device.

License: MIT, Copyright (c) 2020 PolarGoose. Full text: [vendor/BluetoothDevicePairing.LICENSE.txt](vendor/BluetoothDevicePairing.LICENSE.txt). The same notice is included next to the application executable.

## Python runtime and libraries

Windows release packages include Python, Tcl/Tk, CustomTkinter, Pillow, pystray, pycaw, comtypes, psutil, darkdetect, packaging, six and the PyInstaller bootloader. Their installed license and notice files are copied into the release's `licenses/` directory by `tools/collect_licenses.py`. Their respective licenses apply to those components; bundling does not change their authorship or license terms.

AirPods is a trademark of Apple Inc. This project is not affiliated with Apple.
