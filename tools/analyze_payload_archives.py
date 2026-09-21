from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path, PurePosixPath

import py7zr


KEYWORDS = (
    "acsign",
    "fm20",
    "vba",
    "webview",
    "msedge",
    "setup.exe",
    "sample.cus",
    "plotman.cpl",
    "styleman.cpl",
    "packagecontents.xml",
)


def normalize_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("./")


def analyze(path: Path, password: str | None) -> dict:
    with py7zr.SevenZipFile(path, mode="r", password=password) as archive:
        infos = archive.list()

    files = []
    dirs = 0
    extensions = Counter()
    top_levels = Counter()
    total_uncompressed = 0
    interesting = []

    for info in infos:
        name = normalize_name(info.filename)
        is_dir = bool(getattr(info, "is_directory", False)) or name.endswith("/")
        if is_dir:
            dirs += 1
            continue

        size = int(getattr(info, "uncompressed", 0) or 0)
        total_uncompressed += size
        files.append({"path": name, "bytes": size})

        pure = PurePosixPath(name)
        top_levels[pure.parts[0] if pure.parts else name] += 1
        extensions[pure.suffix.lower() or "<none>"] += 1

        lowered = name.lower()
        if any(keyword in lowered for keyword in KEYWORDS):
            interesting.append({"path": name, "bytes": size})

    return {
        "archive": str(path),
        "bytes": path.stat().st_size,
        "file_count": len(files),
        "directory_count": dirs,
        "total_uncompressed_bytes": total_uncompressed,
        "top_levels": dict(top_levels),
        "extensions": dict(extensions),
        "interesting": interesting,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--password", default="zzz")
    args = parser.parse_args()

    relpaths = [
        "default.dll",
        "guanfang.dll",
        "Tohomedrive.dll",
        "app/VBA.dll",
        "app/auedgewebview.dll",
    ]

    results = []
    for rel in relpaths:
        path = args.root / rel
        if not path.exists():
            results.append({"archive": str(path), "error": "missing"})
            continue
        try:
            item = analyze(path, args.password)
        except Exception as exc:  # local evidence tool: preserve exact failure class
            item = {"archive": str(path), "error": f"{type(exc).__name__}: {exc}"}
        results.append(item)

    payload = {"archives": results}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in results:
        if "error" in item:
            print(f"{item['archive']}: ERROR {item['error']}")
            continue
        print(
            f"{Path(item['archive']).name}: files={item['file_count']} "
            f"dirs={item['directory_count']} bytes={item['total_uncompressed_bytes']} "
            f"interesting={len(item['interesting'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
