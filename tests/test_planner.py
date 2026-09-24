from __future__ import annotations

from pathlib import Path

import pytest

from acad_portable.audit import validate_core_plan
from acad_portable.model import PackageError, PackageLayout
from acad_portable.ops import CreateShortcut, EnsureJunction, InstallArchiveFile, SetRegistryValue
from acad_portable.planner import (
    HKLM_INSTALLER_CLASSES,
    HKLM_INSTALLER_USERDATA_SYSTEM,
    InstallPlanner,
    KnownFolders,
    VBA71_2052_FEATURE,
    VBA71_2052_PACKED_PRODUCT,
    VBA71_2052_REQUIRED_COMPONENTS,
    VBA71_FEATURE,
    VBA71_FM20_PACKED_COMPONENT,
    VBA71_PACKED_PRODUCT,
    VBA71_QUALIFIED_CATEGORY_PACKED,
    VBA71_QUALIFIER_2052,
    VBA71_REQUIRED_COMPONENTS,
    VBA_ENABLER_ACVBA_PACKED_COMPONENT,
    VBA_ENABLER_PACKED_PRODUCT,
    VBA_MSI_COMPONENT_CLIENT_ROOT,
)


REG_HEADER = "Windows Registry Editor Version 5.00\n\n"


def _multi_sz_hex(*items: str) -> str:
    raw = ("\x00".join(items) + "\x00\x00").encode("utf-16le")
    return ",".join(f"{byte:02x}" for byte in raw)


def append_vba_msi_fixture(layout: PackageLayout) -> None:
    text = layout.vba_registry.read_text(encoding="utf-16")
    component_rows: list[tuple[str, str, str]] = []
    for packed_component in sorted(VBA71_REQUIRED_COMPONENTS):
        if packed_component == VBA71_FM20_PACKED_COMPONENT:
            data = r"C:\Windows\system32\FM20.DLL"
        else:
            data = rf"C:\Program Files\Common Files\Microsoft Shared\VBA\VBA7.1\{packed_component}.bin"
        component_rows.append((packed_component, VBA71_PACKED_PRODUCT, data))
    for packed_component in sorted(VBA71_2052_REQUIRED_COMPONENTS):
        data = rf"C:\Program Files\Common Files\Microsoft Shared\VBA\VBA7.1\2052\{packed_component}.bin"
        component_rows.append((packed_component, VBA71_2052_PACKED_PRODUCT, data))
    parts = [
        text,
        f'''\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\S-1-5-18\\Products\\{VBA71_PACKED_PRODUCT}\\Features]\n"{VBA71_FEATURE}"="base-feature"\n''',
        f'''\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\S-1-5-18\\Products\\{VBA71_PACKED_PRODUCT}\\Usage]\n"{VBA71_FEATURE}"=dword:00000001\n''',
        f'''\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\S-1-5-18\\Products\\{VBA71_2052_PACKED_PRODUCT}\\Features]\n"{VBA71_2052_FEATURE}"="lang-feature"\n''',
        f'''\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\S-1-5-18\\Products\\{VBA71_2052_PACKED_PRODUCT}\\Usage]\n"{VBA71_2052_FEATURE}"=dword:00000001\n''',
    ]
    for packed_component, packed_product, data in component_rows:
        parts.append(
            f'''\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\S-1-5-18\\Components\\{packed_component}]\n"{packed_product}"="{data.replace(chr(92), chr(92) * 2)}"\n'''
        )
    parts.append(
        f'''\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\Installer\\Components\\{VBA71_QUALIFIED_CATEGORY_PACKED}]\n"{VBA71_QUALIFIER_2052}"=hex(7):{_multi_sz_hex("descriptor")}\n'''
    )
    layout.vba_registry.write_text("".join(parts), encoding="utf-16")


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

[HKEY_CURRENT_USER\SOFTWARE\Classes\AutoCAD.ApplicationExtra]
@="must-not-enter-core"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\AutoCAD.Application.24Extra]
@="must-not-enter-core"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{8B4929F8-076F-4AEC-AFEE-8928747B7AE3}\LocalServer32]
@="D:\\00\\AutoCAD 2024\\AutoCAD 2024\\acad.exe /Automation"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{AA9A2205-75AA-43AD-9138-1767F1BB5E0C}\1.0\0\win32]
@="D:\\00\\AutoCAD 2024\\AutoCAD 2024\\Autodesk Shared\\acax24enu.tlb"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{E89B39BB-5AE4-4C52-9011-B70FC663F249}]
@="AcadObject"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{E89B39BB-5AE4-4C52-9011-B70FC663F249}\InProcServer32]
@="axdb.dll"
"ThreadingModel"="Apartment"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{E89B39BB-5AE4-4C52-9011-B70FC663F249}Extra]
@="must-not-enter-core"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{E8B0B8B1-FC46-4358-8DDE-217554361CB0}]
@="AcadWipeout"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{E8B0B8B1-FC46-4358-8DDE-217554361CB0}\InProcServer32]
@="axdb.dll"
"ThreadingModel"="Apartment"

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
    assert any("AutoCAD.Application.24\\CLSID" in op.key for op in registry_values)
    assert all("AutoCAD.ApplicationExtra" not in op.key for op in registry_values)
    assert all("AutoCAD.Application.24Extra" not in op.key for op in registry_values)
    assert any("{E89B39BB-5AE4-4C52-9011-B70FC663F249}" in op.key for op in registry_values)
    assert all("{E89B39BB-5AE4-4C52-9011-B70FC663F249}Extra" not in op.key for op in registry_values)
    assert all("{E8B0B8B1-FC46-4358-8DDE-217554361CB0}" not in op.key for op in registry_values)
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


def test_planner_includes_only_traced_acadobject_clsid(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    plan = InstallPlanner(layout).build()
    registry_values = [op for op in plan.operations if isinstance(op, SetRegistryValue)]

    target = [
        op
        for op in registry_values
        if "{E89B39BB-5AE4-4C52-9011-B70FC663F249}" in op.key
    ]
    assert {(op.name, op.data) for op in target} == {
        ("", "AcadObject"),
        ("", "axdb.dll"),
        ("ThreadingModel", "Apartment"),
    }
    assert all(
        "{E8B0B8B1-FC46-4358-8DDE-217554361CB0}" not in op.key
        for op in registry_values
    )
    assert all(
        "{E89B39BB-5AE4-4C52-9011-B70FC663F249}Extra" not in op.key
        for op in registry_values
    )


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


def test_planner_refuses_version_from_unrelated_registry_root(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    text = layout.reg2.read_text(encoding="utf-16")
    text = text.replace(
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3",
        r"HKEY_CURRENT_USER\SOFTWARE\OtherVendor\AutoCAD\R24.3",
    )
    layout.reg2.write_text(text, encoding="utf-16")

    with pytest.raises(PackageError, match="Cannot parse AutoCAD registry version"):
        InstallPlanner(layout).build()


def test_planner_refuses_nested_fake_version_under_autocad_root(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    text = layout.reg2.read_text(encoding="utf-16")
    text = text.replace(
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3",
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\SomeVendor\AutoCAD\R24.3",
    )
    layout.reg2.write_text(text, encoding="utf-16")

    with pytest.raises(PackageError, match="Cannot parse AutoCAD registry version"):
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


def test_vba_base_plan_includes_minimal_msi_identity_and_excludes_untraced_installer_state(
    tmp_path: Path,
) -> None:
    layout = make_package(tmp_path)
    layout.config.write_text("桌面快捷方式=1\n安装 VBA编程=1\n", encoding="utf-8")
    layout.vba_archive.parent.mkdir(parents=True, exist_ok=True)
    layout.vba_archive.write_bytes(b"7z-placeholder")
    layout.vba_registry.write_text(
        REG_HEADER
        + r'''[HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3\AutoCAD 2024 VBA Enabler]
"LangAbbrev"=""

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{2F967C44-B1F0-485E-957C-97538BCAD2DE}]
@="Microsoft APC 7.1 Object Library"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{2F967C44-B1F0-485E-957C-97538BCAD2DE}\InprocServer32]
@="C:\\Program Files\\Common Files\\Microsoft Shared\\VBA\\VBA7.1\\apc71.dll"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\MSAPC.ApcGlobal]
@="Microsoft APC 7.1 Object Library"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\MSAPC.ApcGlobal\CurVer]
@="MSAPC.ApcGlobal.7.1"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{000204EF-0000-0000-C000-000000000046}\4.2\9\win64]
@="C:\\PROGRA~1\\COMMON~1\\MICROS~1\\VBA\\VBA7.1\\VBE7.DLL"

[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\VBA]
"Vbe71DllPath"="C:\\PROGRA~1\\COMMON~1\\MICROS~1\\VBA\\VBA7.1\\VBE7.DLL"

[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\VBA\VBA7.1\Install]
@=dword:00000001

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{0D452EE1-E08F-101A-852E-02608C4D0BB4}\2.0\0\win64]
@="C:\\Windows\\system32\\FM20.DLL"

[HKEY_LOCAL_MACHINE\SOFTWARE\Classes\Installer\Products\FAKE]
"ProductName"="Microsoft VBA 7.1"
''',
        encoding="utf-16",
    )
    append_vba_msi_fixture(layout)
    windows_root = tmp_path / "Windows"
    system32 = windows_root / "System32"
    system32.mkdir(parents=True)
    (system32 / "FM20.DLL").write_bytes(b"")
    (system32 / "FM20chs.DLL").write_bytes(b"")
    folders = KnownFolders(
        user_profile=Path(r"C:\Users\Tester"),
        appdata=Path(r"C:\Users\Tester\AppData\Roaming"),
        local_appdata=Path(r"C:\Users\Tester\AppData\Local"),
        desktop=Path(r"C:\Users\Tester\Desktop"),
        windows=windows_root,
        program_data=Path(r"C:\ProgramData"),
        public=Path(r"C:\Users\Public"),
        program_files=Path(r"C:\Program Files"),
        program_files_x86=Path(r"C:\Program Files (x86)"),
    )

    plan = InstallPlanner(layout, folders).build()
    files = [op for op in plan.operations if isinstance(op, InstallArchiveFile)]
    values = [op for op in plan.operations if isinstance(op, SetRegistryValue)]

    assert plan.metadata["vba_enabled"] is True
    assert len(files) == 14
    assert all("FM20" not in op.member.upper() for op in files)
    assert all("\\Windows\\System32" not in str(op.destination) for op in files)
    assert any("AcVBA2024.Bundle" in str(op.destination) for op in files)
    assert any("VBA7.1" in str(op.destination) for op in files)
    assert all(
        op.reuse_existing
        for op in files
        if "Common Files" in op.member
    )
    assert all(
        not op.reuse_existing
        for op in files
        if "AcVBA2024.Bundle" in op.member
    )
    assert any("\\Applications\\AcadVBA" in op.key for op in values)
    acadvba_values = [
        op for op in values if "\\applications\\acadvba" in op.key.casefold()
    ]
    assert acadvba_values
    assert all(op.preserve_existing for op in acadvba_values)
    assert any("MSAPC.ApcGlobal" in op.key for op in values)
    assert any("SOFTWARE\\Microsoft\\VBA" in op.key for op in values)
    assert all("\\Installer\\Products\\FAKE" not in op.key for op in values)
    assert all("\\SourceList" not in op.key for op in values)
    assert all(op.name not in {"LocalPackage", "InstallSource", "PackageCode"} for op in values)
    assert all("0D452EE1-E08F-101A-852E-02608C4D0BB4" not in op.key for op in values)

    component_values = [
        op
        for op in values
        if op.key.casefold().startswith((VBA_MSI_COMPONENT_CLIENT_ROOT + "\\").casefold())
    ]
    assert all(op.preserve_existing for op in component_values)
    assert {
        (op.key.rsplit("\\", 1)[-1], op.name)
        for op in component_values
    } == (
        {(VBA_ENABLER_ACVBA_PACKED_COMPONENT, VBA_ENABLER_PACKED_PRODUCT)}
        | {(component, VBA71_PACKED_PRODUCT) for component in VBA71_REQUIRED_COMPONENTS}
        | {
            (component, VBA71_2052_PACKED_PRODUCT)
            for component in VBA71_2052_REQUIRED_COMPONENTS
        }
    )
    assert len(component_values) == (
        1 + len(VBA71_REQUIRED_COMPONENTS) + len(VBA71_2052_REQUIRED_COMPONENTS)
    )
    # Exhaustive Feature-state A/B proved these two 2052 help components are
    # not needed to make VBAIntl LOCAL or to satisfy qualified-component
    # resolution.  Keep them out of the portable runtime identity.
    assert all(
        op.key.rsplit("\\", 1)[-1]
        not in {
            "510B39BF82203DD46BD61B5EDBCCC141",  # VBCN6.CHM
            "81C4E51E4B74CD4498C9EB0AC0DDC578",  # FM20.CHM
        }
        for op in component_values
    )
    assert any(
        op.key.endswith("\\" + VBA71_FM20_PACKED_COMPONENT)
        and str(op.data).replace("/", "\\").lower().endswith(
            r"\windows\system32\fm20.dll"
        )
        for op in component_values
    )

    assert any(
        op.key.casefold()
        == rf"{HKLM_INSTALLER_CLASSES}\Features\{VBA71_PACKED_PRODUCT}".casefold()
        and op.name == VBA71_FEATURE
        and op.data == ""
        for op in values
    )
    assert any(
        op.key.casefold()
        == rf"{HKLM_INSTALLER_USERDATA_SYSTEM}\Products\{VBA71_PACKED_PRODUCT}\InstallProperties".casefold()
        and op.name == "WindowsInstaller"
        and op.data == 1
        for op in values
    )
    qualified = next(
        op
        for op in values
        if op.key.casefold()
        == rf"{HKLM_INSTALLER_CLASSES}\Components\{VBA71_QUALIFIED_CATEGORY_PACKED}".casefold()
        and op.name == VBA71_QUALIFIER_2052
    )
    assert qualified.kind == "multi_sz"
    assert qualified.data == ["descriptor"]
    assert qualified.preserve_existing is True
    vbe_path = next(
        op
        for op in values
        if op.key.endswith(r"SOFTWARE\Microsoft\VBA") and op.name == "Vbe71DllPath"
    )
    vbe_path_text = str(vbe_path.data).replace("/", "\\")
    assert vbe_path_text.startswith(
        r"C:\Program Files\Common Files\Microsoft Shared\VBA"
    )
    assert "PROGRA~1" not in vbe_path_text.upper()
    assert vbe_path.preserve_existing is True
    msi_values = [
        op
        for op in values
        if "\\Installer\\" in op.key
        or "\\CurrentVersion\\Installer\\UserData\\" in op.key
    ]
    assert msi_values
    assert all(op.preserve_existing for op in msi_values)
    assert validate_core_plan(plan, layout) == ()

