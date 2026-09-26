from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    candidates: list[Path] = []
    for name in ("7z.exe", "7za.exe", "7zr.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    for base in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ):
        for rel in (Path("7-Zip/7z.exe"), Path("7-Zip/7za.exe")):
            candidate = base / rel
            if candidate.is_file():
                candidates.append(candidate)

    bundled = Path("AutoCAD 2024") / "ACAOE" / "hui7za.dll"
    if bundled.is_file():
        candidates.append(bundled.resolve())

    unique = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate.resolve())

    print(f"count={len(unique)}")
    for candidate in unique:
        print(candidate)
        header = candidate.read_bytes()[:2]
        print(f"  mz={header == b'MZ'}")
        try:
            probe = subprocess.run(
                [str(candidate), "i"],
                capture_output=True,
                text=True,
                encoding="mbcs",
                errors="replace",
                timeout=10,
                check=False,
            )
        except OSError as exc:
            print(f"  execute_error={type(exc).__name__}: {exc}")
            continue
        print(f"  exit={probe.returncode}")
        summary = (probe.stdout + "\n" + probe.stderr).strip().replace("\r", "")
        print(summary[:4000])
    return 0 if unique else 1


if __name__ == "__main__":
    raise SystemExit(main())
