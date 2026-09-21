from __future__ import annotations

from acad_portable import cli
from acad_portable.model import PackageError


def test_cli_reports_planner_package_error_without_traceback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.PackageLayout, "discover", lambda _root: object())

    class BrokenPlanner:
        def __init__(self, _layout) -> None:
            pass

        def build(self):
            raise PackageError("Cannot parse AutoCAD registry version from reg2.dli")

    monkeypatch.setattr(cli, "InstallPlanner", BrokenPlanner)

    assert cli.main(["plan"]) == 2
    output = capsys.readouterr().out
    assert output == "ERROR: Cannot parse AutoCAD registry version from reg2.dli\n"
