from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path

import pytest

import acad_portable.real_windows as rw
from acad_portable.ops import WriteInstallState
from acad_portable.planner import InstallPlan

from test_real_windows_journal import RegistryMemory, patch_registry_backend
from test_real_windows_remediation import _archive_plan, _entry, _no_file_plan


_win_only = pytest.mark.skipif(os.name != "nt", reason="Windows handle semantics")


# --- Real Windows handle evidence -------------------------------------------


@_win_only
def test_delete_owned_file_blocks_replacement_while_handle_is_held(
    tmp_path: Path, monkeypatch
) -> None:
    """A same-name replacement during the locked read must fail, then succeed after."""
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    expected_sha = hashlib.sha256(b"payload-v1").hexdigest()
    replacement = tmp_path / "replacement.dll"
    replacement.write_bytes(b"external-replacement")

    real_read_all = rw._read_all_from_handle
    observed: list[str] = []

    def read_and_attempt_replace(kernel32, handle):
        # Fires inside the helper's locked-read window, with the target handle
        # open for DELETE and not sharing write/delete.
        try:
            os.replace(replacement, destination)
        except OSError as exc:
            observed.append(f"blocked:{exc.winerror}")
        else:
            observed.append("replaced")
        return real_read_all(kernel32, handle)

    monkeypatch.setattr(rw, "_read_all_from_handle", read_and_attempt_replace)

    result = rw._delete_owned_file_by_handle(destination, expected_sha)

    assert result.outcome == "removed"
    assert result.payload == b"payload-v1"
    # Windows reports a sharing violation (32) or access denied (5) depending
    # on which conflicting access right is denied first; either proves the
    # replacement was refused while the handle was held.
    assert observed in (["blocked:32"], ["blocked:5"]), observed
    assert not destination.exists()


@_win_only
def test_delete_owned_file_hash_mismatch_keeps_file_and_closes_handle(
    tmp_path: Path, monkeypatch
) -> None:
    """On hash mismatch the file is preserved and the handle is released."""
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    replacement = tmp_path / "replacement.dll"
    replacement.write_bytes(b"external-replacement")

    real_read_all = rw._read_all_from_handle
    observed: list[str] = []

    def read_and_attempt_replace(kernel32, handle):
        try:
            os.replace(replacement, destination)
        except OSError:
            observed.append("blocked")
        else:
            observed.append("replaced")
        return real_read_all(kernel32, handle)

    monkeypatch.setattr(rw, "_read_all_from_handle", read_and_attempt_replace)

    wrong_sha = hashlib.sha256(b"some-other-content").hexdigest()
    result = rw._delete_owned_file_by_handle(destination, wrong_sha)

    assert result.outcome == "external"
    assert result.reason == "hash mismatch"
    assert result.payload is None
    assert observed == ["blocked"]
    assert destination.read_bytes() == b"payload-v1"

    # The helper closed the handle, so the replacement now succeeds.
    monkeypatch.undo()
    os.replace(replacement, destination)
    assert destination.read_bytes() == b"external-replacement"


def test_delete_owned_file_metadata_error_propagates_and_preserves_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "Apps64" / "runtime.dll"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    expected = hashlib.sha256(b"payload-v1").hexdigest()
    real_lstat = rw.os.lstat

    def denied_lstat(path):
        if Path(path) == destination:
            raise PermissionError("simulated metadata denial")
        return real_lstat(path)

    monkeypatch.setattr(rw.os, "lstat", denied_lstat)

    with pytest.raises(PermissionError, match="simulated metadata denial"):
        rw._delete_owned_file_by_handle(destination, expected)

    assert destination.read_bytes() == b"payload-v1"


@_win_only
def test_delete_owned_file_missing_and_directory_are_classified(tmp_path: Path) -> None:
    missing = tmp_path / "Apps64" / "absent.dll"
    missing.parent.mkdir(parents=True)
    result = rw._delete_owned_file_by_handle(missing, None)
    assert result.outcome == "missing"

    directory = tmp_path / "Apps64" / "a-directory"
    directory.mkdir()
    result = rw._delete_owned_file_by_handle(directory, None)
    assert result.outcome == "external"
    assert result.reason == "non-file"
    assert directory.is_dir()


@_win_only
def test_delete_owned_file_without_recorded_hash_is_external(tmp_path: Path) -> None:
    """An existing file with no recorded hash must not be deleted."""
    destination = tmp_path / "Apps64" / "runtime.dll"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")

    result = rw._delete_owned_file_by_handle(destination, None)

    assert result.outcome == "external"
    assert destination.read_bytes() == b"payload-v1"


@_win_only
def test_delete_owned_file_missing_whole_parent_chain_is_missing(tmp_path: Path) -> None:
    """A removed parent directory must classify as missing, not raise."""
    import shutil

    destination = tmp_path / "Apps64" / "runtime.dll"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    shutil.rmtree(destination.parent)
    assert not destination.parent.exists()

    result = rw._delete_owned_file_by_handle(
        destination, hashlib.sha256(b"payload-v1").hexdigest()
    )

    assert result.outcome == "missing"


# --- Fake kernel32: API failure paths fail closed ---------------------------


class _FakeKernel32:
    """Scriptable stand-in for kernel32 covering the handle-deletion calls.

    The parent-chain lock also calls ``CreateFileW``/``GetFileInformationByHandle``
    for every directory above the target, so this fake recognises on-disk
    directories and reports them as directories instead of the scripted target
    attributes.  That keeps the real ``_locked_parent_chain`` logic exercised
    while the target handle stays scriptable.
    """

    def __init__(self, *, attributes: int = 0, reads: list[bytes] | None = None,
                 fail_info: bool = False, fail_read: bool = False,
                 fail_disposition: bool = False, fail_create: bool = False) -> None:
        self.attributes = attributes
        self.reads = list(reads or [])
        self.fail_info = fail_info
        self.fail_read = fail_read
        self.fail_disposition = fail_disposition
        self.fail_create = fail_create
        self.closed: list[int] = []
        self.disposition_calls = 0
        self._next_handle = 0x1234
        self._attrs: dict[int, int] = {}

    def CreateFileW(self, path, *args):
        is_directory = os.path.isdir(str(path))
        if self.fail_create and not is_directory:
            # A real sharing violation, not FILE_NOT_FOUND, so the helper must
            # fail closed at the target, not while locking an ancestor.
            ctypes.set_last_error(32)
            return rw._INVALID_HANDLE_VALUE
        handle = self._next_handle
        self._next_handle += 1
        self._attrs[handle] = (
            rw._FILE_ATTRIBUTE_DIRECTORY
            if is_directory
            else self.attributes
        )
        return handle

    def GetFileInformationByHandle(self, handle, info_ptr):
        attributes = self._attrs.get(handle, self.attributes)
        if self.fail_info and not (attributes & rw._FILE_ATTRIBUTE_DIRECTORY):
            ctypes.set_last_error(5)
            return 0
        info = ctypes.cast(info_ptr, ctypes.POINTER(rw._ByHandleFileInformation)).contents
        info.dwFileAttributes = attributes
        return 1

    def ReadFile(self, handle, buffer, size, read_ptr, overlapped):
        if self.fail_read:
            ctypes.set_last_error(5)
            return 0
        chunk = self.reads.pop(0) if self.reads else b""
        buffer[: len(chunk)] = chunk
        read_ptr._obj.value = len(chunk)
        return 1

    def SetFileInformationByHandle(self, handle, info_class, info_ptr, size):
        self.disposition_calls += 1
        if self.fail_disposition:
            ctypes.set_last_error(5)
            return 0
        return 1

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


def _patch_kernel32(monkeypatch, fake: _FakeKernel32) -> None:
    monkeypatch.setattr(rw, "_get_kernel32", lambda: fake)


@_win_only
def test_handle_read_failure_raises_and_closes_handle(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    fake = _FakeKernel32(fail_read=True)
    _patch_kernel32(monkeypatch, fake)

    with pytest.raises(OSError):
        rw._delete_owned_file_by_handle(destination, hashlib.sha256(b"payload-v1").hexdigest())

    assert fake.disposition_calls == 0
    assert destination.read_bytes() == b"payload-v1"
    # Every handle the helper opened (parent chain + target) was closed.
    assert len(fake.closed) == len(fake._attrs)


@_win_only
def test_handle_disposition_failure_raises_and_closes_handle(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    fake = _FakeKernel32(reads=[b"payload-v1", b""], fail_disposition=True)
    _patch_kernel32(monkeypatch, fake)

    with pytest.raises(OSError):
        rw._delete_owned_file_by_handle(destination, hashlib.sha256(b"payload-v1").hexdigest())

    assert fake.disposition_calls == 1
    assert destination.read_bytes() == b"payload-v1"
    assert len(fake.closed) == len(fake._attrs)


@_win_only
def test_handle_metadata_failure_raises_and_closes_handle(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    fake = _FakeKernel32(fail_info=True)
    _patch_kernel32(monkeypatch, fake)

    with pytest.raises(OSError):
        rw._delete_owned_file_by_handle(destination, None)

    assert destination.read_bytes() == b"payload-v1"


@_win_only
def test_handle_create_failure_raises_and_deletes_nothing(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    fake = _FakeKernel32(fail_create=True)
    _patch_kernel32(monkeypatch, fake)

    with pytest.raises(OSError):
        rw._delete_owned_file_by_handle(destination, None)

    # The target CreateFileW fails closed, so no delete was requested and the
    # file is untouched.  The ancestor lock handles opened by
    # ``_locked_parent_chain`` are expected to exist; every one of them must be
    # released, with no handle opened that was not closed and vice versa.
    assert fake.disposition_calls == 0
    assert sorted(fake.closed) == sorted(fake._attrs)
    assert len(fake.closed) == len(fake._attrs)
    assert destination.read_bytes() == b"payload-v1"


@_win_only
def test_handle_reparse_attribute_is_external_and_closes_handle(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    fake = _FakeKernel32(attributes=rw._FILE_ATTRIBUTE_REPARSE_POINT)
    _patch_kernel32(monkeypatch, fake)

    result = rw._delete_owned_file_by_handle(destination, None)

    assert result.outcome == "external"
    assert result.reason == "reparse"
    assert destination.read_bytes() == b"payload-v1"
    assert len(fake.closed) == len(fake._attrs)


@_win_only
def test_handle_matching_hash_deletes_and_returns_exact_payload(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "Apps64" / "AcVba.arx"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"payload-v1")
    fake = _FakeKernel32(reads=[b"pay", b"load-v1", b""])
    _patch_kernel32(monkeypatch, fake)
    expected = hashlib.sha256(b"payload-v1").hexdigest()

    result = rw._delete_owned_file_by_handle(destination, expected)

    assert result.outcome == "removed"
    assert result.payload == b"payload-v1"
    assert fake.disposition_calls == 1
    assert len(fake.closed) == len(fake._attrs)
    # The fake never touched the real file; the adapter's real delete is proven
    # separately by the Windows-only tests above.
    assert destination.read_bytes() == b"payload-v1"


# --- Uninstall / retirement fail-closed integration -------------------------


def test_uninstall_operational_failure_retains_ownership(tmp_path: Path, monkeypatch) -> None:
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

    def failing_delete(path, expected_sha256):
        raise OSError("sharing violation")

    monkeypatch.setattr(rw, "_delete_owned_file_by_handle", failing_delete)

    report = adapter.uninstall(state_path)

    assert len(report.conflicts) == 1
    assert "could not be removed" in report.conflicts[0]
    assert destination.read_bytes() == b"runtime-v1"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "uninstall_conflicts"
    assert _entry(state["created_files"], destination) is not None


def test_retirement_operational_failure_propagates_and_keeps_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "AcVba.arx"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(state_path, archive, "Program Files/AcVba.arx", destination)
    )

    def failing_delete(path, expected_sha256):
        raise OSError("sharing violation during retirement")

    monkeypatch.setattr(rw, "_delete_owned_file_by_handle", failing_delete)

    with pytest.raises(OSError, match="sharing violation during retirement"):
        adapter.apply_plan(_no_file_plan(state_path))

    assert destination.read_bytes() == b"runtime-v1"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "failed"
    # Ownership was never silently released.
    assert _entry(state["created_files"], destination) is not None
