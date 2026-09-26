"""Containment tests for archive member extraction/read (PR #4 symlink escape).

``_read_archive_member`` must never read a payload through a symlink/reparse
point, nor read a member that resolves outside the temp extraction root.  The
tests below exercise the dedicated ``_validated_extracted_member`` helper
directly (fast, deterministic) plus the full ``_read_archive_member`` path with
a real py7zr archive and with a mocked extractor that plants an escaping link.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import acad_portable.real_windows as rw
from acad_portable.ops import InstallArchiveFile


def _symlinks_supported() -> bool:
    return hasattr(os, "symlink")


def _make_symlink(link: Path, target: Path, *, is_dir: bool) -> None:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError):
        pytest.skip("host does not allow creating symlinks")


# --------------------------------------------------------------------------
# _validated_extracted_member: happy path
# --------------------------------------------------------------------------


def test_validated_member_accepts_regular_nested_member(tmp_path: Path) -> None:
    temp_root = tmp_path / "root"
    member_path = temp_root / "Program Files" / "runtime.dll"
    member_path.parent.mkdir(parents=True)
    member_path.write_bytes(b"payload")

    resolved = rw._validated_extracted_member(temp_root, "Program Files/runtime.dll")

    assert resolved == member_path.resolve(strict=True)
    assert resolved.read_bytes() == b"payload"


def test_validated_member_accepts_backslash_member(tmp_path: Path) -> None:
    temp_root = tmp_path / "root"
    member_path = temp_root / "a" / "b.dll"
    member_path.parent.mkdir(parents=True)
    member_path.write_bytes(b"x")

    resolved = rw._validated_extracted_member(temp_root, "a\\b.dll")

    assert resolved == member_path.resolve(strict=True)


# --------------------------------------------------------------------------
# _validated_extracted_member: rejected shapes
# --------------------------------------------------------------------------


def test_member_itself_symlink_is_rejected(tmp_path: Path) -> None:
    if not _symlinks_supported():
        pytest.skip("host does not allow creating symlinks")
    temp_root = tmp_path / "root"
    temp_root.mkdir()
    outside = tmp_path / "outside.dll"
    outside.write_bytes(b"secret")
    _make_symlink(temp_root / "runtime.dll", outside, is_dir=False)

    with pytest.raises(RuntimeError, match="reparse point"):
        rw._validated_extracted_member(temp_root, "runtime.dll")


def test_ancestor_directory_symlink_is_rejected(tmp_path: Path) -> None:
    if not _symlinks_supported():
        pytest.skip("host does not allow creating symlinks")
    temp_root = tmp_path / "root"
    temp_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "runtime.dll").write_bytes(b"secret")
    _make_symlink(temp_root / "Program Files", outside_dir, is_dir=True)

    with pytest.raises(RuntimeError, match="reparse point"):
        rw._validated_extracted_member(temp_root, "Program Files/runtime.dll")


def test_resolved_escape_rejected_when_detector_is_blind(
    tmp_path: Path, monkeypatch
) -> None:
    """Defence in depth: even if the lstat detector misses a link, resolve()
    must still catch the escape out of the extraction root."""
    if not _symlinks_supported():
        pytest.skip("host does not allow creating symlinks")
    temp_root = tmp_path / "root"
    temp_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "runtime.dll").write_bytes(b"secret")
    _make_symlink(temp_root / "linked", outside_dir, is_dir=True)
    monkeypatch.setattr(rw, "_is_reparse_or_symlink", lambda path: False)

    with pytest.raises(RuntimeError, match="escapes the extraction root"):
        rw._validated_extracted_member(temp_root, "linked/runtime.dll")


def test_reparse_detection_at_root_intermediate_and_leaf(
    tmp_path: Path, monkeypatch
) -> None:
    """Deterministic reparse coverage that does not need host symlink support."""
    temp_root = tmp_path / "root"
    (temp_root / "a").mkdir(parents=True)
    (temp_root / "a" / "b.dll").write_bytes(b"payload")

    real_detector = rw._is_reparse_or_symlink

    # Extraction root itself is flagged.
    monkeypatch.setattr(
        rw, "_is_reparse_or_symlink", lambda path: path == temp_root
    )
    with pytest.raises(RuntimeError, match="extraction root is a reparse point"):
        rw._validated_extracted_member(temp_root, "a/b.dll")

    # Intermediate directory is flagged.
    monkeypatch.setattr(
        rw, "_is_reparse_or_symlink", lambda path: path == temp_root / "a"
    )
    with pytest.raises(RuntimeError, match="traverses a reparse point"):
        rw._validated_extracted_member(temp_root, "a/b.dll")

    # Leaf member is flagged.
    monkeypatch.setattr(
        rw, "_is_reparse_or_symlink", lambda path: path == temp_root / "a" / "b.dll"
    )
    with pytest.raises(RuntimeError, match="traverses a reparse point"):
        rw._validated_extracted_member(temp_root, "a/b.dll")

    monkeypatch.setattr(rw, "_is_reparse_or_symlink", real_detector)
    assert rw._validated_extracted_member(temp_root, "a/b.dll").is_file()


def test_missing_member_is_rejected(tmp_path: Path) -> None:
    temp_root = tmp_path / "root"
    temp_root.mkdir()

    with pytest.raises(RuntimeError, match="could not be resolved"):
        rw._validated_extracted_member(temp_root, "missing.dll")


def test_directory_member_is_rejected_by_read(tmp_path: Path, monkeypatch) -> None:
    """A mocked extractor plants a directory at the requested member; the
    caller's ``is_file`` gate must raise and never read bytes."""
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"not a real archive")

    class _FakeSevenZipFile:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract(self, path, targets):
            (Path(path) / targets[0]).mkdir(parents=True, exist_ok=True)

    import py7zr

    monkeypatch.setattr(py7zr, "SevenZipFile", _FakeSevenZipFile)

    reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def spy_read_bytes(self):
        reads.append(self)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)

    operation = InstallArchiveFile(archive, "sub", tmp_path / "out.dll")

    with pytest.raises(RuntimeError, match="was not extracted"):
        rw._read_archive_member(operation)

    assert reads == []


def test_root_only_member_is_rejected(tmp_path: Path) -> None:
    temp_root = tmp_path / "root"
    temp_root.mkdir()

    for member in (".", "./", "", "/"):
        with pytest.raises(RuntimeError, match="unsafe archive member path"):
            rw._validated_extracted_member(temp_root, member)


def test_parent_traversal_member_is_rejected(tmp_path: Path) -> None:
    temp_root = tmp_path / "root"
    temp_root.mkdir()
    (tmp_path / "outside.dll").write_bytes(b"secret")

    with pytest.raises(RuntimeError, match="unsafe archive member path"):
        rw._validated_extracted_member(temp_root, "../outside.dll")


def test_drive_relative_member_is_rejected(tmp_path: Path) -> None:
    temp_root = tmp_path / "root"
    temp_root.mkdir()

    with pytest.raises(RuntimeError, match="unsafe archive member path"):
        rw._validated_extracted_member(temp_root, "C:windows/system32/evil.dll")


# --------------------------------------------------------------------------
# _read_archive_member: end-to-end regression + mocked extraction
# --------------------------------------------------------------------------


def _write_archive(archive: Path, member: str, payload: bytes) -> None:
    py7zr = pytest.importorskip("py7zr")
    with py7zr.SevenZipFile(archive, "w") as handle:
        handle.writestr(payload, member)


def test_read_archive_member_normal_member_still_works(tmp_path: Path) -> None:
    archive = tmp_path / "payload.7z"
    _write_archive(archive, "Program Files/runtime.dll", b"runtime-v1")
    operation = InstallArchiveFile(archive, "Program Files/runtime.dll", tmp_path / "out.dll")

    assert rw._read_archive_member(operation) == b"runtime-v1"


def test_read_archive_member_backslash_relative_member_still_works(tmp_path: Path) -> None:
    archive = tmp_path / "payload.7z"
    _write_archive(archive, "Program Files/runtime.dll", b"runtime-v1")
    operation = InstallArchiveFile(
        archive, r"Program Files\runtime.dll", tmp_path / "out.dll"
    )

    assert rw._read_archive_member(operation) == b"runtime-v1"


@pytest.mark.parametrize(
    "member",
    [
        "/absolute/runtime.dll",
        r"\absolute\runtime.dll",
        "//server/share/runtime.dll",
        "C:/absolute/runtime.dll",
        "C:relative/runtime.dll",
        "../runtime.dll",
    ],
)
def test_read_archive_member_rejects_unsafe_member_before_extraction(
    tmp_path: Path, monkeypatch, member: str
) -> None:
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"not a real archive")
    extraction_attempted: list[str] = []

    import py7zr

    def forbidden_extractor(*args, **kwargs):
        extraction_attempted.append("py7zr")
        raise AssertionError("archive extractor must not run for an unsafe member")

    def forbidden_subprocess(*args, **kwargs):
        extraction_attempted.append("subprocess")
        raise AssertionError("bundled extractor must not run for an unsafe member")

    monkeypatch.setattr(py7zr, "SevenZipFile", forbidden_extractor)
    monkeypatch.setattr(rw.subprocess, "run", forbidden_subprocess)
    operation = InstallArchiveFile(archive, member, tmp_path / "out.dll")

    with pytest.raises(RuntimeError, match="unsafe archive member path"):
        rw._read_archive_member(operation)

    assert extraction_attempted == []


def test_read_archive_member_rejects_real_symlink_entry(tmp_path: Path) -> None:
    """Real py7zr archive whose requested member is a symlink entry.

    py7zr restores in-root symlinks and ``read_bytes()`` would follow them;
    the containment guard must reject the member before any read happens.
    """
    if not _symlinks_supported():
        pytest.skip("host does not allow creating symlinks")
    py7zr = pytest.importorskip("py7zr")

    src = tmp_path / "src"
    src.mkdir()
    (src / "real.dll").write_bytes(b"REAL")
    try:
        os.symlink("real.dll", src / "runtime.dll")
    except (OSError, NotImplementedError):
        pytest.skip("host does not allow creating symlinks")

    archive = tmp_path / "payload.7z"
    with py7zr.SevenZipFile(archive, "w") as handle:
        handle.write(src / "real.dll", "real.dll")
        handle.write(src / "runtime.dll", "runtime.dll")

    # Confirm this py7zr build restores symlink entries on this host; if it does
    # not (or sanitises them into regular files), the escape vector is absent
    # here and the real-host coverage is provided by the mocked-extractor test.
    probe = tmp_path / "probe"
    try:
        with py7zr.SevenZipFile(archive, "r") as handle:
            handle.extract(path=probe, targets=["real.dll", "runtime.dll"])
    except Exception:
        pytest.skip("py7zr cannot restore symlink entries on this host")
    if not (probe / "runtime.dll").is_symlink():
        pytest.skip("py7zr did not restore a symlink entry on this host")

    operation = InstallArchiveFile(archive, "runtime.dll", tmp_path / "out.dll")

    with pytest.raises(RuntimeError, match="reparse point"):
        rw._read_archive_member(operation)


def test_read_archive_member_rejects_symlinked_member_before_read(
    tmp_path: Path, monkeypatch
) -> None:
    """A mocked extractor plants an escaping symlink; ``read_bytes`` must never
    run and the failure must be an explicit RuntimeError."""
    outside = tmp_path / "outside.dll"
    outside.write_bytes(b"secret")
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"not a real archive")

    class _FakeSevenZipFile:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract(self, path, targets):
            planted = Path(path) / targets[0]
            planted.parent.mkdir(parents=True, exist_ok=True)
            _make_symlink(planted, outside, is_dir=False)

    import py7zr

    monkeypatch.setattr(py7zr, "SevenZipFile", _FakeSevenZipFile)

    reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def spy_read_bytes(self):
        reads.append(self)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)

    operation = InstallArchiveFile(archive, "runtime.dll", tmp_path / "out.dll")

    with pytest.raises(RuntimeError, match="reparse point"):
        rw._read_archive_member(operation)

    assert reads == []


def test_read_archive_member_rejects_member_resolving_outside_root(
    tmp_path: Path, monkeypatch
) -> None:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "runtime.dll").write_bytes(b"secret")
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"not a real archive")

    class _FakeSevenZipFile:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract(self, path, targets):
            _make_symlink(
                Path(path) / "linked", outside_dir, is_dir=True
            )

    import py7zr

    monkeypatch.setattr(py7zr, "SevenZipFile", _FakeSevenZipFile)
    # Blind the lstat detector so only the resolve()-based containment can fire.
    monkeypatch.setattr(rw, "_is_reparse_or_symlink", lambda path: False)

    operation = InstallArchiveFile(
        archive, "linked/runtime.dll", tmp_path / "out.dll"
    )

    with pytest.raises(RuntimeError, match="escapes the extraction root"):
        rw._read_archive_member(operation)
