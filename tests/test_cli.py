from __future__ import annotations

import json
from types import SimpleNamespace

from acad_portable import cli
from acad_portable.model import PackageError
from acad_portable.real_windows import LiveDiffReport


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


def _patch_diff_report(monkeypatch, report: LiveDiffReport) -> None:
    monkeypatch.setattr(cli.PackageLayout, "discover", lambda _root: object())

    class FakePlanner:
        def __init__(self, _layout) -> None:
            pass

        def build(self):
            return SimpleNamespace(warnings=(), operations=())

    monkeypatch.setattr(cli, "InstallPlanner", FakePlanner)
    monkeypatch.setattr(cli, "validate_core_plan", lambda _plan, _layout: [])
    monkeypatch.setattr(cli, "inspect_live_diff", lambda _plan: report)


def _live_diff_report(
    *,
    file_upgrade: int,
    file_conflict: int = 0,
    registry_retire: int = 0,
    file_retire: int = 0,
) -> LiveDiffReport:
    return LiveDiffReport(
        registry_same=0,
        registry_change=0,
        registry_external_preserved=0,
        registry_create=0,
        registry_keys_create=0,
        junction_same=0,
        junction_create=0,
        junction_conflict=0,
        shortcut_existing=0,
        shortcut_create=0,
        file_same=0,
        file_reuse=0,
        file_create=0,
        file_conflict=file_conflict,
        details=(),
        file_upgrade=file_upgrade,
        registry_retire=registry_retire,
        file_retire=file_retire,
    )


def test_diff_reports_file_upgrade_in_json_and_text(monkeypatch, capsys) -> None:
    report = _live_diff_report(file_upgrade=7)
    _patch_diff_report(monkeypatch, report)

    assert cli.main(["diff", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == {
        "same": 0,
        "reuse": 0,
        "create": 0,
        "conflict": 0,
        "upgrade": 7,
        "retire": 0,
    }

    assert cli.main(["diff"]) == 0
    lines = capsys.readouterr().out.splitlines()
    files_line = next(line for line in lines if line.startswith("Files        :"))
    assert "upgrade=7" in files_line


def test_diff_file_upgrade_does_not_change_conflict_exit_code(monkeypatch, capsys) -> None:
    report = _live_diff_report(file_upgrade=3, file_conflict=1)
    _patch_diff_report(monkeypatch, report)

    assert cli.main(["diff", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"]["upgrade"] == 3
    assert payload["files"]["conflict"] == 1


def test_diff_reports_retire_aggregate_in_json_and_text(monkeypatch, capsys) -> None:
    report = _live_diff_report(file_upgrade=0, registry_retire=2, file_retire=5)
    _patch_diff_report(monkeypatch, report)

    assert cli.main(["diff", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry"]["retire"] == 2
    assert payload["files"]["retire"] == 5

    assert cli.main(["diff"]) == 0
    lines = capsys.readouterr().out.splitlines()
    registry_line = next(line for line in lines if line.startswith("Registry     :"))
    files_line = next(line for line in lines if line.startswith("Files        :"))
    assert "retire=2" in registry_line
    assert "retire=5" in files_line


def test_diff_retire_does_not_change_conflict_exit_code(monkeypatch, capsys) -> None:
    report = _live_diff_report(file_upgrade=0, file_conflict=1, registry_retire=4, file_retire=4)
    _patch_diff_report(monkeypatch, report)

    assert cli.main(["diff", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry"]["retire"] == 4
    assert payload["files"]["retire"] == 4
