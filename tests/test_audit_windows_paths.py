from __future__ import annotations

from pathlib import Path

from acad_portable.audit import (
    _destination_within_vba_root,
    _is_within_root,
    _vba_allowed_file_roots,
    validate_core_plan,
)
from acad_portable.ops import InstallArchiveFile, SetRegistryValue
from acad_portable.planner import InstallPlan

from test_planner import make_package


def _archive_plan(
    layout,
    *,
    member: str,
    destination: Path,
    metadata: dict[str, object],
) -> InstallPlan:
    return InstallPlan(
        operations=(
            InstallArchiveFile(layout.vba_archive, member, destination, "zzz"),
        ),
        warnings=(),
        metadata={"vba_enabled": True, **metadata},
    )


class _PosixPath:
    """Minimal POSIX-like path used to emulate the Ubuntu CI host.

    On POSIX, ``Path("C:\\...")`` is relative and ``/`` joins with a
    forward slash, so the pre-fix audit appended the Windows loader to the
    POSIX ``autocad_root``.  Emulating those two semantics lets the
    regression bind on a Windows developer host too.
    """

    def __init__(self, value: object) -> None:
        self._value = str(value)

    def __truediv__(self, other: object) -> "_PosixPath":
        return _PosixPath(self._value.rstrip("/") + "/" + str(other))

    def is_absolute(self) -> bool:
        return self._value.replace("\\", "/").startswith("/")

    def resolve(self, strict: bool = False) -> "_PosixPath":
        return self

    def exists(self) -> bool:
        return False

    def __str__(self) -> str:
        return self._value

    def __fspath__(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(self._value)


def test_windows_absolute_loader_is_not_joined_to_posix_autocad_root(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression for the Ubuntu CI ``LOADER_MISSING`` failure.

    The loader value is a Windows absolute path while the host is POSIX, so
    the pre-fix audit treated it as relative and joined it onto
    ``layout.autocad_root``.  The Windows path must never be appended to the
    AutoCAD root and must still match the planned archive destination.
    """
    import dataclasses

    import acad_portable.audit as audit_module

    layout = make_package(tmp_path)
    posix_root = _PosixPath("/home/runner/work/pkg/AutoCAD 2024")
    posix_layout = dataclasses.replace(layout, autocad_root=posix_root)
    monkeypatch.setattr(audit_module, "Path", _PosixPath)

    windows_loader = (
        r"C:\Program Files\Autodesk\ApplicationPlugins"
        r"\AcVBA2024.Bundle\Contents\AcVba.arx"
    )
    planned_destination = _PosixPath(
        r"C:\Program Files\Autodesk\ApplicationPlugins"
        r"\AcVBA2024.Bundle\Contents\AcVba.arx"
    )
    plan = InstallPlan(
        operations=(
            SetRegistryValue(
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
                r"\ACAD-7101:804\Applications\AcadVBA",
                "LOADER",
                "sz",
                windows_loader,
            ),
            InstallArchiveFile(
                layout.vba_archive,
                "Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/Contents/AcVba.arx",
                planned_destination,
                "zzz",
            ),
        ),
        warnings=(),
        metadata={
            "vba_enabled": True,
            "program_files": r"C:\Program Files",
            "program_files_x86": r"C:\Program Files (x86)",
        },
    )

    findings = validate_core_plan(plan, posix_layout)

    assert not any(finding.code == "LOADER_MISSING" for finding in findings)
    assert not any(
        str(posix_root) in finding.message for finding in findings
    )


def test_loader_message_keeps_windows_path_verbatim_when_missing(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    windows_loader = r"C:\Missing\Place\AcVba.arx"
    plan = InstallPlan(
        operations=(
            SetRegistryValue(
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
                r"\ACAD-7101:804\Applications\AcadVBA",
                "LOADER",
                "sz",
                windows_loader,
            ),
        ),
        warnings=(),
        metadata={"vba_enabled": True},
    )

    findings = validate_core_plan(plan, layout)
    missing = [f for f in findings if f.code == "LOADER_MISSING"]

    assert len(missing) == 1
    assert missing[0].message == windows_loader


def test_relocated_program_files_roots_pass_audit(tmp_path: Path) -> None:
    """Configured, relocated program-files roots must not be rejected."""
    layout = make_package(tmp_path)
    apps64 = tmp_path / "Apps64"
    apps32 = tmp_path / "Apps32"
    plan = InstallPlan(
        operations=(
            InstallArchiveFile(
                layout.vba_archive,
                "Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/Contents/AcVba.arx",
                apps64 / "Autodesk" / "ApplicationPlugins" / "AcVBA2024.Bundle" / "Contents" / "AcVba.arx",
                "zzz",
            ),
            InstallArchiveFile(
                layout.vba_archive,
                "Program Files (x86)/Common Files/Microsoft Shared/VBA/VBA6/VBE6EXT.OLB",
                apps32 / "Common Files" / "Microsoft Shared" / "VBA" / "VBA6" / "VBE6EXT.OLB",
                "zzz",
            ),
        ),
        warnings=(),
        metadata={
            "vba_enabled": True,
            "program_files": str(apps64),
            "program_files_x86": str(apps32),
        },
    )

    findings = validate_core_plan(plan, layout)

    assert not any(finding.code == "VBA_FILE_ROOT" for finding in findings)


def test_archive_destination_outside_configured_root_is_rejected(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    apps64 = tmp_path / "Apps64"
    outside = tmp_path / "Elsewhere" / "AcVba.arx"
    plan = _archive_plan(
        layout,
        member="Program Files/Autodesk/AcVba.arx",
        destination=outside,
        metadata={"program_files": str(apps64), "program_files_x86": str(apps64)},
    )

    findings = validate_core_plan(plan, layout)

    assert any(finding.code == "VBA_FILE_ROOT" for finding in findings)


def test_archive_destination_traversal_escape_is_rejected(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    apps64 = tmp_path / "Apps64"
    escape = apps64 / ".." / "Outside" / "AcVba.arx"
    plan = _archive_plan(
        layout,
        member="Program Files/Autodesk/AcVba.arx",
        destination=escape,
        metadata={"program_files": str(apps64), "program_files_x86": str(apps64)},
    )

    findings = validate_core_plan(plan, layout)

    assert any(finding.code == "VBA_FILE_ROOT" for finding in findings)


def test_archive_destination_sibling_prefix_is_rejected(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    apps64 = tmp_path / "Apps64"
    sibling = tmp_path / "Apps64-other" / "AcVba.arx"
    plan = _archive_plan(
        layout,
        member="Program Files/Autodesk/AcVba.arx",
        destination=sibling,
        metadata={"program_files": str(apps64), "program_files_x86": str(apps64)},
    )

    findings = validate_core_plan(plan, layout)

    assert any(finding.code == "VBA_FILE_ROOT" for finding in findings)


def test_missing_configured_root_metadata_fails_closed(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    plan = _archive_plan(
        layout,
        member="Program Files/Autodesk/AcVba.arx",
        destination=tmp_path / "Apps64" / "Autodesk" / "AcVba.arx",
        metadata={},
    )

    findings = validate_core_plan(plan, layout)

    assert any(finding.code == "VBA_FILE_ROOT" for finding in findings)


def test_unsupported_member_prefix_fails_closed(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    plan = _archive_plan(
        layout,
        member="Windows/system32/evil.dll",
        destination=tmp_path / "Apps64" / "evil.dll",
        metadata={"program_files": str(tmp_path / "Apps64")},
    )

    findings = validate_core_plan(plan, layout)

    assert any(finding.code == "VBA_FILE_ROOT" for finding in findings)


def test_windows_path_containment_helpers_are_host_independent() -> None:
    # Backslashes, forward slashes and casing are all equivalent.
    assert _is_within_root(
        r"C:\Program Files\Autodesk\AcVba.arx", r"c:/program files"
    )
    assert _is_within_root(r"C:\Program Files", r"C:\Program Files")
    # A sibling with a shared textual prefix is not contained.
    assert not _is_within_root(r"C:\Program Files (x86)\x.dll", r"C:\Program Files")
    # Parent traversal escapes.
    assert not _is_within_root(r"C:\Program Files\..\Outside\x.dll", r"C:\Program Files")

    roots = _vba_allowed_file_roots(
        InstallPlan(
            operations=(),
            warnings=(),
            metadata={
                "program_files": r"D:\Apps64",
                "program_files_x86": r"D:\Apps32",
            },
        )
    )
    assert roots == {
        "Program Files/": r"D:\Apps64",
        "Program Files (x86)/": r"D:\Apps32",
    }


def test_destination_within_vba_root_selects_matching_prefix(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    roots = {"Program Files/": r"D:\Apps64", "Program Files (x86)/": r"D:\Apps32"}
    ok = InstallArchiveFile(
        layout.vba_archive,
        "Program Files (x86)/Common Files/x.dll",
        Path(r"D:\Apps32\Common Files\x.dll"),
        "zzz",
    )
    bad = InstallArchiveFile(
        layout.vba_archive,
        "Program Files (x86)/Common Files/x.dll",
        Path(r"D:\Apps64\Common Files\x.dll"),
        "zzz",
    )
    assert _destination_within_vba_root(ok, roots) is True
    assert _destination_within_vba_root(bad, roots) is False


def test_existing_native_absolute_loader_is_found(tmp_path: Path) -> None:
    """A real, existing absolute loader must be found with native existence.

    Building the candidate by replacing a forward slash with a backslash
    would turn a real
    POSIX path into a nonexistent backslash filename and emit a spurious
    ``LOADER_MISSING``.  There is deliberately no planned archive file here.
    """
    layout = make_package(tmp_path)
    loader_file = tmp_path / "Existing AcVba.arx"
    loader_file.write_bytes(b"arx")
    plan = InstallPlan(
        operations=(
            SetRegistryValue(
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
                r"\ACAD-7101:804\Applications\AcadVBA",
                "LOADER",
                "sz",
                str(loader_file),
            ),
        ),
        warnings=(),
        metadata={"vba_enabled": True},
    )

    findings = validate_core_plan(plan, layout)

    assert not any(finding.code == "LOADER_MISSING" for finding in findings)


def test_missing_native_absolute_loader_reports_original_path(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    missing = tmp_path / "Missing AcVba.arx"
    plan = InstallPlan(
        operations=(
            SetRegistryValue(
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3"
                r"\ACAD-7101:804\Applications\AcadVBA",
                "LOADER",
                "sz",
                str(missing),
            ),
        ),
        warnings=(),
        metadata={"vba_enabled": True},
    )

    findings = validate_core_plan(plan, layout)
    reported = [f.message for f in findings if f.code == "LOADER_MISSING"]

    assert reported == [str(missing)]
