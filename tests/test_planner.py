from __future__ import annotations

from pathlib import Path

import pytest

from acad_portable.model import PackageError, PackageLayout
from acad_portable.ops import CreateShortcut, EnsureJunction, SetRegistryValue
from acad_portable.planner import InstallPlanner, KnownFolders


REG_HEADER = "Windows Registry Editor Version 5.00\n\n"


def make_package(root: Path) -> PackageLayout:
    acad = root / "AutoCAD 2024"
    acaoe = acad / "ACAOE"
    (acaoe / "CHS" / "Plotters" / "Plot Styles").mkdir(parents=True)
    (acad / "Support").mkdir(parents=True)
    (acad / "0加载应用程序").mkdir(parents=True)
    (acad / "acad.exe").write_bytes(b"exe")
    (acad / "addplwiz.exe").write_bytes(b"exe")
    (acad / "styshwiz.exe").write_bytes(b"exe")
    (acad / "Support" / "acad2024.lsp").write_text('(load "appload.lsp")', encoding="utf-8")
    (acad / "Support" / "appload.lsp").write_text("(princ)", encoding="utf-8")
    (acaoe / "配置.txt").write_text("桌面快捷方式=1\n", encoding="utf-8")

    (acaoe / "reg1.dli").write_text(
        REG_HEADER
        + r'''[HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804]
"UserPath"="C:\\Users\\Administrator\\AppData\\Roaming\\Autodesk"
"LastRunTime"="legacy-runtime-value"
"AutoMigrate"=dword:00000001

[HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804\MiniDump]
"SessionStartCount"=dword:00000009
"KeepMe"=dword:00000001

[HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804\Applications\CloudAccess]
"LOADER"="%UserProfile%\\AppData\\Roaming\\Autodesk\\ApplicationPlugins\\Old.bundle\\Contents\\Cloud.dll"

[HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804\AssemblyMap]
"OldPlugin"="C:\\Users\\Administrator\\AppData\\Roaming\\Autodesk\\ApplicationPlugins\\Old.dll"

[HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804\Profiles\<<未命名配置>>\General]
"ACAD"=hex(2):45,00,3a,00,5c,00,4f,00,6c,00,64,00,5c,00,41,00,75,00,74,00,6f,00,43,00,41,00,44,00,20,00,32,00,30,00,32,00,34,00,5c,00,53,00,75,00,70,00,70,00,6f,00,72,00,74,00,00,00

[HKEY_CURRENT_USER\SOFTWARE\OtherVendor]
"ShouldNotAppear"="x"
''',
        encoding="utf-16",
    )
    (acaoe / "reg3.dli").write_text(
        REG_HEADER
        + r'''[HKEY_CURRENT_USER\SOFTWARE\Classes\AutoCAD.Application]
@="AutoCAD Application"

[HKEY_CURRENT_USER\SOFTWARE\Classes\AutoCAD.Application.24\CLSID]
@="{8B4929F8-076F-4AEC-AFEE-8928747B7AE3}"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{8B4929F8-076F-4AEC-AFEE-8928747B7AE3}\LocalServer32]
@="D:\\00\\AutoCAD 2024\\AutoCAD 2024\\acad.exe /Automation"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{AA9A2205-75AA-43AD-9138-1767F1BB5E0C}\1.0\0\win32]
@="D:\\00\\AutoCAD 2024\\AutoCAD 2024\\Autodesk Shared\\acax24enu.tlb"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\MicrosoftEdge.Fake]
@="must-not-enter-core"
''',
        encoding="utf-16",
    )
    (acaoe / "reg2.dli").write_text(
        REG_HEADER
        + r'''[HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804]
"AcadLocation"="D:\\00\\AutoCAD 2024\\AutoCAD 2024\\"
"ProductNameGlob"="AutoCAD 2024"
"Loader"="D:\\00\\AutoCAD 2024\\AutoCAD 2024\\acad.exe"

[HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804\Applications\AcadVBA]
"LOADER"="C:\\Program Files\\Autodesk\\ApplicationPlugins\\AcVBA2024.Bundle\\Contents\\AcVBA.arx"

[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\EdgeUpdate]
"ShouldNotAppear"="x"
''',
        encoding="utf-16",
    )
    return PackageLayout.discover(root)


def test_planner_rebases_paths_and_allowlists_registry(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    folders = KnownFolders(
        user_profile=Path(r"C:\Users\Tester"),
        appdata=Path(r"C:\Users\Tester\AppData\Roaming"),
        local_appdata=Path(r"C:\Users\Tester\AppData\Local"),
        desktop=Path(r"C:\Users\Tester\Desktop"),
        windows=Path(r"C:\Windows"),
        program_data=Path(r"C:\ProgramData"),
        public=Path(r"C:\Users\Public"),
    )

    plan = InstallPlanner(layout, folders).build()

    registry_values = [op for op in plan.operations if isinstance(op, SetRegistryValue)]
    assert registry_values
    assert all("OtherVendor" not in op.key for op in registry_values)
    assert all("EdgeUpdate" not in op.key for op in registry_values)
    assert all("CloudAccess" not in op.key for op in registry_values)
    assert all("AssemblyMap" not in op.key for op in registry_values)
    assert all("AcadVBA" not in op.key for op in registry_values)
    assert all(op.name != "LastRunTime" for op in registry_values)
    assert all(op.name != "AutoMigrate" for op in registry_values)
    assert all(op.name != "SessionStartCount" for op in registry_values)
    assert any(op.name == "KeepMe" for op in registry_values)
    assert any("AutoCAD.Application" in op.key for op in registry_values)
    assert all("MicrosoftEdge.Fake" not in op.key for op in registry_values)

    com_server = next(
        op
        for op in registry_values
        if "{8B4929F8-076F-4AEC-AFEE-8928747B7AE3}" in op.key
        and op.name == ""
    )
    expected_exe = str(layout.acad_exe).replace("/", "\\")
    actual_server = str(com_server.data).replace("/", "\\")
    assert expected_exe in actual_server

    loader = next(op for op in registry_values if op.name == "Loader")
    assert str(layout.autocad_root) in str(loader.data)
    assert r"D:\00\AutoCAD 2024" not in str(loader.data)

    user_path = next(op for op in registry_values if op.name == "UserPath")
    assert str(user_path.data).startswith(r"C:\Users\Tester")

    acad_path = next(op for op in registry_values if op.name == "ACAD")
    assert acad_path.kind == "expand_sz"
    expected_support = str(layout.autocad_root / "Support").replace("/", "\\")
    actual_support = str(acad_path.data).replace("/", "\\")
    assert actual_support == expected_support
    assert not plan.warnings


def test_planner_builds_chs_junctions_and_shortcuts(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    folders = KnownFolders(
        user_profile=Path(r"C:\Users\Tester"),
        appdata=Path(r"C:\Users\Tester\AppData\Roaming"),
        local_appdata=Path(r"C:\Users\Tester\AppData\Local"),
        desktop=Path(r"C:\Users\Tester\Desktop"),
        windows=Path(r"C:\Windows"),
        program_data=Path(r"C:\ProgramData"),
        public=Path(r"C:\Users\Public"),
    )

    plan = InstallPlanner(layout, folders).build()
    junctions = [op for op in plan.operations if isinstance(op, EnsureJunction)]
    assert len(junctions) == 2
    assert all(op.target == layout.chs for op in junctions)

    shortcuts = [op for op in plan.operations if isinstance(op, CreateShortcut)]
    assert len(shortcuts) == 3
    desktop = next(op for op in shortcuts if op.path.parent == folders.desktop)
    assert desktop.target == layout.acad_exe
    assert desktop.arguments == "/nologo"


def test_desktop_shortcut_respects_config(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    layout.config.write_text("桌面快捷方式=0\n", encoding="utf-8")
    folders = KnownFolders(
        user_profile=Path(r"C:\Users\Tester"),
        appdata=Path(r"C:\Users\Tester\AppData\Roaming"),
        local_appdata=Path(r"C:\Users\Tester\AppData\Local"),
        desktop=Path(r"C:\Users\Tester\Desktop"),
        windows=Path(r"C:\Windows"),
        program_data=Path(r"C:\ProgramData"),
        public=Path(r"C:\Users\Public"),
    )
    plan = InstallPlanner(layout, folders).build()
    shortcuts = [op for op in plan.operations if isinstance(op, CreateShortcut)]
    assert len(shortcuts) == 2
    assert all(op.path.parent != folders.desktop for op in shortcuts)


def test_planner_refuses_unparseable_registry_version(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    text = layout.reg2.read_text(encoding="utf-16")
    layout.reg2.write_text(text.replace(r"\AutoCAD\R24.3", r"\AutoCAD\UNKNOWN"), encoding="utf-16")

    with pytest.raises(PackageError, match="registry version"):
        InstallPlanner(layout).build()


def test_planner_refuses_other_active_autocad_version(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    text = layout.reg2.read_text(encoding="utf-16")
    layout.reg2.write_text(text.replace(r"\AutoCAD\R24.3", r"\AutoCAD\R25.0"), encoding="utf-16")

    with pytest.raises(PackageError, match=r"R25\.0.*expected R24\.3"):
        InstallPlanner(layout).build()


def test_planner_ignores_deleted_registry_version_sections(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    text = layout.reg2.read_text(encoding="utf-16")
    deleted = REG_HEADER + r'''[-HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R25.0]
'''
    layout.reg2.write_text(deleted + text.removeprefix(REG_HEADER), encoding="utf-16")

    plan = InstallPlanner(layout).build()
    assert plan.metadata["version"] == "R24.3"


def test_planner_deleted_sections_do_not_influence_path_rebasing(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    reg1_text = layout.reg1.read_text(encoding="utf-16")
    deleted = REG_HEADER + r'''[-HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD\R24.3\Deleted]
"StaleUserPath"="Z:\\Users\\DeletedUser\\AppData\\Roaming\\Autodesk"
"StaleAcadPath"="Z:\\Deleted\\AutoCAD 2024\\Support"
'''
    layout.reg1.write_text(deleted + reg1_text.removeprefix(REG_HEADER), encoding="utf-16")

    plan = InstallPlanner(layout).build()

    assert all(
        not old.startswith(r"Z:\Users\DeletedUser")
        and not old.startswith(r"Z:\Deleted\AutoCAD 2024")
        for old in plan.metadata["legacy_path_prefixes"]
    )

