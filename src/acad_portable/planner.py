from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .config import FeatureConfig
from .model import PackageError, PackageLayout
from .ops import (
    CreateShortcut,
    EnsureDirectory,
    EnsureJunction,
    EnsureRegistryKey,
    Operation,
    SetRegistryValue,
    WriteInstallState,
)
from .registry import PathRebaser, RegistryDocument


HKCU_AUTOCAD = r"HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD"
HKLM_AUTOCAD = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD"
HKCU_CLASSES = r"HKEY_CURRENT_USER\SOFTWARE\Classes"
HKLM_CLASSES = r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes"
HISTORICAL_USER_RE = re.compile(r"(?i)[A-Z]:\\Users\\[^\\\";]+")
AUTOCAD_MARKER = "\\autocad 2024"

AUTOCAD_APPLICATION_COM_PREFIXES = (
    rf"{HKCU_CLASSES}\AutoCAD.Application",
    rf"{HKLM_CLASSES}\AutoCAD.Application.24",
    rf"{HKLM_CLASSES}\CLSID\{{8B4929F8-076F-4AEC-AFEE-8928747B7AE3}}",
    rf"{HKLM_CLASSES}\CLSID\{{AA46BA8A-9825-40FD-8493-0BA3C4D5CEB5}}",
    rf"{HKLM_CLASSES}\CLSID\{{169B5B8E-E315-41C7-9574-66FC7E530D10}}",
    rf"{HKLM_CLASSES}\CLSID\{{AF18D91C-A699-4578-ADC6-972F3BA007F0}}",
    rf"{HKLM_CLASSES}\TypeLib\{{AA9A2205-75AA-43AD-9138-1767F1BB5E0C}}",
)

AUTOCAD_REG3_CORE_PREFIXES = AUTOCAD_APPLICATION_COM_PREFIXES + (
    r"HKEY_CURRENT_USER\SOFTWARE\Autodesk\DwgCommon",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Drawing Check",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\Hardcopy",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\ObjectDBX",
    rf"{HKLM_CLASSES}\ObjectDBX.AxDbDocument.24",
    rf"{HKLM_CLASSES}\CLSID\{{39C92898-2FBB-4629-8E1B-6968D3122EC4}}",
    rf"{HKLM_CLASSES}\TypeLib\{{39FFAA00-8623-488F-8C53-DD3B0B7A464F}}",
)


@dataclass(frozen=True)
class KnownFolders:
    user_profile: Path
    appdata: Path
    local_appdata: Path
    desktop: Path
    windows: Path
    program_data: Path
    public: Path

    @classmethod
    def current(cls) -> "KnownFolders":
        user = Path(os.environ.get("USERPROFILE", str(Path.home())))
        appdata = Path(os.environ.get("APPDATA", str(user / "AppData" / "Roaming")))
        local = Path(os.environ.get("LOCALAPPDATA", str(user / "AppData" / "Local")))
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        public = Path(os.environ.get("PUBLIC", str(user.parent / "Public")))
        desktop = _desktop_folder(user)
        return cls(user, appdata, local, desktop, windows, program_data, public)


@dataclass(frozen=True)
class InstallPlan:
    operations: tuple[Operation, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, object]

    def summary(self) -> dict[str, int]:
        return dict(Counter(type(op).__name__ for op in self.operations))


class InstallPlanner:
    def __init__(self, layout: PackageLayout, folders: KnownFolders | None = None):
        self.layout = layout
        self.folders = folders or KnownFolders.current()

    def build(self) -> InstallPlan:
        config = FeatureConfig.load(self.layout.config)
        reg1 = RegistryDocument.load(self.layout.reg1)
        reg2 = RegistryDocument.load(self.layout.reg2)
        reg3 = RegistryDocument.load(self.layout.reg3)
        acad_location = reg2.first_string("AcadLocation")
        product_name = reg2.first_string("ProductNameGlob") or "AutoCAD 2024"

        version = self._version_from_keys(reg2)
        if version is None:
            raise PackageError("Cannot parse AutoCAD registry version from reg2.dli")
        mappings = self._path_mappings(reg1, reg2, acad_location)
        rebaser = PathRebaser(mappings)

        operations: list[Operation] = []
        warnings: list[str] = []
        operations.extend(self._registry_ops(reg1, HKCU_AUTOCAD, rebaser, warnings, source="reg1"))
        operations.extend(self._registry_ops(reg2, HKLM_AUTOCAD, rebaser, warnings, source="reg2"))
        operations.extend(self._reg3_core_ops(reg3, rebaser, warnings))

        local_product = self.folders.local_appdata / "Autodesk" / product_name / version
        roaming_product = self.folders.appdata / "Autodesk" / product_name / version
        for parent in (local_product, roaming_product):
            operations.append(EnsureDirectory(parent))
            operations.append(EnsureJunction(parent / "chs", self.layout.chs))

        if config.enabled("桌面快捷方式", default=True):
            operations.append(
                CreateShortcut(
                    path=self.folders.desktop / f"{product_name}.lnk",
                    target=self.layout.acad_exe,
                    arguments="/nologo",
                    working_directory=self.layout.autocad_root,
                )
            )

        operations.extend(self._wizard_shortcuts())
        operations.append(
            WriteInstallState(
                path=self.layout.acaoe / ".python-installer-state.json",
                payload={
                    "product": product_name,
                    "version": version,
                    "autocad_root": str(self.layout.autocad_root),
                    "managed_registry_roots": [HKCU_AUTOCAD, HKLM_AUTOCAD],
                    "managed_junctions": [str(local_product / "chs"), str(roaming_product / "chs")],
                },
            )
        )
        return InstallPlan(
            operations=tuple(operations),
            warnings=tuple(warnings),
            metadata={
                "product": product_name,
                "version": version,
                "legacy_acad_location": acad_location,
                "legacy_path_prefixes": [old for old, _new in rebaser.mappings],
                "autocad_root": str(self.layout.autocad_root),
                "desktop_shortcut": config.enabled("桌面快捷方式", default=True),
                "desktop": str(self.folders.desktop),
            },
        )

    def _reg3_core_ops(
        self,
        document: RegistryDocument,
        rebaser: PathRebaser,
        warnings: list[str],
    ) -> list[Operation]:
        ops: list[Operation] = []
        prefixes = tuple(prefix.casefold() for prefix in AUTOCAD_REG3_CORE_PREFIXES)
        for section in document.sections:
            if section.deleted or not section.key.casefold().startswith(prefixes):
                continue
            ops.append(EnsureRegistryKey(section.key))
            for value in section.values:
                if value.kind == "delete":
                    continue
                data = value.data
                if value.kind in {"sz", "expand_sz"}:
                    data = rebaser.apply(str(value.data))
                    if self._contains_historical_package_path(str(data), rebaser):
                        warnings.append(
                            f"Unresolved legacy COM path: {section.key} [{value.name}] -> {data}"
                        )
                ops.append(SetRegistryValue(section.key, value.name, value.kind, data))
        return ops

    def _registry_ops(
        self,
        document: RegistryDocument,
        allowed_root: str,
        rebaser: PathRebaser,
        warnings: list[str],
        source: str,
    ) -> list[Operation]:
        ops: list[Operation] = []
        allowed_cf = allowed_root.casefold()
        for section in document.sections:
            if section.deleted or not section.key.casefold().startswith(allowed_cf):
                continue
            if self._excluded_core_registry_section(section.key, source):
                continue
            ops.append(EnsureRegistryKey(section.key))
            for value in section.values:
                if value.kind == "delete":
                    continue
                if self._excluded_core_registry_value(section.key, value.name, source):
                    continue
                data = value.data
                if value.kind in {"sz", "expand_sz"}:
                    data = rebaser.apply(str(value.data))
                    if self._contains_historical_package_path(str(data), rebaser):
                        warnings.append(f"Unresolved legacy path: {section.key} [{value.name}] -> {data}")
                ops.append(SetRegistryValue(section.key, value.name, value.kind, data))
        return ops

    def _path_mappings(
        self,
        reg1: RegistryDocument,
        reg2: RegistryDocument,
        acad_location: str | None,
    ) -> list[tuple[str, str]]:
        mappings: list[tuple[str, str]] = []
        if acad_location:
            mappings.append((acad_location, str(self.layout.autocad_root)))

        old_shared = reg1.first_string("AutodeskSharedFolder")
        current_shared = self.layout.autocad_root / "Autodesk Shared"
        if old_shared and current_shared.exists():
            mappings.append((old_shared, str(current_shared)))

        for old_root in self._discover_legacy_autocad_roots(reg1, reg2):
            mappings.append((old_root, str(self.layout.autocad_root)))

        user_candidates = Counter()
        for document in (reg1, reg2):
            for section in document.sections:
                for value in section.values:
                    if value.kind not in {"sz", "expand_sz"}:
                        continue
                    for match in HISTORICAL_USER_RE.findall(str(value.data)):
                        user_candidates[match] += 1
        for old_user, _count in user_candidates.most_common():
            if old_user.casefold() == r"C:\Users\Public".casefold():
                continue
            mappings.append((old_user, str(self.folders.user_profile)))

        mappings.extend(
            [
                (r"C:\Windows", str(self.folders.windows)),
                (r"C:\ProgramData", str(self.folders.program_data)),
                (r"C:\Users\Public", str(self.folders.public)),
            ]
        )
        return mappings

    def _discover_legacy_autocad_roots(
        self,
        reg1: RegistryDocument,
        reg2: RegistryDocument,
    ) -> list[str]:
        roots: set[str] = set()
        current_cf = str(self.layout.autocad_root).casefold().rstrip("\\/")
        for document in (reg1, reg2):
            for section in document.sections:
                for value in section.values:
                    if value.kind not in {"sz", "expand_sz"}:
                        continue
                    for segment in str(value.data).split(";"):
                        candidate_text = segment.strip().strip('"')
                        lowered = candidate_text.casefold()
                        if not re.match(r"(?i)^[a-z]:\\", candidate_text):
                            continue
                        start = 0
                        while True:
                            pos = lowered.find(AUTOCAD_MARKER, start)
                            if pos < 0:
                                break
                            end = pos + len(AUTOCAD_MARKER)
                            candidate_root = candidate_text[:end].rstrip("\\/")
                            remainder = candidate_text[end:].lstrip("\\/")
                            if candidate_root.casefold() != current_cf:
                                if not remainder or (self.layout.autocad_root / Path(remainder)).exists():
                                    roots.add(candidate_root)
                            start = end
        return sorted(roots, key=len, reverse=True)

    @staticmethod
    def _version_from_keys(reg2: RegistryDocument) -> str | None:
        match_re = re.compile(r"\\AutoCAD\\(?P<version>R\d+\.\d+)(?:\\|$)", re.IGNORECASE)
        for section in reg2.sections:
            match = match_re.search(section.key)
            if match:
                return match.group("version")
        return None

    @staticmethod
    def _contains_historical_package_path(value: str, rebaser: PathRebaser) -> bool:
        return rebaser.contains_legacy_prefix(value)

    @staticmethod
    def _excluded_core_registry_section(key: str, source: str) -> bool:
        lowered = key.casefold()
        if source == "reg1":
            if "\\applications" in lowered:
                return True
            if "\\assemblymap" in lowered or "\\loaded\\" in lowered:
                return True
            if "\\infocenter" in lowered:
                return True
        if source == "reg2" and "\\applications\\acadvba" in lowered:
            return True
        return False

    @staticmethod
    def _excluded_core_registry_value(key: str, name: str, source: str) -> bool:
        if source != "reg1":
            return False
        lowered_key = key.casefold()
        lowered_name = name.casefold()
        if lowered_name in {"lastruntime", "automigrate"}:
            return True
        if "\\minidump" in lowered_key and lowered_name == "sessionstartcount":
            return True
        return False

    def _wizard_shortcuts(self) -> list[Operation]:
        return [
            CreateShortcut(
                path=self.layout.chs / "Plotters" / "添加绘图仪向导.lnk",
                target=self.layout.autocad_root / "addplwiz.exe",
                arguments="/language zh-cn",
                working_directory=self.layout.autocad_root,
            ),
            CreateShortcut(
                path=self.layout.chs / "Plotters" / "Plot Styles" / "添加打印样式表向导.lnk",
                target=self.layout.autocad_root / "styshwiz.exe",
                working_directory=self.layout.autocad_root,
            ),
        ]


def _desktop_folder(user_profile: Path, *, windows: bool | None = None) -> Path:
    """Resolve the actual Windows desktop, honoring User Shell Folders redirects."""
    is_windows = os.name == "nt" if windows is None else windows
    if is_windows:
        try:
            import winreg

            for subkey in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            ):
                try:
                    handle = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ)
                except FileNotFoundError:
                    continue
                try:
                    value, _kind = winreg.QueryValueEx(handle, "Desktop")
                except FileNotFoundError:
                    continue
                finally:
                    winreg.CloseKey(handle)
                resolved = os.path.expandvars(str(value)).strip()
                if resolved:
                    return Path(resolved)
        except (ImportError, OSError):
            pass
    return user_profile / "Desktop"

