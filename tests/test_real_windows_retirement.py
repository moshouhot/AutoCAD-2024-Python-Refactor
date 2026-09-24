from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import acad_portable.real_windows as rw
from acad_portable.ops import WriteInstallState
from acad_portable.planner import InstallPlan

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


# --- G: destructive retirement must roll back on a later apply failure -------


def _fail_final_state_write(monkeypatch) -> None:
    """Make only the post-retirement ``complete`` state write fail."""
    real_write_state = rw._write_state

    def failing_write_state(path: Path, state) -> None:
        if state.get("status") == "complete":
            raise OSError("simulated final state write failure")
        real_write_state(path, state)

    monkeypatch.setattr(rw, "_write_state", failing_write_state)


def test_final_state_write_failure_rolls_back_retired_file(
    tmp_path: Path, monkeypatch
) -> None:
    """A failure after the unlink must restore bytes and ownership, not lose data."""
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

    _fail_final_state_write(monkeypatch)
    with pytest.raises(OSError, match="simulated final state write failure"):
        adapter.apply_plan(_no_file_plan(state_path))

    # The stale owned file is back, byte for byte.
    assert destination.read_bytes() == b"runtime-v1"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "failed"
    # Ownership is back with the file: it is not silently retired.
    owned = _entry(state["created_files"], destination)
    assert owned is not None and owned["installed_sha256"] == old_sha
    assert _entry(state["retired_files"], destination) is None

    # The restored file is still uninstallable as installer-owned.
    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.files_removed == 1
    assert not destination.exists()


def test_retirement_success_path_still_removes_and_records_removed(
    tmp_path: Path, monkeypatch
) -> None:
    """Without a failure the stale owned file is genuinely deleted."""
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

    adapter.apply_plan(_no_file_plan(state_path))

    assert not destination.exists()
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "complete"
    assert state["created_files"] == {}
    retired = _entry(state["retired_files"], destination)
    assert retired is not None and retired["action"] == "removed"


def test_retirement_rollback_restores_multiple_files_in_reverse(
    tmp_path: Path, monkeypatch
) -> None:
    """Several retired files are all restored; newest-deleted is restored first."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    first = tmp_path / "Apps64" / "first.dll"
    second = tmp_path / "Apps64" / "second.dll"
    state_path = tmp_path / "state.json"
    payloads = {
        "Program Files/first.dll": b"first-v1",
        "Program Files/second.dll": b"second-v1",
    }
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: payloads[op.member])
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "Program Files/first.dll", first, "zzz"),
            rw.InstallArchiveFile(archive, "Program Files/second.dll", second, "zzz"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(),
        metadata={},
    )
    adapter.apply_plan(plan)

    restored_order: list[str] = []
    real_atomic = rw._atomic_write_bytes

    def spy_atomic(path, payload):
        restored_order.append(Path(path).name)
        return real_atomic(path, payload)

    monkeypatch.setattr(rw, "_atomic_write_bytes", spy_atomic)
    _fail_final_state_write(monkeypatch)

    with pytest.raises(OSError, match="simulated final state write failure"):
        adapter.apply_plan(_no_file_plan(state_path))

    assert first.read_bytes() == b"first-v1"
    assert second.read_bytes() == b"second-v1"
    assert restored_order == ["second.dll", "first.dll"]
    state = rw._load_state(state_path)
    assert state is not None
    assert _entry(state["created_files"], first) is not None
    assert _entry(state["created_files"], second) is not None
    assert state["retired_files"] == {}


def test_retirement_rollback_failure_is_loud_and_keeps_original_context(
    tmp_path: Path, monkeypatch
) -> None:
    """A failing restore must not be reported as a clean rollback."""
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

    _fail_final_state_write(monkeypatch)

    def failing_restore(path, payload):
        raise OSError("simulated restore failure")

    monkeypatch.setattr(rw, "_atomic_write_bytes", failing_restore)

    with pytest.raises(RuntimeError, match="retired-file rollback failed") as excinfo:
        adapter.apply_plan(_no_file_plan(state_path))

    # Original failure stays attached as context for diagnosis.
    assert isinstance(excinfo.value.__cause__, OSError)
    assert "simulated final state write failure" in str(excinfo.value.__cause__)


def test_partial_retirement_failure_rolls_back_already_deleted_file(
    tmp_path: Path, monkeypatch
) -> None:
    """If retirement fails midway, files already unlinked are restored."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    first = tmp_path / "Apps64" / "first.dll"
    second = tmp_path / "Apps64" / "second.dll"
    state_path = tmp_path / "state.json"
    payloads = {
        "Program Files/first.dll": b"first-v1",
        "Program Files/second.dll": b"second-v1",
    }
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: payloads[op.member])
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "Program Files/first.dll", first, "zzz"),
            rw.InstallArchiveFile(archive, "Program Files/second.dll", second, "zzz"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(),
        metadata={},
    )
    adapter.apply_plan(plan)

    real_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self == second:
            raise OSError("simulated unlink failure")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)

    with pytest.raises(OSError, match="simulated unlink failure"):
        adapter.apply_plan(_no_file_plan(state_path))

    # Whichever file was deleted first is restored; nothing is lost.
    assert first.read_bytes() == b"first-v1"
    assert second.read_bytes() == b"second-v1"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "failed"
    assert _entry(state["created_files"], first) is not None
    assert _entry(state["created_files"], second) is not None


# --- P2-1: non-file replacement at an owned destination is a conflict --------


def test_uninstall_conflicts_when_owned_file_replaced_by_directory(
    tmp_path: Path, monkeypatch
) -> None:
    """An external directory at an owned path is a conflict, not a silent no-op."""
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

    # Replace the owned regular file with a directory holding unrelated data.
    destination.unlink()
    destination.mkdir()
    (destination / "external.txt").write_text("external", encoding="utf-8")

    report = adapter.uninstall(state_path)

    assert report.conflicts != ()
    assert report.files_removed == 0
    assert destination.is_dir()
    assert (destination / "external.txt").read_text(encoding="utf-8") == "external"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "uninstall_conflicts"


def test_uninstall_genuinely_missing_owned_file_is_not_a_conflict(
    tmp_path: Path, monkeypatch
) -> None:
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

    destination.unlink()

    report = adapter.uninstall(state_path)

    assert report.conflicts == ()
    assert report.files_removed == 0
    assert not state_path.exists()
