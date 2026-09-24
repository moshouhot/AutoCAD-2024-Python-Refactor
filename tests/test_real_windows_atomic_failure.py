from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import acad_portable.real_windows as rw
from acad_portable.ops import (
    EnsureRegistryKey,
    InstallArchiveFile,
    SetRegistryValue,
    WriteInstallState,
)
from acad_portable.planner import InstallPlan

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


def test_archive_preflight_failure_happens_before_registry_and_state_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_CURRENT_USER\SOFTWARE\PreflightOrder"
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "runtime.dll"
    state_path = tmp_path / "state.json"

    def fail_read(_operation):
        raise RuntimeError("bad password")

    monkeypatch.setattr(rw, "_read_archive_member", fail_read)
    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "v1"),
            InstallArchiveFile(
                archive,
                "Program Files/runtime.dll",
                destination,
                "bad-password",
            ),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(),
        metadata={},
    )

    with pytest.raises(RuntimeError, match="bad password"):
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(plan)

    assert key not in memory.keys
    assert (key, "Setting") not in memory.values
    assert not destination.exists()
    assert not state_path.exists()


def test_archive_preflight_failure_does_not_rewrite_existing_state(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "runtime.dll"
    state_path = tmp_path / "state.json"
    existing_state = rw._new_state()
    existing_state["status"] = "complete"
    existing_state["install_payload"] = {"version": "existing"}
    rw._write_state(state_path, existing_state)
    before = state_path.read_bytes()

    def fail_read(_operation):
        raise RuntimeError("corrupt archive")

    monkeypatch.setattr(rw, "_read_archive_member", fail_read)
    plan = InstallPlan(
        operations=(
            InstallArchiveFile(
                archive,
                "Program Files/runtime.dll",
                destination,
                "password",
            ),
            WriteInstallState(state_path, {"version": "new"}),
        ),
        warnings=(),
        metadata={},
    )

    with pytest.raises(RuntimeError, match="corrupt archive"):
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(plan)

    assert state_path.read_bytes() == before
    assert not destination.exists()


def test_all_archive_members_preflight_before_first_destination_write(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    first_destination = tmp_path / "Apps64" / "first.dll"
    second_destination = tmp_path / "Apps64" / "second.dll"
    state_path = tmp_path / "state.json"
    reads: list[str] = []

    def read_member(operation: InstallArchiveFile) -> bytes:
        reads.append(operation.member)
        if operation.member.endswith("second.dll"):
            raise RuntimeError("second member missing")
        return b"first-payload"

    monkeypatch.setattr(rw, "_read_archive_member", read_member)
    plan = InstallPlan(
        operations=(
            InstallArchiveFile(
                archive,
                "Program Files/first.dll",
                first_destination,
                "password",
            ),
            InstallArchiveFile(
                archive,
                "Program Files/second.dll",
                second_destination,
                "password",
            ),
            WriteInstallState(state_path, {}),
        ),
        warnings=(),
        metadata={},
    )

    with pytest.raises(RuntimeError, match="second member missing"):
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(plan)

    assert reads == ["Program Files/first.dll", "Program Files/second.dll"]
    assert not first_destination.exists()
    assert not second_destination.exists()
    assert not state_path.exists()


def test_archive_preflight_cache_reads_each_operation_once_and_refreshes_next_apply(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_CURRENT_USER\SOFTWARE\PreflightSuccess"
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    first_destination = tmp_path / "Apps64" / "first.dll"
    second_destination = tmp_path / "Apps64" / "second.dll"
    state_path = tmp_path / "state.json"
    payloads = {
        "Program Files/first.dll": b"first-v1",
        "Program Files/second.dll": b"second-v1",
    }
    events: list[str] = []
    reads: list[str] = []

    def read_member(operation: InstallArchiveFile) -> bytes:
        reads.append(operation.member)
        events.append(f"read:{operation.member}")
        return payloads[operation.member]

    real_write_state = rw._write_state

    def spy_write_state(path: Path, state) -> None:
        events.append("state-write")
        real_write_state(path, state)

    real_set_value = rw._set_registry_value

    def spy_set_value(operation: SetRegistryValue) -> None:
        events.append("registry-write")
        real_set_value(operation)

    monkeypatch.setattr(rw, "_read_archive_member", read_member)
    monkeypatch.setattr(rw, "_write_state", spy_write_state)
    monkeypatch.setattr(rw, "_set_registry_value", spy_set_value)

    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "portable"),
            InstallArchiveFile(
                archive,
                "Program Files/first.dll",
                first_destination,
                "password",
            ),
            InstallArchiveFile(
                archive,
                "Program Files/second.dll",
                second_destination,
                "password",
            ),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(),
        metadata={},
    )
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(plan)

    expected_reads = ["Program Files/first.dll", "Program Files/second.dll"]
    assert reads == expected_reads
    assert events[:2] == [f"read:{member}" for member in expected_reads]
    assert events.index("state-write") >= 2
    assert events.index("registry-write") >= 2
    assert first_destination.read_bytes() == b"first-v1"
    assert second_destination.read_bytes() == b"second-v1"
    state = rw._load_state(state_path)
    assert state is not None
    first_entry = _entry(state["created_files"], first_destination)
    second_entry = _entry(state["created_files"], second_destination)
    assert first_entry is not None
    assert second_entry is not None
    assert first_entry["installed_sha256"] == hashlib.sha256(b"first-v1").hexdigest()
    assert second_entry["installed_sha256"] == hashlib.sha256(b"second-v1").hexdigest()

    payloads["Program Files/first.dll"] = b"first-v2"
    payloads["Program Files/second.dll"] = b"second-v2"
    events.clear()
    adapter.apply_plan(plan)

    assert reads == expected_reads + expected_reads
    assert events[:2] == [f"read:{member}" for member in expected_reads]
    assert first_destination.read_bytes() == b"first-v2"
    assert second_destination.read_bytes() == b"second-v2"
    state = rw._load_state(state_path)
    assert state is not None
    first_entry = _entry(state["created_files"], first_destination)
    second_entry = _entry(state["created_files"], second_destination)
    assert first_entry is not None
    assert second_entry is not None
    assert first_entry["installed_sha256"] == hashlib.sha256(b"first-v2").hexdigest()
    assert second_entry["installed_sha256"] == hashlib.sha256(b"second-v2").hexdigest()


def test_archive_destination_conflict_preflights_before_registry_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    """A strict destination conflict must fail before registry/state mutation.

    The conflicting archive op is placed *after* registry operations in the
    plan, so the preflight gate is the only thing that can prevent the registry
    backend from being touched.
    """
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_CURRENT_USER\SOFTWARE\DestinationPreflight"
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "runtime.dll"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"external-version")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "v1"),
            InstallArchiveFile(
                archive, "Program Files/runtime.dll", destination, "zzz"
            ),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(),
        metadata={},
    )

    with pytest.raises(RuntimeError, match="refusing to overwrite existing shared file"):
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(plan)

    # No registry mutation, no state file, and the external file is intact.
    assert key not in memory.keys
    assert (key, "Setting") not in memory.values
    assert not state_path.exists()
    assert destination.read_bytes() == b"external-version"


def test_archive_destination_reuse_existing_passes_preflight(
    tmp_path: Path, monkeypatch
) -> None:
    """An unowned different file with ``reuse_existing`` is not a preflight conflict."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "Common Files" / "runtime.dll"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"external-version")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

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

    assert destination.read_bytes() == b"external-version"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}


# --- H: Windows parent-junction race is closed by the directory-chain lock ---


_win_only = pytest.mark.skipif(os.name != "nt", reason="Windows filesystem semantics")


@_win_only
def test_atomic_write_blocks_parent_rename_between_check_and_replace(
    tmp_path: Path, monkeypatch
) -> None:
    """A concurrent parent rename at replace time must fail, not redirect the write."""
    parent = tmp_path / "Apps64"
    parent.mkdir()
    destination = parent / "AcVba.arx"
    moved_parent = tmp_path / "moved-Apps64"
    real_replace = rw.os.replace
    observed: list[str] = []

    def rename_attempting_replace(src, dst):
        if Path(dst) == destination:
            try:
                os.rename(parent, moved_parent)
            except OSError as exc:
                observed.append(f"blocked:{exc.winerror}")
            else:
                observed.append("renamed")
        return real_replace(src, dst)

    monkeypatch.setattr(rw.os, "replace", rename_attempting_replace)

    rw._atomic_write_bytes(destination, b"payload")

    # The parent-chain handles withhold FILE_SHARE_DELETE, so the rename is a
    # sharing violation rather than a silent redirection.
    assert observed == ["blocked:32"], observed
    assert destination.read_bytes() == b"payload"
    assert not (moved_parent / "AcVba.arx").exists()
    assert not list(parent.glob("*.tmp"))


@_win_only
def test_atomic_write_blocks_higher_ancestor_rename(
    tmp_path: Path, monkeypatch
) -> None:
    """An ancestor above the immediate parent is locked as well."""
    top = tmp_path / "top"
    parent = top / "Apps64"
    parent.mkdir(parents=True)
    destination = parent / "AcVba.arx"
    moved_top = tmp_path / "moved-top"
    real_replace = rw.os.replace
    observed: list[str] = []

    def rename_attempting_replace(src, dst):
        if Path(dst) == destination:
            try:
                os.rename(top, moved_top)
            except OSError as exc:
                observed.append(f"blocked:{exc.winerror}")
            else:
                observed.append("renamed")
        return real_replace(src, dst)

    monkeypatch.setattr(rw.os, "replace", rename_attempting_replace)

    rw._atomic_write_bytes(destination, b"payload")

    assert observed == ["blocked:32"], observed
    assert destination.read_bytes() == b"payload"
    assert not (moved_top / "Apps64" / "AcVba.arx").exists()


@_win_only
def test_atomic_write_fails_closed_on_reparse_parent(tmp_path: Path) -> None:
    """A junction/symlink parent is refused and no payload is written."""
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    link_parent = tmp_path / "link-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        rw._create_junction(link_parent, real_parent)

    with pytest.raises(RuntimeError, match="reparse"):
        rw._atomic_write_bytes(link_parent / "AcVba.arx", b"payload")

    assert not (real_parent / "AcVba.arx").exists()
    assert not list(real_parent.glob("*.tmp"))


@_win_only
def test_atomic_write_releases_directory_handles_on_success_and_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """Held directory handles are always closed, so the parent stays renameable."""
    parent = tmp_path / "Apps64"
    parent.mkdir()
    destination = parent / "AcVba.arx"

    rw._atomic_write_bytes(destination, b"payload")
    os.rename(parent, tmp_path / "moved")
    os.rename(tmp_path / "moved", parent)

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(rw.os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        rw._atomic_write_bytes(destination, b"other")
    monkeypatch.undo()

    # No leaked handle: the parent can still be renamed after the failure.
    os.rename(parent, tmp_path / "moved2")
    os.rename(tmp_path / "moved2", parent)
    assert not list(parent.glob("*.tmp"))
