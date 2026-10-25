"""Hold a temporary QA image open without FILE_SHARE_DELETE for partial-failure checks."""

import argparse
import ctypes
import tempfile
import threading
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('ready', type=Path)
    args = parser.parse_args()
    source = args.image.resolve(strict=True)
    if not source.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise SystemExit('Only temporary QA files may be locked')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(source), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        args.ready.write_text('locked', encoding='ascii')
        threading.Event().wait()
    finally:
        kernel.CloseHandle(handle)


if __name__ == '__main__':
    main()
