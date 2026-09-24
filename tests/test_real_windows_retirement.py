from __future__ import annotations

import os
from pathlib import Path

import acad_portable.real_windows as rw

from test_real_windows_journal import RegistryMemory, patch_registry_backend
from test_real_windows_remediation import (
    _archive_plan,
    _entry,
    _no_file_plan,
)


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")


def test_retirement_releases_symlink_destination_itself(
    tmp_path: Path, monkeypatch
) -> None:
    """A symlink swapped in at the destination must be released, not hashed/deleted."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "runtime.dll"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(state_path, archive, "Program Files/runtime.dll", destination)
    )

    # Replace the owned regular file with a symlink to an unrelated target.
    destination.unlink()
    target = tmp_path / "unrelated.dll"
    target.write_bytes(b"unrelated")
    _symlink_or_skip(destination, target)

    adapter.apply_plan(_no_file_plan(state_path))

    assert target.read_bytes() == b"unrelated"
    assert os.path.islink(destination)
    state = rw._load_state(state_path)
    assert state is not None
    assert _entry(state["created_files"], destination) is None
    retired = _entry(state["retired_files"], destination)
    assert retired is not None and retired["action"] == "released_reparse"


def test_live_diff_matches_apply_for_external_bytes_equal_to_payload_strict(
    tmp_path: Path, monkeypatch
) -> None:
    """Diff must report conflict where apply would refuse (strict, external==new)."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "AcVba.arx"
    state_path = tmp_path / "state.json"
    payload = {"value": b"runtime-v1"}
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: payload["value"])
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(state_path, archive, "Program Files/AcVba.arx", destination)
    )
    payload["value"] = b"runtime-v2"
    destination.write_bytes(b"runtime-v2")

    report = rw.inspect_live_diff(
        _archive_plan(
            state_path, archive, "Program Files/AcVba.arx", destination, version=2
        ),
        allow_non_windows_for_tests=True,
    )

    assert report.file_conflict == 1
    assert report.file_same == 0
    assert report.file_upgrade == 0


def test_live_diff_matches_apply_for_external_bytes_equal_to_payload_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "Common Files" / "runtime.dll"
    state_path = tmp_path / "state.json"
    payload = {"value": b"runtime-v1"}
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: payload["value"])
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(
            state_path,
            archive,
            "Program Files/Common Files/runtime.dll",
            destination,
            reuse_existing=True,
        )
    )
    payload["value"] = b"runtime-v2"
    destination.write_bytes(b"runtime-v2")

    report = rw.inspect_live_diff(
        _archive_plan(
            state_path,
            archive,
            "Program Files/Common Files/runtime.dll",
            destination,
            reuse_existing=True,
            version=2,
        ),
        allow_non_windows_for_tests=True,
    )

    assert report.file_reuse == 1
    assert report.file_same == 0
    assert report.file_conflict == 0
