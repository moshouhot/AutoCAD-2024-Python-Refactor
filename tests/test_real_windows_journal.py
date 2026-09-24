from __future__ import annotations

import os
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
        kind = {"sz": 1, "expand_sz": 2, "dword": 4, "multi_sz": 7}[operation.kind]
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


def test_first_install_preserves_preexisting_shared_registry_value(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\SharedRuntime"
    memory.keys.add(key)
    memory.values[(key, "Setting")] = {"type": 1, "data": "external"}
    state_path = tmp_path / "state.json"
    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(
                key,
                "Setting",
                "sz",
                "portable",
                preserve_existing=True,
            ),
            WriteInstallState(state_path, {}),
        ),
        warnings=(),
        metadata={},
    )

    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(plan)

    identity = f"{key}\u0000Setting"
    state = rw._load_state(state_path)
    assert state is not None
    assert identity not in state["registry_values"]
    assert memory.values[(key, "Setting")]["data"] == "external"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert memory.values[(key, "Setting")]["data"] == "external"


def test_first_install_owns_missing_preserve_existing_registry_value(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\SharedRuntime"
    memory.keys.add(key)
    state_path = tmp_path / "state.json"
    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(
                key,
                "Setting",
                "sz",
                "portable",
                preserve_existing=True,
            ),
            WriteInstallState(state_path, {}),
        ),
        warnings=(),
        metadata={},
    )

    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(plan)

    identity = f"{key}\u0000Setting"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["registry_values"][identity]["before"] is None
    assert state["registry_values"][identity]["installed"]["data"] == "portable"
    assert memory.values[(key, "Setting")]["data"] == "portable"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert (key, "Setting") not in memory.values


def test_upgrade_releases_registry_value_changed_externally(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\Runtime"
    memory.keys.add(key)
    memory.values[(key, "Setting")] = {"type": 1, "data": "before"}
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    first = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "installed-v1"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(), metadata={},
    )
    second = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "installed-v2"),
            WriteInstallState(state_path, {"version": 2}),
        ),
        warnings=(), metadata={},
    )

    adapter.apply_plan(first)
    memory.values[(key, "Setting")] = {"type": 1, "data": "external"}
    adapter.apply_plan(second)
    adapter.apply_plan(second)

    identity = f"{key}\u0000Setting"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["registry_values"][identity]["released"] is True
    assert memory.values[(key, "Setting")]["data"] == "external"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert memory.values[(key, "Setting")]["data"] == "external"
    assert not state_path.exists()


def test_upgrade_updates_registry_value_when_still_installer_owned(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    memory.keys.add(key)
    memory.values[(key, "Setting")] = {"type": 1, "data": "before"}
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(InstallPlan(
        operations=(EnsureRegistryKey(key), SetRegistryValue(key, "Setting", "sz", "v1"), WriteInstallState(state_path, {})),
        warnings=(), metadata={},
    ))
    adapter.apply_plan(InstallPlan(
        operations=(EnsureRegistryKey(key), SetRegistryValue(key, "Setting", "sz", "v2"), WriteInstallState(state_path, {})),
        warnings=(), metadata={},
    ))

    identity = f"{key}\u0000Setting"
    state = rw._load_state(state_path)
    assert state is not None
    assert state["registry_values"][identity]["before"]["data"] == "before"
    assert state["registry_values"][identity]["installed"]["data"] == "v2"
    assert not state["registry_values"][identity].get("released", False)
    assert memory.values[(key, "Setting")]["data"] == "v2"


def test_upgrade_removes_stale_owned_registry_value_dropped_from_new_plan(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    first = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Keep", "sz", "keep"),
            SetRegistryValue(key, "Drop", "sz", "drop"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(), metadata={},
    )
    second = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Keep", "sz", "keep"),
            WriteInstallState(state_path, {"version": 2}),
        ),
        warnings=(), metadata={},
    )

    adapter.apply_plan(first)
    adapter.apply_plan(second)

    stale_identity = f"{key}\u0000Drop"
    state = rw._load_state(state_path)
    assert state is not None
    assert (key, "Drop") not in memory.values
    assert stale_identity not in state["registry_values"]
    assert state["retired_registry_values"][stale_identity]["action"] == "removed"
    assert memory.values[(key, "Keep")]["data"] == "keep"


def test_upgrade_restores_stale_owned_registry_value_to_original(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    memory.keys.add(key)
    memory.values[(key, "Setting")] = {"type": 1, "data": "original"}
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "installed"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(), metadata={},
    ))
    adapter.apply_plan(InstallPlan(
        operations=(EnsureRegistryKey(key), WriteInstallState(state_path, {"version": 2})),
        warnings=(), metadata={},
    ))

    identity = f"{key}\u0000Setting"
    state = rw._load_state(state_path)
    assert state is not None
    assert memory.values[(key, "Setting")]["data"] == "original"
    assert identity not in state["registry_values"]
    assert state["retired_registry_values"][identity]["action"] == "restored"


def test_upgrade_preserves_external_change_when_stale_value_is_dropped(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    adapter.apply_plan(InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "installed"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(), metadata={},
    ))
    memory.values[(key, "Setting")] = {"type": 1, "data": "external"}
    adapter.apply_plan(InstallPlan(
        operations=(EnsureRegistryKey(key), WriteInstallState(state_path, {"version": 2})),
        warnings=(), metadata={},
    ))

    identity = f"{key}\u0000Setting"
    state = rw._load_state(state_path)
    assert state is not None
    assert memory.values[(key, "Setting")]["data"] == "external"
    assert identity not in state["registry_values"]
    assert state["retired_registry_values"][identity]["action"] == "released_external"


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
    memory.values[(key, "Preserve")] = {"type": 1, "data": "external"}

    plan = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Same", "sz", "same"),
            SetRegistryValue(key, "Change", "sz", "new"),
            SetRegistryValue(
                key,
                "Preserve",
                "sz",
                "portable",
                preserve_existing=True,
            ),
            SetRegistryValue(key, "Create", "dword", 1),
            WriteInstallState(tmp_path / "state.json", {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    report = rw.inspect_live_diff(plan, allow_non_windows_for_tests=True)
    assert report.registry_same == 1
    assert report.registry_change == 1
    assert report.registry_external_preserved == 1
    assert report.registry_create == 1
    assert memory.values[(key, "Change")]["data"] == "old"
    assert memory.values[(key, "Preserve")]["data"] == "external"
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


def test_archive_file_install_refuses_dangling_destination_reparse_point_without_creating_it(
    tmp_path: Path, monkeypatch
) -> None:
    """A dangling symlink/reparse point at the destination must never be written through.

    ``Path.exists()`` is False for a symlink whose target is missing, so an
    existence check based on it would fall through and create the file at the
    link target.  The adapter's ``lexists`` gate must instead refuse the
    destination outright, leave the filesystem untouched and keep the journal
    from claiming ownership of a file it never created.
    """
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive-placeholder")
    destination = tmp_path / "Program Files" / "Shared" / "runtime.dll"
    assert not destination.exists()
    assert not os.path.lexists(destination)
    state_path = tmp_path / "state.json"

    read_calls: list[str] = []

    def read_member(operation) -> bytes:
        read_calls.append(str(operation.destination))
        return b"runtime-v1"

    monkeypatch.setattr(rw, "_read_archive_member", read_member)
    real_lexists = os.path.lexists

    def fake_lexists(path) -> bool:
        # Emulate a dangling symlink/reparse point: lexists() is True while the
        # path is not a regular file and does not exist for exists().
        if Path(path) == destination:
            return True
        return real_lexists(path)

    monkeypatch.setattr(rw.os.path, "lexists", fake_lexists)
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "Program Files/Shared/runtime.dll", destination, "zzz"),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    try:
        rw.RealWindowsAdapter(allow_non_windows_for_tests=True).apply_plan(plan)
    except RuntimeError as exc:
        assert "exists but is not a file" in str(exc)
    else:
        raise AssertionError("expected dangling destination to be refused")

    # The payload was read before the decision, so the refusal is about the
    # destination gate and not an early member-read failure.
    assert read_calls == [str(destination)]
    assert not real_lexists(destination)
    assert not destination.exists()
    assert not destination.parent.exists()
    state = rw._load_state(state_path)
    assert state is not None
    assert state["created_files"] == {}
    assert str(destination) not in state["created_files"]
    assert state["status"] == "failed"


def test_archive_file_install_reuses_different_preexisting_shared_file_when_allowed(
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
            rw.InstallArchiveFile(
                archive, "runtime.dll", destination, "zzz", reuse_existing=True
            ),
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
    assert destination.read_bytes() == b"external-version"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert report.files_removed == 0
    assert destination.read_bytes() == b"external-version"


def test_live_diff_classifies_archive_files_without_writing(tmp_path: Path, monkeypatch) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"archive-placeholder")
    same = tmp_path / "same.dll"
    same.write_bytes(b"runtime-v1")
    create = tmp_path / "create.dll"
    reuse = tmp_path / "reuse.dll"
    reuse.write_bytes(b"external-version")
    conflict = tmp_path / "conflict.dll"
    conflict.write_bytes(b"external-version")
    monkeypatch.setattr(rw, "_read_archive_member", lambda operation: b"runtime-v1")
    plan = InstallPlan(
        operations=(
            rw.InstallArchiveFile(archive, "same.dll", same, "zzz"),
            rw.InstallArchiveFile(archive, "create.dll", create, "zzz"),
            rw.InstallArchiveFile(
                archive, "reuse.dll", reuse, "zzz", reuse_existing=True
            ),
            rw.InstallArchiveFile(archive, "conflict.dll", conflict, "zzz"),
            WriteInstallState(tmp_path / "state.json", {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    report = rw.inspect_live_diff(plan, allow_non_windows_for_tests=True)

    assert report.file_same == 1
    assert report.file_reuse == 1
    assert report.file_create == 1
    assert report.file_conflict == 1
    assert any(str(conflict) in detail for detail in report.details)
    assert not create.exists()
