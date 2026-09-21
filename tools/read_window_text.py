from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes


user32 = ctypes.WinDLL("user32", use_last_error=True)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def pid_for(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def collect_children(parent: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    @EnumWindowsProc
    def callback(hwnd: int, _lparam: int) -> bool:
        rows.append(
            {
                "hwnd": int(hwnd),
                "class": class_name(hwnd),
                "text": window_text(hwnd),
            }
        )
        return True

    user32.EnumChildWindows(parent, callback, 0)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    args = parser.parse_args()

    windows: list[int] = []

    @EnumWindowsProc
    def callback(hwnd: int, _lparam: int) -> bool:
        if pid_for(hwnd) == args.pid:
            windows.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    for hwnd in windows:
        print(f"HWND={hwnd} CLASS={class_name(hwnd)!r} TEXT={window_text(hwnd)!r}")
        for child in collect_children(hwnd):
            if child["text"] or child["class"]:
                print(
                    f"  CHILD={child['hwnd']} CLASS={child['class']!r} "
                    f"TEXT={child['text']!r}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
