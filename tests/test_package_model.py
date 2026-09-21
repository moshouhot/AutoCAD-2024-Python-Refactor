from __future__ import annotations

from pathlib import Path

import pytest

from acad_portable.model import PackageError, PackageLayout


def make_minimal_package(root: Path) -> Path:
    acad = root / "AutoCAD 2024"
    (acad / "ACAOE" / "CHS").mkdir(parents=True)
    (acad / "Support").mkdir(parents=True)
    (acad / "0加载应用程序").mkdir(parents=True)
    for path in (
        acad / "acad.exe",
        acad / "ACAOE" / "reg1.dli",
        acad / "ACAOE" / "reg2.dli",
        acad / "ACAOE" / "reg3.dli",
        acad / "ACAOE" / "配置.txt",
        acad / "Support" / "acad2024.lsp",
        acad / "Support" / "appload.lsp",
    ):
        path.write_bytes(b"")
    return acad


def test_package_layout_discovers_project_root(tmp_path: Path) -> None:
    acad = make_minimal_package(tmp_path)
    layout = PackageLayout.discover(tmp_path)
    assert layout.autocad_root == acad.resolve()
    assert layout.acaoe == (acad / "ACAOE").resolve()


def test_package_layout_reports_missing_required_input(tmp_path: Path) -> None:
    acad = make_minimal_package(tmp_path)
    (acad / "Support" / "appload.lsp").unlink()

    with pytest.raises(PackageError, match="appload.lsp"):
        PackageLayout.discover(tmp_path)

