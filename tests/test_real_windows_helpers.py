from __future__ import annotations

from pathlib import Path

from acad_portable.ops import CreateShortcut, SetRegistryValue
from acad_portable.real_windows import (
    _decode_json_value,
    _encode_json_value,
    _new_state,
    _ps_quote,
    _registry_operation_matches_snapshot,
    inspect_install_state,
)


def test_json_registry_value_roundtrip() -> None:
    values = [b"\x00\xff", ["a", "b"], (1, "x"), "plain", 123]
    for value in values:
        assert _decode_json_value(_encode_json_value(value)) == value


def test_powershell_quote_handles_apostrophe_and_unicode() -> None:
    assert _ps_quote("C:\\Tiger's CAD\\中文") == "'C:\\Tiger''s CAD\\中文'"


def test_new_state_has_ownership_sections() -> None:
    state = _new_state()
    assert state["schema"] == 1
    assert state["registry_values"] == {}
    assert state["created_junctions"] == {}
    assert state["created_files"] == {}
    assert state["shortcuts"] == {}


def test_shortcut_operation_is_plain_data() -> None:
    op = CreateShortcut(Path("a.lnk"), Path("acad.exe"), "/nologo", Path("."))
    assert op.arguments == "/nologo"


def test_inspect_install_state_missing_and_invalid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert inspect_install_state(path) == {"exists": False, "status": None}

    path.write_text("not-json", encoding="utf-8")
    status = inspect_install_state(path)
    assert status["exists"] is True
    assert status["status"] == "invalid"


def test_vbe71_registry_path_treats_same_file_as_equivalent(tmp_path: Path, monkeypatch) -> None:
    operation = SetRegistryValue(
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\VBA",
        "Vbe71DllPath",
        "sz",
        r"C:\Program Files\Common Files\Microsoft Shared\VBA\VBA7.1\VBE7.DLL",
    )
    snapshot = {
        "type": 1,
        "data": r"C:\PROGRA~1\COMMON~1\MICROS~1\VBA\VBA7.1\VBE7.DLL",
    }
    monkeypatch.setattr("acad_portable.real_windows._same_path", lambda left, right: True)

    assert _registry_operation_matches_snapshot(operation, snapshot) is True
