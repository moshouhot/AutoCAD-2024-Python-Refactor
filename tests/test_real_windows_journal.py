from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import acad_portable.real_windows as rw
from acad_portable.ops import EnsureRegistryKey, SetRegistryValue, WriteInstallState
from acad_portable.planner import InstallPlan


class _CaseInsensitiveValueMap(dict):
    """dict keyed by (key, name) tuples with Windows case-insensitive semantics."""

    @staticmethod
    def _norm(key: tuple[str, str]) -> tuple[str, str]:
        registry_key, name = key
        return (registry_key.rstrip("\\").casefold(), name.casefold())

    def __getitem__(self, key):
        return super().__getitem__(self._norm(key))

    def __setitem__(self, key, value):
        super().__setitem__(self._norm(key), value)

    def __contains__(self, key) -> bool:
        return super().__contains__(self._norm(key))

    def get(self, key, default=None):
        return super().get(self._norm(key), default)

    def pop(self, key, default=None):
        return super().pop(self._norm(key), default)


class _CaseInsensitiveSet(set):
    """set of registry key paths with Windows case-insensitive semantics."""

    @staticmethod
    def _norm(key: str) -> str:
        return key.rstrip("\\").casefold()

    def add(self, key: str) -> None:
        super().add(self._norm(key))

    def __contains__(self, key) -> bool:
        return super().__contains__(self._norm(key))

    def remove(self, key: str) -> None:
        super().remove(self._norm(key))


class RegistryMemory:
    """In-memory registry that mirrors Windows case-insensitive key/value names."""

    def __init__(self) -> None:
        self.keys: set[str] = _CaseInsensitiveSet()
        self.values: dict[tuple[str, str], dict[str, object]] = _CaseInsensitiveValueMap()

    def snapshot(self, key: str, name: str):
        value = self.values.get((key, name))
        return deepcopy(value) if value is not None else None

    def set(self, key: str, name: str, snapshot: dict[str, object]) -> None:
        self.values[(key, name)] = deepcopy(snapshot)

    def drop(self, key: str, name: str) -> None:
        self.values.pop((key, name), None)

    def has_key(self, key: str) -> bool:
        return key in self.keys

    def add_key(self, key: str) -> None:
        self.keys.add(key)


def patch_registry_backend(monkeypatch, memory: RegistryMemory) -> None:
    monkeypatch.setattr(rw, "_registry_key_exists", memory.has_key)
    monkeypatch.setattr(rw, "_ensure_registry_key", memory.add_key)
    monkeypatch.setattr(rw, "_query_registry_value", memory.snapshot)

    def set_value(operation: SetRegistryValue) -> None:
        memory.add_key(operation.key)
        kind = {"sz": 1, "expand_sz": 2, "dword": 4, "multi_sz": 7}[operation.kind]
        memory.set(
            operation.key,
            operation.name,
            {"type": kind, "data": deepcopy(operation.data)},
        )

    monkeypatch.setattr(rw, "_set_registry_value", set_value)
    monkeypatch.setattr(
        rw,
        "_set_registry_snapshot",
        lambda key, name, snapshot: memory.set(key, name, snapshot),
    )
    monkeypatch.setattr(rw, "_delete_registry_value", memory.drop)
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

    identity = rw._registry_identity(key, "AcadLocation")
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

    identity = rw._registry_identity(key, "Setting")
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

    identity = rw._registry_identity(key, "Setting")
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

    identity = rw._registry_identity(key, "Setting")
    state = rw._load_state(state_path)
    assert state is not None
    assert state["registry_values"][identity]["released"] is True
    assert memory.values[(key, "Setting")]["data"] == "external"

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert memory.values[(key, "Setting")]["data"] == "external"
    assert not state_path.exists()


def test_upgrade_releases_external_value_even_when_it_matches_next_wanted(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_CURRENT_USER\SOFTWARE\Autodesk\Owned"
    memory.keys.add(key)
    memory.values[(key, "Setting")] = {"type": 1, "data": "before"}
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)

    first = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "A"),
            WriteInstallState(state_path, {"version": 1}),
        ),
        warnings=(),
        metadata={},
    )
    second = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "Setting", "sz", "B"),
            WriteInstallState(state_path, {"version": 2}),
        ),
        warnings=(),
        metadata={},
    )

    adapter.apply_plan(first)
    memory.values[(key, "Setting")] = {"type": 1, "data": "B"}

    real_set_value = rw._set_registry_value
    writes: list[str] = []

    def spy_set_value(operation: SetRegistryValue) -> None:
        writes.append(str(operation.data))
        real_set_value(operation)

    monkeypatch.setattr(rw, "_set_registry_value", spy_set_value)
    adapter.apply_plan(second)

    identity = rw._registry_identity(key, "Setting")
    state = rw._load_state(state_path)
    assert state is not None
    entry = state["registry_values"][identity]
    assert entry["released"] is True
    assert entry["released_snapshot"] == {"type": 1, "data": "B"}
    assert writes == []
    assert memory.values[(key, "Setting")] == {"type": 1, "data": "B"}

    report = adapter.uninstall(state_path)
    assert report.conflicts == ()
    assert memory.values[(key, "Setting")] == {"type": 1, "data": "B"}
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

    identity = rw._registry_identity(key, "Setting")
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

    stale_identity = rw._registry_identity(key, "Drop")
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

    identity = rw._registry_identity(key, "Setting")
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

    identity = rw._registry_identity(key, "Setting")
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
    assert rw._find_file_entry(state["created_files"], destination) is not None

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
    assert rw._find_file_entry(state["created_files"], destination) is None
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


# --- P2-2: registry ownership is decided before any wanted-value match -------


def test_live_diff_prior_ownership_beats_wanted_value_match(
    tmp_path: Path, monkeypatch
) -> None:
    """owned A -> external B -> next plan wants B must be external, never same."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(make_plan(state_path, key, "A"))

    # An external process overwrites our value with B, which the next plan
    # also happens to want.  Apply releases ownership in this case, so the
    # diff must not report a wanted-value match.
    memory.set(key, "AcadLocation", {"type": 1, "data": "B"})

    report = rw.inspect_live_diff(
        make_plan(state_path, key, "B"), allow_non_windows_for_tests=True
    )

    assert report.registry_external_preserved == 1
    assert report.registry_same == 0
    assert report.registry_change == 0


def test_live_diff_active_owned_value_wanted_match_is_same(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(make_plan(state_path, key, "A"))

    report = rw.inspect_live_diff(
        make_plan(state_path, key, "A"), allow_non_windows_for_tests=True
    )

    assert report.registry_same == 1
    assert report.registry_external_preserved == 0


def test_live_diff_no_journal_external_equal_to_wanted_is_same(
    tmp_path: Path, monkeypatch
) -> None:
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Unowned"
    memory.keys.add(key)
    memory.set(key, "AcadLocation", {"type": 1, "data": "B"})

    report = rw.inspect_live_diff(
        make_plan(tmp_path / "state.json", key, "B"),
        allow_non_windows_for_tests=True,
    )

    assert report.registry_same == 1
    assert report.registry_external_preserved == 0
    assert not (tmp_path / "state.json").exists()


def test_live_diff_released_entry_equal_to_wanted_is_external(
    tmp_path: Path, monkeypatch
) -> None:
    """A journaled-but-released value must stay external even if it equals wanted."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(make_plan(state_path, key, "A"))
    # External process changes it; a re-apply of A observes the mismatch and
    # marks our ownership released.
    memory.set(key, "AcadLocation", {"type": 1, "data": "B"})
    adapter.apply_plan(make_plan(state_path, key, "A"))
    state = rw._load_state(state_path)
    assert state is not None
    assert state["registry_values"][rw._registry_identity(key, "AcadLocation")]["released"]

    report = rw.inspect_live_diff(
        make_plan(state_path, key, "B"), allow_non_windows_for_tests=True
    )

    assert report.registry_external_preserved == 1
    assert report.registry_same == 0


def test_live_diff_preserve_existing_does_not_block_owned_upgrade(
    tmp_path: Path, monkeypatch
) -> None:
    """An installer-owned value is still upgradable under preserve_existing."""
    memory = RegistryMemory()
    patch_registry_backend(monkeypatch, memory)
    key = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Owned"
    state_path = tmp_path / "state.json"
    adapter = rw.RealWindowsAdapter(allow_non_windows_for_tests=True)
    adapter.apply_plan(make_plan(state_path, key, "A"))

    upgrade = InstallPlan(
        operations=(
            EnsureRegistryKey(key),
            SetRegistryValue(key, "AcadLocation", "sz", "B", preserve_existing=True),
            WriteInstallState(state_path, {"version": 2}),
        ),
        warnings=(),
        metadata={},
    )
    report = rw.inspect_live_diff(upgrade, allow_non_windows_for_tests=True)

    assert report.registry_change == 1
    assert report.registry_external_preserved == 0

    adapter.apply_plan(upgrade)
    assert memory.values[(key, "AcadLocation")]["data"] == "B"
