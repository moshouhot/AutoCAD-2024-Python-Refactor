from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageLayout:
    project_root: Path
    autocad_root: Path
    acaoe: Path
    chs: Path
    reg1: Path
    reg2: Path
    config: Path
    acad_exe: Path
    support_lsp: Path
    appload_lsp: Path
    extensions_dir: Path

    @classmethod
    def discover(cls, start: Path) -> "PackageLayout":
        start = start.resolve()
        candidates = [start, start / "AutoCAD 2024"]
        autocad_root = next((p for p in candidates if (p / "acad.exe").is_file()), None)
        if autocad_root is None:
            raise PackageError(f"Cannot find acad.exe from package root: {start}")

        project_root = autocad_root.parent if autocad_root != start else start
        acaoe = autocad_root / "ACAOE"
        required = {
            "ACAOE": acaoe,
            "CHS": acaoe / "CHS",
            "reg1.dli": acaoe / "reg1.dli",
            "reg2.dli": acaoe / "reg2.dli",
            "配置.txt": acaoe / "配置.txt",
            "acad2024.lsp": autocad_root / "Support" / "acad2024.lsp",
            "appload.lsp": autocad_root / "Support" / "appload.lsp",
            "0加载应用程序": autocad_root / "0加载应用程序",
        }
        missing = [name for name, path in required.items() if not path.exists()]
        if missing:
            raise PackageError("Missing required package inputs: " + ", ".join(missing))

        return cls(
            project_root=project_root,
            autocad_root=autocad_root,
            acaoe=acaoe,
            chs=acaoe / "CHS",
            reg1=acaoe / "reg1.dli",
            reg2=acaoe / "reg2.dli",
            config=acaoe / "配置.txt",
            acad_exe=autocad_root / "acad.exe",
            support_lsp=autocad_root / "Support" / "acad2024.lsp",
            appload_lsp=autocad_root / "Support" / "appload.lsp",
            extensions_dir=autocad_root / "0加载应用程序",
        )

