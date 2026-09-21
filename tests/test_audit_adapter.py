from __future__ import annotations

from pathlib import Path

from acad_portable.adapters import FakeWindowsAdapter
from acad_portable.audit import validate_core_plan
from acad_portable.ops import CreateShortcut
from acad_portable.planner import InstallPlan
from acad_portable.planner import InstallPlanner, KnownFolders

from test_planner import make_package


def folders() -> KnownFolders:
    return KnownFolders(
        user_profile=Path(r"C:\Users\Tester"),
        appdata=Path(r"C:\Users\Tester\AppData\Roaming"),
        local_appdata=Path(r"C:\Users\Tester\AppData\Local"),
        desktop=Path(r"C:\Users\Tester\Desktop"),
        windows=Path(r"C:\Windows"),
        program_data=Path(r"C:\ProgramData"),
        public=Path(r"C:\Users\Public"),
    )


def test_core_plan_passes_independent_static_audit(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    plan = InstallPlanner(layout, folders()).build()
    assert validate_core_plan(plan, layout) == ()


def test_fake_adapter_is_idempotent(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    plan = InstallPlanner(layout, folders()).build()
    adapter = FakeWindowsAdapter()

    adapter.apply_plan(plan)
    first = adapter.state.snapshot()
    adapter.apply_plan(plan)
    second = adapter.state.snapshot()

    assert first == second
    assert len(second.junctions) == 2
    assert len(second.shortcuts) == 3


def test_plan_audit_rejects_shortcut_parent_that_is_a_file(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    parent = tmp_path / "Desktop"
    parent.write_bytes(b"not-a-directory")
    plan = InstallPlan(
        operations=(CreateShortcut(parent / "AutoCAD 2024.lnk", layout.acad_exe),),
        warnings=(),
        metadata={},
    )
    findings = validate_core_plan(plan, layout)
    assert any(item.code == "SHORTCUT_PARENT_NOT_DIRECTORY" for item in findings)
