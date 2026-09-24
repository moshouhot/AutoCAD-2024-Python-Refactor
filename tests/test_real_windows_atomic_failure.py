from __future__ import annotations

import hashlib
import os
from pathlib import Path

import acad_portable.real_windows as rw

from test_real_windows_journal import RegistryMemory, patch_registry_backend
from test_real_windows_remediation import (
    _archive_plan,
    _entry,
    _no_file_plan,
)


def _fail_replace_for(destination: Path, monkeypatch) -> None:
    real_replace = rw.os.replace

    def failing_replace(src, dst):
        if Path(dst) == destination:
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(rw.os, "replace", failing_replace)


def test_atomic_create_failure_records_pending_hash_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed create still journals the intended hash for diagnosis."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "AcVba.arx"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    _fail_replace_for(destination, monkeypatch)

    try:
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(
            _archive_plan(state_path, archive, "Program Files/AcVba.arx", destination)
        )
    except OSError:
        pass
    else:
        raise AssertionError("expected replace failure to propagate")

    assert not destination.exists()
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "failed"
    assert _entry(state["created_files"], destination) is None
    pending = _entry(state["pending_files"], destination)
    assert pending is not None
    assert pending["installed_sha256"] == hashlib.sha256(b"runtime-v1").hexdigest()


def test_atomic_upgrade_failure_records_old_and_new_hash_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed upgrade keeps old ownership and records the new pending hash."""
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
    old_sha = hashlib.sha256(b"runtime-v1").hexdigest()
    new_sha = hashlib.sha256(b"runtime-v2").hexdigest()
    _fail_replace_for(destination, monkeypatch)
    payload["value"] = b"runtime-v2"

    try:
        adapter.apply_plan(
            _archive_plan(
                state_path, archive, "Program Files/AcVba.arx", destination, version=2
            )
        )
    except OSError:
        pass
    else:
        raise AssertionError("expected replace failure to propagate")

    assert destination.read_bytes() == b"runtime-v1"
    state = rw._load_state(state_path)
    assert state is not None
    owned = _entry(state["created_files"], destination)
    assert owned is not None and owned["installed_sha256"] == old_sha
    pending = _entry(state["pending_files"], destination)
    assert pending is not None and pending["installed_sha256"] == new_sha


def test_atomic_write_rechecks_reparse_before_replace(
    tmp_path: Path, monkeypatch
) -> None:
    """The guard is re-evaluated after the temp file is written.

    A parent swapped for a reparse point *after* the earlier checks but before
    ``os.replace`` must still be refused.  The swap is modelled by reporting
    the parent as a reparse point only once the same-directory temp file
    exists, which is exactly the window between flush/fsync and replace.
    """
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    parent = tmp_path / "Apps64"
    destination = parent / "AcVba.arx"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    real_is_reparse = rw._is_reparse_or_symlink

    def counting_is_reparse(path):
        if Path(path) == parent and parent.is_dir() and list(parent.glob("*.tmp")):
            return True
        return real_is_reparse(path)

    def guard_replace(src, dst):
        # The journal's own writes must keep working; only the archive
        # destination replace is forbidden here.
        if Path(dst) == destination:
            raise AssertionError("replace must not be reached with a reparse parent")
        return real_replace(src, dst)

    real_replace = rw.os.replace
    monkeypatch.setattr(rw, "_is_reparse_or_symlink", counting_is_reparse)
    monkeypatch.setattr(rw.os, "replace", guard_replace)

    try:
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(
            _archive_plan(state_path, archive, "Program Files/AcVba.arx", destination)
        )
    except RuntimeError as exc:
        assert "reparse point" in str(exc)
    else:
        raise AssertionError("expected reparse recheck to refuse the replace")

    assert not destination.exists()
    assert not list(parent.glob("*.tmp"))
