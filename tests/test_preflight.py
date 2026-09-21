from __future__ import annotations

from pathlib import Path

from acad_portable.preflight import inspect_autoload_chain

from test_planner import make_package


def test_autoload_chain_static_contract(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    layout.appload_lsp.write_text(
        '0加载应用程序 *.ARX *.LSP *.FAS *.VLX',
        encoding="utf-8",
    )
    assert inspect_autoload_chain(layout) == ()


def test_autoload_chain_reports_missing_capability(tmp_path: Path) -> None:
    layout = make_package(tmp_path)
    layout.appload_lsp.write_text('0加载应用程序 *.LSP', encoding="utf-8")
    findings = inspect_autoload_chain(layout)
    assert any("*.arx" in item for item in findings)
