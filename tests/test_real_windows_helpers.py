from __future__ import annotations

from pathlib import Path

from acad_portable.ops import CreateShortcut
from acad_portable.real_windows import (
    _decode_json_value,
    _encode_json_value,
    _new_state,
    _ps_quote,
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
