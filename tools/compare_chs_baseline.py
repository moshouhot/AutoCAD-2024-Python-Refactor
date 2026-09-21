from __future__ import annotations

import argparse
import json
from pathlib import Path

import py7zr


def norm(name: str) -> str:
    return name.replace("\\", "/").lstrip("./").lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--password", default="zzz")
    args = parser.parse_args()

    with py7zr.SevenZipFile(args.archive, "r", password=args.password) as archive:
        archive_files = {
            norm(info.filename): {
                "path": info.filename.replace("\\", "/").lstrip("./"),
                "bytes": int(getattr(info, "uncompressed", 0) or 0),
            }
            for info in archive.list()
            if not bool(getattr(info, "is_directory", False))
            and not info.filename.endswith(("/", "\\"))
        }

    current_files = {}
    for path in args.current.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(args.current).as_posix()
        current_files[norm(rel)] = {"path": rel, "bytes": path.stat().st_size}

    missing = [archive_files[k] for k in sorted(archive_files.keys() - current_files.keys())]
    extra = [current_files[k] for k in sorted(current_files.keys() - archive_files.keys())]
    size_mismatch = []
    for key in sorted(archive_files.keys() & current_files.keys()):
        a = archive_files[key]
        c = current_files[key]
        if a["bytes"] != c["bytes"]:
            size_mismatch.append(
                {
                    "path": c["path"],
                    "archive_bytes": a["bytes"],
                    "current_bytes": c["bytes"],
                }
            )

    result = {
        "archive_file_count": len(archive_files),
        "current_file_count": len(current_files),
        "missing_from_current": missing,
        "extra_in_current": extra,
        "size_mismatch": size_mismatch,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"archive={len(archive_files)} current={len(current_files)}")
    print(f"missing={len(missing)} extra={len(extra)} size_mismatch={len(size_mismatch)}")
    for title, items in (
        ("missing", missing),
        ("extra", extra),
        ("size_mismatch", size_mismatch),
    ):
        if items:
            print(f"[{title}]")
            for item in items[:50]:
                print(json.dumps(item, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
