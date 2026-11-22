"""On Windows, put the interpreter's conda ``Library/bin`` on the DLL search path before PyBullet loads."""
import os
import sys
from pathlib import Path

_dll_handles = []
if os.name == 'nt':
    directory = Path(sys.prefix) / 'Library/bin'
    if directory.exists():
        _dll_handles.append(os.add_dll_directory(str(directory)))
