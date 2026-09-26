from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    if os.name != "nt":
        print("not-windows")
        return 1

    import winreg

    key_path = r"SOFTWARE\Microsoft\VBA"
    try:
        handle = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            key_path,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
    except FileNotFoundError:
        print("missing-key")
        return 0
    try:
        try:
            value, kind = winreg.QueryValueEx(handle, "Vbe71DllPath")
        except FileNotFoundError:
            print("missing-value")
            return 0
    finally:
        winreg.CloseKey(handle)

    print(f"kind={kind}")
    print(f"value={value}")
    path = Path(str(value))
    print(f"exists={path.is_file()}")
    try:
        print(f"resolved={path.resolve(strict=False)}")
    except OSError as exc:
        print(f"resolve_error={type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
