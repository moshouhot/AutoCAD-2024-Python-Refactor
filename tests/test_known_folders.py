from __future__ import annotations

from pathlib import Path

from acad_portable.planner import _desktop_folder


def test_desktop_folder_falls_back_to_profile_off_windows() -> None:
    user = Path("/home/tester")
    assert _desktop_folder(user, windows=False) == user / "Desktop"
