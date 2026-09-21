from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import acad_portable.real_windows as rw
from acad_portable.ops import EnsureRegistryKey, SetRegistryValue, WriteInstallState
from acad_portable.planner import InstallPlan


class RegistryMemory:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.values: dict[tuple[str, str], dict[str, object]] = {}

    def snapshot(self, key: str, name: str):
        value = self.values.get((key, name))
        return deepcopy(value) if value is not None else None


def patch_registry_backend(monkeypatch, memory: RegistryMemory) -> None:
    monkeypatch.setattr(rw, "_registry_key_exists", lambda key: key in memory.keys)
    monkeypatch.setattr(rw, "_ensure_registry_key", lambda key: memory.keys.add(key))
    monkeypatch.setattr(rw, "_query_registry_value", memory.snapshot)

    def set_value(operation: SetRegistryValue) -> None:
        memory.keys.add(operation.key)
        kind = {"sz": 1, "expand_sz": 2, "dword": 4}[operation.kind]
        memory.values[(operation.key, operation.name)] = {
            "type": kind,
            "data": deepcopy(operation.data),
        }

    monkeypatch.setattr(rw, "_set_registry_value", set_value)
    monkeypatch.setattr(
        rw,
        "_set_registry_snapshot",
        lambda key, name, snapshot: memory.values.__setitem__((key, name), deepcopy(snapshot)),
    )
    monkeypatch.setattr(rw, "_delete_registry_value", lambda key, name: memory.values.pop((key, name), None))
    monkeypatch.setattr(rw, "_delete_registry_key_if_empty", lambda key: None)


def make_plan(state_path: Path, key: str, value: str) -> InstallPlan:
    return InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "AcadLocation", "sz", value),
            WriteInstallState(state_path, {"autocad_root": value}),
        ),
        warnings=(),
        metadata={},
    )


def test_journal_preserves_original_state_across_repeat_install(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
    memory.keys.add(key)
    memory.values[(key, "AcadLocation")] = {"type": 1, "data": r"D:\Original"}
    state_path = tmp_path / "state.json"
    plan = make_plan(state_path, key, r"F:\Portable")

    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(plan)
    first_state = rw._load_state(state_path)
    adapter.apply_plan(plan)
    second_state = rw._load_state(state_path)

    identity = f"{key}\u0000AcadLocation"
    assert first_state is not None and second_state is not None
    assert first_state["registry_values"][identity]["before"]["data"] == r"D:\Original"
    assert second_state["registry_values"][identity]["before"]["data"] == r"D:\Original"
    assert memory.values[(key, "AcadLocation")]["data"] == r"F:\Portable"


def test_uninstall_restores_original_registry_value(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
    memory.keys.add(key)
    memory.values[(key, "AcadLocation")] = {"type": 1, "data": r"D:\Original"}
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(make_plan(state_path, key, r"F:\Portable"))
    report = adapter.uninstall(state_path)

    assert report.conflicts == ()
    assert report.registry_restored == 1
    assert memory.values[(key, "AcadLocation")]["data"] == r"D:\Original"
    assert not state_path.exists()


def test_uninstall_preserves_external_registry_change(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(make_plan(state_path, key, r"F:\Portable"))
    memory.values[(key, "AcadLocation")] = {"type": 1, "data": r"G:\External"}
    report = adapter.uninstall(state_path)

    assert len(report.conflicts) == 1
    assert memory.values[(key, "AcadLocation")]["data"] == r"G:\External"
    assert state_path.exists()


def test_shortcut_journal_restores_preexisting_file(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    shortcut = tmp_path / "AutoCAD 2024.lnk"
    shortcut.write_bytes(b"before-shortcut")
    state_path = tmp_path / "state.json"

    def fake_create_shortcut(operation) -> None:
        operation.path.parent.mkdir(parents=True, exist_ok=True)
        operation.path.write_bytes(b"installed-shortcut")

    monkeypatch.setattr(rw, "_create_shortcut", fake_create_shortcut)
    plan = InstallPlan(
        operations=(
            rw.CreateShortcut(shortcut, Path("acad.exe"), "/nologo", tmp_path),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(plan)
    assert shortcut.read_bytes() == b"installed-shortcut"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.shortcuts_restored == 1
    assert shortcut.read_bytes() == b"before-shortcut"


def test_shortcut_journal_preserves_external_change(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    shortcut = tmp_path / "AutoCAD 2024.lnk"
    state_path = tmp_path / "state.json"

    def fake_create_shortcut(operation) -> None:
        operation.path.parent.mkdir(parents=True, exist_ok=True)
        operation.path.write_bytes(b"installed-shortcut")

    monkeypatch.setattr(rw, "_create_shortcut", fake_create_shortcut)
    plan = InstallPlan(
        operations=(
            rw.CreateShortcut(shortcut, Path("acad.exe"), "/nologo", tmp_path),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(plan)
    shortcut.write_bytes(b"external-change")

    report = adapter.uninstall(state_path)
    assert len(report.conflicts) == 1
    assert shortcut.read_bytes() == b"external-change"
    assert state_path.exists()


def test_live_diff_classifies_registry_without_writing(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
    memory.keys.add(key)
    memory.values[(key, "Same")] = {"type": 1, "data": "same"}
    memory.values[(key, "Change")] = {"type": 1, "data": "old"}

    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Same", "sz", "same"),
            SetRegistryValue(key, "Change", "sz", "new"),
            SetRegistryValue(key, "Create", "dword", 1),
            WriteInstallState(tmp_path / "state.json", {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    report = rw.inspect_live_diff(plan, allow_non_windows_for_tests=True)
    assert report.registry_same == 1
    assert report.registry_change == 1
    assert report.registry_create == 1
    assert memory.values[(key, "Change")]["data"] == "old"
    assert not (tmp_path / "state.json").exists()


def test_uninstall_skips_shortcut_that_never_finished_creation(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    state_path = tmp_path / "state.json"
    shortcut = tmp_path / "missing-parent" / "AutoCAD 2024.lnk"
    state = rw._new_state()
    state["status"] = "failed"
    state["shortcuts"][str(shortcut)] = {"before_base64": None}
    rw._write_state(state_path, state)

    report = rw.RealWindowsAdapter(allow_non_windows_for_tests=True).uninstall(state_path)

    assert report.conflicts == ()
    assert report.shortcuts_removed == 0
    assert report.shortcuts_restored == 0
    assert not state_path.exists()


def test_archive_file_install_creates_and_owned_uninstall_removes(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive-placeholder")
    destination = tmp_path / "Program Files" / "Shared" / "runtime.dll"
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda operation: b"runtime-v1")
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "Program Files/Shared/runtime.dll", destination, "zzz"),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(plan)
    assert destination.read_bytes() == b"runtime-v1"
    state = rw._load_state(state_path)
    assert state is not None
    assert str(destination) in state["created_files"]

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.files_removed == 1
    assert not destination.exists()


def test_archive_file_install_reuses_identical_preexisting_file_without_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive-placeholder")
    destination = tmp_path / "runtime.dll"
    destination.write_bytes(b"runtime-v1")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda operation: b"runtime-v1")
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "runtime.dll", destination, "zzz"),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(plan)
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.files_removed == 0
    assert destination.read_bytes() == b"runtime-v1"


def test_archive_file_install_refuses_different_preexisting_shared_file(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive-placeholder")
    destination = tmp_path / "runtime.dll"
    destination.write_bytes(b"external-version")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rw, "_read_archive_member", lambda operation: b"runtime-v1")
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "runtime.dll", destination, "zzz"),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    try:
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(plan)
    except RuntimeError as exc:
        assert "refusing to overwrite existing shared file" in str(exc)
    else:
        raise AssertionError("expected conflicting shared file to be refused")
    assert destination.read_bytes() == b"external-version"


def test_live_diff_classifies_archive_files_without_writing(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive-placeholder")
    same = tmp_path / "same.dll"
    same.write_bytes(b"runtime-v1")
    create = tmp_path / "create.dll"
    conflict = tmp_path / "conflict.dll"
    conflict.write_bytes(b"external-version")
    monkeypatch.setattr(rw, "_read_archive_member", lambda operation: b"runtime-v1")
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "same.dll", same, "zzz"),
            rw.InstallArchiveFile(archive, "create.dll", create, "zzz"),
            rw.InstallArchiveFile(archive, "conflict.dll", conflict, "zzz"),
            WriteInstallState(tmp_path / "state.json", {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    report = rw.inspect_live_diff(plan, allow_non_windows_for_tests=True)

    assert report.file_same == 1
    assert report.file_create == 1
    assert report.file_conflict == 1
    assert any(str(conflict) in detail for detail in report.details)
    assert not create.exists()
