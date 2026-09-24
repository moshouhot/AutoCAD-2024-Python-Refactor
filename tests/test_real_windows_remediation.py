from __future__ import annotations

import os
from pathlib import Path

import acad_portable.real_windows as rw
from acad_portable.ops import EnsureRegistryKey, SetRegistryValue, WriteInstallState
from acad_portable.planner import InstallPlan

from test_real_windows_journal import RegistryMemory, patch_registry_backend

import ntpath


def _canon_registry(key: str, name: str) -> str:
    """Local canonical registry identity (mirrors production semantics)."""
    return key.rstrip("\\").casefold() + "\u0000" + name.casefold()


def _entry(mapping: dict, path) -> dict | None:
    """Local host-independent lookup into a raw-path-keyed journal map."""
    wanted = ntpath.normpath(str(path).replace("/", "\\")).casefold()
    for key, value in mapping.items():
        if ntpath.normpath(str(key).replace("/", "\\")).casefold() == wanted:
            return value
    return None



def _archive_plan(
    state_path: Path,
    archive: Path,
    member: str,
    destination: Path,
    *,
    reuse_existing: bool = False,
    version: int = 1,
) -> InstallPlan:
    return InstallPlan(
        operations=(
            rw.InstallArchiveFile(
                archive,
                member,
                destination,
                "zzz",
                reuse_existing=reuse_existing,
            ),
            WriteInstallState(state_path, {"version": version}),
        ),
        warnings=(),
        metadata={},
    )


def _no_file_plan(state_path: Path, version: int = 2) -> InstallPlan:
    return InstallPlan(
        operations=(WriteInstallState(state_path, {"version": version}),),
        warnings=(),
        metadata={},
    )


# --- C: registry identity is case-insensitive -------------------------------


def test_registry_identity_case_insensitive_upgrade_keeps_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    """A casing-only plan change must not retire/restore/delete the value."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    lower_key = r"hkey_local_machine\software\autodesk\owned"
    upper_key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    memory.keys.add(upper_key)
    memory.values[(upper_key, "Setting")] = {"type": 1, "data": "before"}
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(
        InstallPlan(
            operations=(
                EnsureRegistryKey(upper_key),
                SetRegistryValue(upper_key, "Setting", "sz", "installed-v1"),
                WriteInstallState(state_path, {"version": 1}),
            ),
            warnings=(),
            metadata={},
        )
    )
    # Second plan differs only by key/value casing.
    adapter.apply_plan(
        InstallPlan(
            operations=(
                EnsureRegistryKey(lower_key),
                SetRegistryValue(lower_key, "setting", "sz", "installed-v2"),
                WriteInstallState(state_path, {"version": 2}),
            ),
            warnings=(),
            metadata={},
        )
    )

    state = rw._load_state(state_path)
    assert state is not None
    identity = _canon_registry(upper_key, "Setting")
    assert identity in state["registry_values"]
    assert state["registry_values"][identity]["before"]["data"] == "before"
    assert state["registry_values"][identity]["installed"]["data"] == "installed-v2"
    assert state["registry_values"][identity].get("released") is not True
    assert identity not in state["retired_registry_values"]
    assert memory.values[(upper_key, "Setting")]["data"] == "installed-v2"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert memory.values[(upper_key, "Setting")]["data"] == "before"


def test_registry_journal_legacy_raw_identity_is_migrated(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = rw._new_state()
    state["registry_values"][
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned" + "\u0000Setting"
    ] = {
        "before": None,
        "installed": {"type": 1, "data": "installed"},
    }
    state["created_registry_keys"] = [r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"]
    rw._write_state(state_path, state)

    loaded = rw._load_state(state_path)

    assert loaded is not None
    canonical = _canon_registry(r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned", "Setting")
    assert canonical in loaded["registry_values"]
    assert (
        r"hkey_local_machine\software\autodesk\owned"
        in loaded["created_registry_keys"]
    )


def test_registry_journal_ambiguous_casefold_collision_is_rejected(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = rw._new_state()
    state["registry_values"][
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Owned" + "\u0000Setting"
    ] = {"before": None, "installed": {"type": 1, "data": "a"}}
    state["registry_values"][
        r"hkey_local_machine\software\owned" + "\u0000setting"
    ] = {"before": None, "installed": {"type": 1, "data": "b"}}
    rw._write_state(state_path, state)

    try:
        rw._load_state(state_path)
    except RuntimeError as exc:
        assert "ambiguous registry identity" in str(exc)
    else:
        raise AssertionError("expected ambiguous journal to be rejected")


def test_retired_registry_value_lookup_is_case_insensitive(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    state_path = tmp_path / "state.json"
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(
        InstallPlan(
            operations=(
                EnsureRegistryKey(key),
                SetRegistryValue(key, "Drop", "sz", "drop"),
                WriteInstallState(state_path, {"version": 1}),
            ),
            warnings=(),
            metadata={},
        )
    )
    # Re-apply with different casing for the remaining plan: "Drop" is gone.
    adapter.apply_plan(
        InstallPlan(
            operations=(
                EnsureRegistryKey(key.upper()),
                WriteInstallState(state_path, {"version": 2}),
            ),
            warnings=(),
            metadata={},
        )
    )

    state = rw._load_state(state_path)
    assert state is not None
    assert _canon_registry(key, "Drop") in state["retired_registry_values"]
    assert _canon_registry(key, "Drop") not in state["registry_values"]


# --- D: installer-owned archive upgrade ------------------------------------


def test_owned_strict_file_is_upgraded_on_new_payload(tmp_path: Path, monkeypatch) -> None:
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
    assert destination.read_bytes() == b"runtime-v1"

    payload["value"] = b"runtime-v2"
    adapter.apply_plan(
        _archive_plan(
            state_path, archive, "Program Files/AcVba.arx", destination, version=2
        )
    )

    assert destination.read_bytes() == b"runtime-v2"
    state = rw._load_state(state_path)
    assert state is not None
    entry = _entry(state["created_files"], destination)
    assert entry is not None
    assert entry["installed_sha256"] == rw._file_sha256(destination)


def test_owned_reuse_existing_file_is_upgraded_on_new_payload(
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
    adapter.apply_plan(
        _archive_plan(
            state_path,
            archive,
            "Program Files/Common Files/runtime.dll",
            destination,
            reuse_existing=True,
            version=2,
        )
    )

    assert destination.read_bytes() == b"runtime-v2"


def test_externally_modified_owned_file_is_not_overwritten(
    tmp_path: Path, monkeypatch
) -> None:
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
    destination.write_bytes(b"external-edit")
    payload["value"] = b"runtime-v2"

    try:
        adapter.apply_plan(
            _archive_plan(
                state_path, archive, "Program Files/AcVba.arx", destination, version=2
            )
        )
    except RuntimeError as exc:
        assert "refusing to overwrite" in str(exc)
    else:
        raise AssertionError("expected external change to be refused")

    assert destination.read_bytes() == b"external-edit"


def test_live_diff_reports_owned_upgrade(tmp_path: Path, monkeypatch) -> None:
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

    report = rw.inspect_live_diff(
        _archive_plan(
            state_path, archive, "Program Files/AcVba.arx", destination, version=2
        ),
        allow_non_windows_for_tests=True,
    )

    assert report.file_upgrade == 1
    assert report.file_conflict == 0
    assert destination.read_bytes() == b"runtime-v1"


def test_live_diff_treats_dangling_reparse_destination_as_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "dangling.dll"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    real_lexists = os.path.lexists

    def fake_lexists(path) -> bool:
        if Path(path) == destination:
            return True
        return real_lexists(path)

    monkeypatch.setattr(rw.os.path, "lexists", fake_lexists)

    report = rw.inspect_live_diff(
        _archive_plan(
            tmp_path / "state.json",
            archive,
            "Program Files/dangling.dll",
            destination,
        ),
        allow_non_windows_for_tests=True,
    )

    assert report.file_conflict == 1
    assert report.file_create == 0
    assert not real_lexists(destination)


# --- E: retire owned files removed from plan -------------------------------


def test_upgrade_removes_owned_file_dropped_from_plan(tmp_path: Path, monkeypatch) -> None:
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
    # VBA disabled -> the archive file op disappears from the plan.
    adapter.apply_plan(_no_file_plan(state_path))

    assert not destination.exists()
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}
    retired = state["retired_files"]
    assert len(retired) == 1
    entry = next(iter(retired.values()))
    assert entry["action"] == "removed"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.files_removed == 0


def test_upgrade_releases_externally_changed_owned_file(
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
    destination.write_bytes(b"external-edit")
    adapter.apply_plan(_no_file_plan(state_path))

    assert destination.read_bytes() == b"external-edit"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}
    entry = next(iter(state["retired_files"].values()))
    assert entry["action"] == "released_external"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.files_removed == 0
    assert destination.read_bytes() == b"external-edit"


def test_upgrade_releases_missing_owned_file(tmp_path: Path, monkeypatch) -> None:
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
    destination.unlink()
    adapter.apply_plan(_no_file_plan(state_path))

    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}
    entry = next(iter(state["retired_files"].values()))
    assert entry["action"] == "missing"


# --- F: atomic archive write + failure journal -----------------------------


def test_atomic_write_failure_leaves_no_partial_destination(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "AcVba.arx"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    def failing_replace(src, dst):
        # Only fail the archive destination; the journal's own atomic writes
        # must keep working so the failure path is observable.
        if Path(dst) == destination:
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    real_replace = rw.os.replace
    monkeypatch.setattr(rw.os, "replace", failing_replace)
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    try:
        adapter.apply_plan(
            _archive_plan(state_path, archive, "Program Files/AcVba.arx", destination)
        )
    except OSError as exc:
        assert "simulated replace failure" in str(exc)
    else:
        raise AssertionError("expected replace failure to propagate")

    assert not destination.exists()
    assert not destination.parent.exists() or list(destination.parent.iterdir()) == []
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}
    assert state["status"] == "failed"


def test_atomic_upgrade_failure_keeps_old_content_and_ownership(
    tmp_path: Path, monkeypatch
) -> None:
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
    before_state = rw._load_state(state_path)
    assert before_state is not None
    installed_before = _entry(before_state["created_files"], destination)

    def failing_replace(src, dst):
        if Path(dst) == destination:
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    real_replace = rw.os.replace
    monkeypatch.setattr(rw.os, "replace", failing_replace)
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
    installed_after = _entry(state["created_files"], destination)
    assert installed_after == installed_before
    assert state["status"] == "failed"


def test_failure_after_archive_write_is_journaled(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    destination = tmp_path / "Apps64" / "AcVba.arx"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    def boom(self, plan, state):
        raise RuntimeError("simulated reconcile failure")

    monkeypatch.setattr(
        rw.RealWindowsAdapter, "_reconcile_retired_registry_ownership", boom
    )
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    try:
        adapter.apply_plan(
            _archive_plan(state_path, archive, "Program Files/AcVba.arx", destination)
        )
    except RuntimeError as exc:
        assert "simulated reconcile failure" in str(exc)
    else:
        raise AssertionError("expected reconcile failure to propagate")

    state = rw._load_state(state_path)
    assert state is not None
    assert state["status"] == "failed"
    # The successful write is still journaled so the file can be rolled back.
    assert _entry(state["created_files"], destination) is not None


# --- G: reparse / symlink containment --------------------------------------


def test_parent_symlink_destination_is_refused(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    link_parent = tmp_path / "link-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")
    destination = link_parent / "runtime.dll"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    try:
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(
            _archive_plan(state_path, archive, "Program Files/runtime.dll", destination)
        )
    except RuntimeError as exc:
        assert "reparse point" in str(exc)
    else:
        raise AssertionError("expected parent symlink to be refused")

    assert not (real_parent / "runtime.dll").exists()
    assert not destination.exists()
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}


def test_destination_symlink_is_refused(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    target = tmp_path / "real-target.dll"
    target.write_bytes(b"original")
    destination = tmp_path / "link.dll"
    try:
        os.symlink(target, destination)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    try:
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(
            _archive_plan(state_path, archive, "Program Files/link.dll", destination)
        )
    except RuntimeError as exc:
        assert "reparse point" in str(exc)
    else:
        raise AssertionError("expected destination symlink to be refused")

    assert target.read_bytes() == b"original"


def test_reparse_ancestor_detection_uses_windows_attribute(
    tmp_path: Path, monkeypatch
) -> None:
    """Emulate a Windows junction: no symlink bit, only the reparse attribute."""
    import stat as stat_module

    parent = tmp_path / "junction-parent"
    parent.mkdir()
    destination = parent / "runtime.dll"
    real_lstat = rw.os.lstat

    def fake_lstat(path):
        if Path(path) == parent:
            # Minimal stand-in exposing only the attributes the guard reads.
            class _ReparseInfo:
                st_mode = stat_module.S_IFDIR
                st_file_attributes = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT

            return _ReparseInfo()
        return real_lstat(path)

    monkeypatch.setattr(rw.os, "lstat", fake_lstat)

    assert rw._has_reparse_ancestor(destination) is True
    try:
        rw._reject_reparse_path(destination)
    except RuntimeError as exc:
        assert "reparse point" in str(exc)
    else:
        raise AssertionError("expected reparse ancestor to be refused")


def test_uninstall_refuses_reparse_parent(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    destination = real_parent / "runtime.dll"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(state_path, archive, "Program Files/runtime.dll", destination)
    )

    link_parent = tmp_path / "link-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")
    # Swap the recorded raw path for one that traverses a symlink parent.
    state = rw._load_state(state_path)
    assert state is not None
    raw_key = next(iter(state["created_files"]))
    state["created_files"][str(link_parent / "runtime.dll")] = state[
        "created_files"
    ].pop(raw_key)
    rw._write_state(state_path, state)

    report = adapter.uninstall(state_path)

    assert report.files_removed == 0
    assert any("reparse point" in conflict for conflict in report.conflicts)
    assert destination.read_bytes() == b"runtime-v1"


def test_external_bytes_equal_to_new_payload_are_not_adopted_strict(
    tmp_path: Path, monkeypatch
) -> None:
    """Ownership is judged by the installed hash, not the wanted hash."""
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

    # External writer replaces the file with exactly the next payload bytes.
    payload["value"] = b"runtime-v2"
    destination.write_bytes(b"runtime-v2")

    try:
        adapter.apply_plan(
            _archive_plan(
                state_path, archive, "Program Files/AcVba.arx", destination, version=2
            )
        )
    except RuntimeError as exc:
        assert "refusing to overwrite" in str(exc)
    else:
        raise AssertionError("expected externally changed file to be refused")

    state = rw._load_state(state_path)
    assert state is not None
    entry = _entry(state["created_files"], destination)
    # Ownership is unchanged: the old installed hash is still recorded.
    assert entry is not None
    assert entry["installed_sha256"] != rw._file_sha256(destination)


def test_external_bytes_equal_to_new_payload_release_ownership_reuse(
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
    adapter.apply_plan(
        _archive_plan(
            state_path,
            archive,
            "Program Files/Common Files/runtime.dll",
            destination,
            reuse_existing=True,
            version=2,
        )
    )

    assert destination.read_bytes() == b"runtime-v2"
    state = rw._load_state(state_path)
    assert state is not None
    assert _entry(state["created_files"], destination) is None
    released = list(state["retired_files"].values())
    assert released and released[0]["action"] == "released_external"


def test_live_diff_treats_symlink_to_existing_file_as_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    target = tmp_path / "real.dll"
    target.write_bytes(b"runtime-v1")
    destination = tmp_path / "link.dll"
    try:
        os.symlink(target, destination)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    report = rw.inspect_live_diff(
        _archive_plan(tmp_path / "state.json", archive, "Program Files/link.dll", destination),
        allow_non_windows_for_tests=True,
    )

    assert report.file_conflict == 1
    assert report.file_same == 0
    assert report.file_create == 0


def test_live_diff_treats_absent_file_under_symlink_parent_as_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    link_parent = tmp_path / "link-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")
    destination = link_parent / "missing.dll"
    assert not destination.exists()
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")

    report = rw.inspect_live_diff(
        _archive_plan(
            tmp_path / "state.json", archive, "Program Files/missing.dll", destination
        ),
        allow_non_windows_for_tests=True,
    )

    assert report.file_conflict == 1
    assert report.file_create == 0


def test_retirement_releases_reparse_destination(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    destination = real_parent / "runtime.dll"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(state_path, archive, "Program Files/runtime.dll", destination)
    )

    link_parent = tmp_path / "link-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")
    state = rw._load_state(state_path)
    assert state is not None
    raw_key = next(iter(state["created_files"]))
    state["created_files"][str(link_parent / "runtime.dll")] = state[
        "created_files"
    ].pop(raw_key)
    rw._write_state(state_path, state)

    adapter.apply_plan(_no_file_plan(state_path))

    assert destination.read_bytes() == b"runtime-v1"
    state = rw._load_state(state_path)
    assert state is not None
    entry = next(iter(state["retired_files"].values()))
    assert entry["action"] == "released_reparse"


def test_uninstall_refuses_reparse_destination_itself(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive")
    target = tmp_path / "real.dll"
    target.write_bytes(b"runtime-v1")
    destination = tmp_path / "runtime.dll"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda op: b"runtime-v1")
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(
        _archive_plan(state_path, archive, "Program Files/runtime.dll", destination)
    )

    # Swap the owned regular file for a symlink to another file.
    destination.unlink()
    try:
        os.symlink(target, destination)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("host does not allow creating symlinks")

    report = adapter.uninstall(state_path)

    assert report.files_removed == 0
    assert any("reparse point" in conflict for conflict in report.conflicts)
    assert target.read_bytes() == b"runtime-v1"
