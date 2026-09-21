from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from acad_portable.ops import CreateShortcut, EnsureJunction, WriteInstallState
from acad_portable.planner import InstallPlan
from acad_portable.real_windows import (
    RealWindowsAdapter,
    _create_junction,
    _create_shortcut,
    _same_path,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows filesystem integration")


def test_real_junction_roundtrip_in_temp(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "probe.txt").write_text("ok", encoding="utf-8")
    link = tmp_path / "link"

    _create_junction(link, target)
    try:
        assert os.path.lexists(link)
        assert _same_path(link, target)
        assert (link / "probe.txt").read_text(encoding="utf-8") == "ok"
    finally:
        if os.path.lexists(link):
            os.rmdir(link)


def test_real_shortcut_creation_in_temp(tmp_path: Path) -> None:
    shortcut = tmp_path / "python-test.lnk"
    operation = CreateShortcut(
        path=shortcut,
        target=Path(sys.executable),
        arguments="--version",
        working_directory=tmp_path,
    )

    _create_shortcut(operation)
    assert shortcut.is_file()
    assert shortcut.stat().st_size > 0


def test_real_adapter_refuses_existing_dangling_junction(tmp_path: Path) -> None:
    old_target = tmp_path / "old-target"
    old_target.mkdir()
    link = tmp_path / "dangling"
    _create_junction(link, old_target)
    old_target.rmdir()
    assert os.path.lexists(link)
    assert not link.exists()

    wanted = tmp_path / "wanted"
    wanted.mkdir()
    state_path = tmp_path / "state.json"
    plan = InstallPlan(
        operations=(
            EnsureJunction(link, wanted),
            WriteInstallState(state_path, {"test": True}),
        ),
        warnings=(),
        metadata={},
    )

    with pytest.raises(RuntimeError, match="already exists"):
        RealWindowsAdapter().apply_plan(plan)
    assert state_path.is_file()

    os.rmdir(link)
