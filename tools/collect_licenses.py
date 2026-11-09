"""Copy the installed runtime's actual notices into the redistributable folder."""
import importlib.metadata as metadata
from pathlib import Path
import shutil
import sys


def collect(destination):
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    for name in ('comtypes', 'customtkinter', 'darkdetect', 'packaging', 'pillow', 'psutil',
                 'pycaw', 'pystray', 'six', 'pyinstaller'):
        distribution = metadata.distribution(name)
        found = 0
        for file in distribution.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in file.parts):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    output = target / f'{name}-{distribution.version}' / str(file)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
                    found += 1
        if not found:
            raise RuntimeError(f'No license files found for {name}')
    base = Path(sys.base_prefix)
    python_license = base / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python LICENSE.txt missing')
    shutil.copy2(python_license, target / 'Python-LICENSE.txt')
    for path in (base / 'tcl').glob('**/license.terms'):
        output = target / 'Tcl-Tk' / path.relative_to(base / 'tcl')
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, output)


if __name__ == '__main__':
    collect(sys.argv[1])
