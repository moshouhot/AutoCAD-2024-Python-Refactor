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
    InstallArchiveFile,
    Operation,
    SetRegistryValue,
    WriteInstallState,
)

VBA_ARCHIVE_PASSWORD = "zzz"
VBA_BASE_FILE_MEMBERS = (
    "Program Files (x86)/Common Files/Microsoft Shared/VBA/VBA6/VBE6EXT.OLB",
    "Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/Contents/AcVba.arx",
    "Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/PackageContents.xml",
    "Program Files/Autodesk/ApplicationPlugins/AcVBA2024.Bundle/vbaext.ico",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/1033/APC71ITL.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/1033/VBE7INTL.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/1033/VBEUIINTL.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/2052/APC71ITL.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/2052/VBE7INTL.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/2052/VBEUIINTL.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/apc71.dll",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/VBE7.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/VBEUI.DLL",
    "Program Files/Common Files/microsoft shared/VBA/VBA7.1/VBEUIRES.DLL",
)

from .registry import PathRebaser, RegistryDocument


def registry_key_is_same_or_descendant(key: str, prefix: str) -> bool:
    key_cf = key.rstrip("\\").casefold()
    prefix_cf = prefix.rstrip("\\").casefold()
    return key_cf == prefix_cf or key_cf.startswith(prefix_cf + "\\")


HKCU_AUTOCAD = r"HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD"
HKLM_AUTOCAD = r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD"
HKCU_CLASSES = r"HKEY_CURRENT_USER\SOFTWARE\Classes"
HKLM_CLASSES = r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes"
HKLM_INSTALLER_CLASSES = rf"{HKLM_CLASSES}\Installer"
HKLM_INSTALLER_USERDATA_SYSTEM = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer"
    r"\UserData\S-1-5-18"
)
HISTORICAL_USER_RE = re.compile(r"(?i)[A-Z]:\\Users\\[^\\\";]+")
AUTOCAD_MARKER = "\\autocad 2024"
SUPPORTED_AUTOCAD_REGISTRY_VERSION = "R24.3"

# These are not a copy of the captured MSI database.  They are the smallest
# identities proven by live traces plus exhaustive Feature-state subset A/B.
VBA_ENABLER_PACKED_PRODUCT = "FEE98B82551790401000FCF3A3907BD7"
VBA_ENABLER_ACVBA_PACKED_COMPONENT = "1D675EEA61AA0264284CC69034C784FF"
VBA71_PACKED_PRODUCT = "593A1E8712DFA994192A1653AB16216B"
VBA71_FEATURE = "ProductFiles"
VBA71_APC71_PACKED_COMPONENT = "029E703DA86A1D115B5B0006799C897E"
VBA71_FORMS_TYPELIB_PACKED_COMPONENT = "2A8F3F35080EE3E48A4E69A1726B20C9"
VBA71_VBE7_PACKED_COMPONENT = "374F999555861D6408391B4C361BEDB9"
VBA71_VBE6EXT_PACKED_COMPONENT = "57634D5732AA1D11A9CC0006794C4E25"
VBA71_VBEUIRES_PACKED_COMPONENT = "5CBA7A12F82110647A86699DF16FDE01"
VBA71_VBEUI_PACKED_COMPONENT = "A022E749FB2D09D489BC901493B9A972"
VBA71_FM20_PACKED_COMPONENT = "5E942FC614A302346AC6FAA0E9854C6F"
VBA71_VBE_TYPELIB_PACKED_COMPONENT = "EB0C8A90D0D34D14FAB6CF05A69BBEF1"
VBA71_OFFICE_TYPELIB_PACKED_COMPONENT = "FFC7844B38D726447AE1F693823C83FA"
VBA71_REQUIRED_COMPONENTS = frozenset(
    {
        VBA71_APC71_PACKED_COMPONENT,
        VBA71_FORMS_TYPELIB_PACKED_COMPONENT,
        VBA71_VBE7_PACKED_COMPONENT,
        VBA71_VBE6EXT_PACKED_COMPONENT,
        VBA71_VBEUIRES_PACKED_COMPONENT,
        VBA71_VBEUI_PACKED_COMPONENT,
        VBA71_FM20_PACKED_COMPONENT,
        VBA71_VBE_TYPELIB_PACKED_COMPONENT,
        VBA71_OFFICE_TYPELIB_PACKED_COMPONENT,
    }
)
VBA71_2052_PACKED_PRODUCT = "F08F9BBC40537524BA93F75042643985"
VBA71_2052_FEATURE = "VBAIntl"
VBA71_2052_APC71ITL_PACKED_COMPONENT = "0643BD6279CD7B24B99AA4C82D4EEDA9"
VBA71_2052_VBE7INTL_PACKED_COMPONENT = "0D2DA5BFE4DC9EE4283A1EA565AA603C"
VBA71_2052_VBEUIINTL_PACKED_COMPONENT = "F5514BB8B1BF6EC4BB1C3E2F13396476"
VBA71_2052_FM20CHS_PACKED_COMPONENT = "B11D3083768E5A54383A19141825E48E"
VBA71_2052_REQUIRED_COMPONENTS = frozenset(
    {
        VBA71_2052_APC71ITL_PACKED_COMPONENT,
        VBA71_2052_VBE7INTL_PACKED_COMPONENT,
        VBA71_2052_VBEUIINTL_PACKED_COMPONENT,
        VBA71_2052_FM20CHS_PACKED_COMPONENT,
    }
)
VBA71_QUALIFIED_CATEGORY_PACKED = "A60D248310600834EA5F102E00FE15AB"
VBA71_QUALIFIER_2052 = "2052"

VBA_MSI_COMPONENT_CLIENT_ROOT = rf"{HKLM_INSTALLER_USERDATA_SYSTEM}\Components"
VBA_MSI_CLIENT_VALUE_NAMES = frozenset(
    {VBA_ENABLER_PACKED_PRODUCT, VBA71_PACKED_PRODUCT, VBA71_2052_PACKED_PRODUCT}
)
VBA_MSI_ALLOWED_COMPONENT_CLIENTS = {
    VBA_ENABLER_ACVBA_PACKED_COMPONENT: VBA_ENABLER_PACKED_PRODUCT,
    **{component: VBA71_PACKED_PRODUCT for component in VBA71_REQUIRED_COMPONENTS},
    **{
        component: VBA71_2052_PACKED_PRODUCT
        for component in VBA71_2052_REQUIRED_COMPONENTS
    },
}
VBA_MSI_REGISTRY_PREFIXES = (
    rf"{HKLM_INSTALLER_CLASSES}\Products\{VBA_ENABLER_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_CLASSES}\Products\{VBA71_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_CLASSES}\Features\{VBA71_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_USERDATA_SYSTEM}\Products\{VBA71_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_CLASSES}\Products\{VBA71_2052_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_CLASSES}\Features\{VBA71_2052_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_USERDATA_SYSTEM}\Products\{VBA71_2052_PACKED_PRODUCT}",
    rf"{HKLM_INSTALLER_CLASSES}\Components\{VBA71_QUALIFIED_CATEGORY_PACKED}",
    VBA_MSI_COMPONENT_CLIENT_ROOT,
)

VBA_RUNTIME_REGISTRY_PREFIXES = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3\AutoCAD 2024 VBA Enabler",
    rf"{HKLM_CLASSES}\CLSID\{{2F967C44-B1F0-485E-957C-97538BCAD2DE}}",
    rf"{HKLM_CLASSES}\CLSID\{{943FA227-E90C-47DA-987B-C4DD13E48CB4}}",
    rf"{HKLM_CLASSES}\CLSID\{{95C9DCCD-A44A-4034-84BB-D7912DF5711F}}",
    rf"{HKLM_CLASSES}\CLSID\{{CFE9F29B-E1B6-4240-AED7-360846769314}}",
    rf"{HKLM_CLASSES}\TypeLib\{{000204EF-0000-0000-C000-000000000046}}",
    rf"{HKLM_CLASSES}\TypeLib\{{0002E157-0000-0000-C000-000000000046}}",
    rf"{HKLM_CLASSES}\TypeLib\{{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}}",
    rf"{HKLM_CLASSES}\TypeLib\{{A6128B1F-4A3A-40B6-B5CE-5FE8DE3D88E9}}",
    rf"{HKLM_CLASSES}\MSAPC.Apc",
    rf"{HKLM_CLASSES}\MSAPC.Apc.7.1",
    rf"{HKLM_CLASSES}\MSAPC.ApcCollection",
    rf"{HKLM_CLASSES}\MSAPC.ApcCollection.7.1",
    rf"{HKLM_CLASSES}\MSAPC.ApcGlobal",
    rf"{HKLM_CLASSES}\MSAPC.ApcGlobal.7.1",
    rf"{HKLM_CLASSES}\MSAPC.ApcHostAddIns",
    rf"{HKLM_CLASSES}\MSAPC.ApcHostAddIns.7.1",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\VBA",
)

AUTOCAD_APPLICATION_COM_PREFIXES = (
    rf"{HKCU_CLASSES}\AutoCAD.Application",
    rf"{HKCU_CLASSES}\AutoCAD.Application.24",
    rf"{HKLM_CLASSES}\AutoCAD.Application.24",
    rf"{HKLM_CLASSES}\AutoCAD.Application.24.1",
    rf"{HKLM_CLASSES}\AutoCAD.Application.24.2",
    rf"{HKLM_CLASSES}\AutoCAD.Application.24.3",
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
    # Live startup trace: acad.exe opens this AcadObject registration from
    # CheckCOMServerRelativePaths -> InstallUserData.  On a controlled clean
    # baseline, leaving only this CLSID absent reproduces "AutoCAD 错误中断";
    # adding exactly this subtree lets AutoCAD reach Drawing1.dwg.
    rf"{HKLM_CLASSES}\CLSID\{{E89B39BB-5AE4-4C52-9011-B70FC663F249}}",
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
    program_files: Path = Path(r"C:\Program Files")
    program_files_x86: Path = Path(r"C:\Program Files (x86)")

    @classmethod
    def current(cls) -> "KnownFolders":
        user = Path(os.environ.get("USERPROFILE", str(Path.home())))
        appdata = Path(os.environ.get("APPDATA", str(user / "AppData" / "Roaming")))
        local = Path(os.environ.get("LOCALAPPDATA", str(user / "AppData" / "Local")))
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        public = Path(os.environ.get("PUBLIC", str(user.parent / "Public")))
        # A 32-bit Python process on 64-bit Windows sees ``ProgramFiles`` as
        # the x86 root; ``ProgramW6432`` is the native 64-bit root.  Prefer it
        # for ``program_files`` and never use it as the x86 root.
        program_files = Path(
            os.environ.get("ProgramW6432")
            or os.environ.get("ProgramFiles")
            or r"C:\Program Files"
        )
        program_files_x86 = Path(
            os.environ.get("ProgramFiles(x86)")
            or os.environ.get("ProgramFiles")
            or r"C:\Program Files (x86)"
        )
        desktop = _desktop_folder(user)
        return cls(user, appdata, local, desktop, windows, program_data, public, program_files, program_files_x86)


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

        versions = self._versions_from_keys(reg2)
        if not versions:
            raise PackageError("Cannot parse AutoCAD registry version from reg2.dli")
        if versions != {SUPPORTED_AUTOCAD_REGISTRY_VERSION}:
            found = ", ".join(sorted(versions))
            raise PackageError(
                "Unsupported AutoCAD registry version(s) in reg2.dli: "
                f"{found}; expected {SUPPORTED_AUTOCAD_REGISTRY_VERSION}"
            )
        version = SUPPORTED_AUTOCAD_REGISTRY_VERSION
        mappings = self._path_mappings(reg1, reg2, acad_location)
        rebaser = PathRebaser(mappings)

        operations: list[Operation] = []
        warnings: list[str] = []
        operations.extend(self._registry_ops(reg1, HKCU_AUTOCAD, rebaser, warnings, source="reg1"))
        operations.extend(self._registry_ops(reg2, HKLM_AUTOCAD, rebaser, warnings, source="reg2"))
        operations.extend(self._reg3_core_ops(reg3, rebaser, warnings))

        vba_enabled = config.enabled("安装 VBA编程", default=False)
        if vba_enabled:
            if not self.layout.vba_archive.is_file():
                raise PackageError(f"VBA archive not found: {self.layout.vba_archive}")
            if not self.layout.vba_registry.is_file():
                raise PackageError(f"VBA registry template not found: {self.layout.vba_registry}")
            vba_registry = RegistryDocument.load(self.layout.vba_registry)
            operations.extend(self._vba_file_ops())
            operations.extend(self._vba_acad_registry_ops(reg2, rebaser, warnings))
            operations.extend(self._vba_runtime_registry_ops(vba_registry, warnings))
            operations.extend(self._vba_msi_identity_ops(vba_registry))
            for shared_dependency in (
                self.folders.windows / "System32" / "FM20.DLL",
                self.folders.windows / "System32" / "FM20chs.DLL",
            ):
                if not shared_dependency.is_file():
                    warnings.append(
                        f"Required VBA shared dependency missing: {shared_dependency}"
                    )

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
                "vba_enabled": vba_enabled,
                # Explicit allowed file roots for the VBA payload.  The audit
                # validates destinations against these instead of hard-coding
                # the literal "Program Files" directory names, so relocated or
                # renamed program-files folders stay valid.
                "program_files": str(self.folders.program_files),
                "program_files_x86": str(self.folders.program_files_x86),
            },
        )

    def _vba_file_ops(self) -> list[Operation]:
        ops: list[Operation] = []
        for member in VBA_BASE_FILE_MEMBERS:
            if member.startswith("Program Files (x86)/"):
                relative = member.removeprefix("Program Files (x86)/")
                destination = self.folders.program_files_x86 / Path(relative)
            elif member.startswith("Program Files/"):
                relative = member.removeprefix("Program Files/")
                destination = self.folders.program_files / Path(relative)
            else:
                raise PackageError(f"unsupported VBA payload destination: {member}")
            ops.append(
                InstallArchiveFile(
                    archive=self.layout.vba_archive,
                    member=member,
                    destination=destination,
                    password=VBA_ARCHIVE_PASSWORD,
                    reuse_existing=(
                        member.startswith("Program Files/Common Files/")
                        or member.startswith("Program Files (x86)/Common Files/")
                    ),
                )
            )
        return ops

    def _vba_msi_identity_ops(self, document: RegistryDocument) -> list[Operation]:
        """Publish only the MSI identity proven necessary by VBA live traces.

        Deliberately excluded: SourceList, LocalPackage, InstallSource,
        Uninstall metadata, package codes, cached MSI state, and broad Forms
        registration/deployment.  The single FM20 component identity below is
        retained because trace8 observed VBE7 requesting it directly; the
        installer still does not copy or overwrite FM20.DLL in System32.
        """
        ops: list[Operation] = []

        # AutoCAD's VBA loader checks the VBA Enabler ProductCode through MSI.
        # Live A/B proved that the empty advertised product identity is enough.
        ops.append(
            EnsureRegistryKey(
                rf"{HKLM_INSTALLER_CLASSES}\Products\{VBA_ENABLER_PACKED_PRODUCT}"
            )
        )
        enabler_component_key = (
            rf"{VBA_MSI_COMPONENT_CLIENT_ROOT}\{VBA_ENABLER_ACVBA_PACKED_COMPONENT}"
        )
        enabler_loader = (
            self.folders.program_files
            / "Autodesk"
            / "ApplicationPlugins"
            / "AcVBA2024.Bundle"
            / "Contents"
            / "AcVba.arx"
        )
        ops.append(EnsureRegistryKey(enabler_component_key))
        ops.append(
            SetRegistryValue(
                enabler_component_key,
                VBA_ENABLER_PACKED_PRODUCT,
                "sz",
                str(enabler_loader),
                preserve_existing=True,
            )
        )

        ops.extend(
            self._vba_msi_product_identity_ops(
                document,
                packed_product=VBA71_PACKED_PRODUCT,
                feature=VBA71_FEATURE,
                required_components=VBA71_REQUIRED_COMPONENTS,
            )
        )
        ops.extend(
            self._vba_msi_product_identity_ops(
                document,
                packed_product=VBA71_2052_PACKED_PRODUCT,
                feature=VBA71_2052_FEATURE,
                required_components=VBA71_2052_REQUIRED_COMPONENTS,
            )
        )

        qualified_key = (
            rf"{HKLM_INSTALLER_CLASSES}\Components\{VBA71_QUALIFIED_CATEGORY_PACKED}"
        )
        qualified = self._required_registry_value(
            document,
            qualified_key,
            VBA71_QUALIFIER_2052,
            "multi_sz",
        )
        if not isinstance(qualified, list) or len(qualified) != 1:
            raise PackageError(
                "Unexpected VBA 2052 qualified-component descriptor: "
                f"{qualified!r}"
            )
        ops.append(EnsureRegistryKey(qualified_key))
        ops.append(
            SetRegistryValue(
                qualified_key,
                VBA71_QUALIFIER_2052,
                "multi_sz",
                list(qualified),
                preserve_existing=True,
            )
        )
        return ops

    def _vba_msi_product_identity_ops(
        self,
        document: RegistryDocument,
        *,
        packed_product: str,
        feature: str,
        required_components: frozenset[str],
    ) -> list[Operation]:
        classes_product = rf"{HKLM_INSTALLER_CLASSES}\Products\{packed_product}"
        classes_feature = rf"{HKLM_INSTALLER_CLASSES}\Features\{packed_product}"
        userdata_product = rf"{HKLM_INSTALLER_USERDATA_SYSTEM}\Products\{packed_product}"
        userdata_features = userdata_product + r"\Features"
        userdata_install_properties = userdata_product + r"\InstallProperties"
        userdata_usage = userdata_product + r"\Usage"

        feature_data = self._required_registry_value(
            document, userdata_features, feature, "sz"
        )
        usage_data = self._required_registry_value(
            document, userdata_usage, feature, "dword"
        )

        ops: list[Operation] = [
            EnsureRegistryKey(classes_product),
            EnsureRegistryKey(classes_feature),
            SetRegistryValue(
                classes_feature,
                feature,
                "sz",
                "",
                preserve_existing=True,
            ),
            EnsureRegistryKey(userdata_product),
            EnsureRegistryKey(userdata_features),
            SetRegistryValue(
                userdata_features,
                feature,
                "sz",
                feature_data,
                preserve_existing=True,
            ),
            EnsureRegistryKey(userdata_install_properties),
            SetRegistryValue(
                userdata_install_properties,
                "WindowsInstaller",
                "dword",
                1,
                preserve_existing=True,
            ),
            EnsureRegistryKey(userdata_usage),
            SetRegistryValue(
                userdata_usage,
                feature,
                "dword",
                usage_data,
                preserve_existing=True,
            ),
        ]

        component_rows: list[tuple[str, str]] = []
        prefix = VBA_MSI_COMPONENT_CLIENT_ROOT + "\\"
        for section in document.sections:
            if section.deleted or not section.key.casefold().startswith(prefix.casefold()):
                continue
            packed_component = section.key[len(prefix):]
            if not packed_component or "\\" in packed_component:
                continue
            if packed_component not in required_components:
                continue
            for value in section.values:
                if value.name != packed_product or value.kind != "sz":
                    continue
                component_rows.append(
                    (section.key, self._rebase_vba_path(str(value.data)))
                )

        found_components = {key.rsplit("\\", 1)[-1] for key, _data in component_rows}
        if found_components != set(required_components):
            raise PackageError(
                f"Missing VBA MSI components for {packed_product}: "
                f"found={sorted(found_components)!r} expected={sorted(required_components)!r}"
            )
        for key, data in sorted(component_rows, key=lambda row: row[0].casefold()):
            ops.append(EnsureRegistryKey(key))
            ops.append(
                SetRegistryValue(
                    key,
                    packed_product,
                    "sz",
                    data,
                    preserve_existing=True,
                )
            )
        return ops

    @staticmethod
    def _required_registry_value(
        document: RegistryDocument,
        key: str,
        name: str,
        kind: str,
    ) -> object:
        for section in document.sections:
            if section.deleted or section.key.casefold() != key.casefold():
                continue
            for value in section.values:
                if value.name == name and value.kind == kind:
                    return value.data
        raise PackageError(
            f"Required VBA registry value missing: {key} [{name}] type={kind}"
        )

    def _vba_runtime_registry_ops(
        self,
        document: RegistryDocument,
        warnings: list[str],
    ) -> list[Operation]:
        ops: list[Operation] = []
        for section in document.sections:
            if section.deleted or not any(
                registry_key_is_same_or_descendant(section.key, prefix)
                for prefix in VBA_RUNTIME_REGISTRY_PREFIXES
            ):
                continue
            ops.append(EnsureRegistryKey(section.key))
            for value in section.values:
                if value.kind == "delete":
                    continue
                if value.kind not in {"sz", "dword"}:
                    warnings.append(
                        f"Unsupported VBA registry value: {section.key} [{value.name}] type={value.kind}"
                    )
                    continue
                data = value.data
                if value.kind == "sz":
                    data = self._rebase_vba_path(str(value.data))
                ops.append(
                    SetRegistryValue(
                        section.key,
                        value.name,
                        value.kind,
                        data,
                        preserve_existing=True,
                    )
                )
        return ops

    def _rebase_vba_path(self, value: str) -> str:
        mappings = (
            (
                r"C:\PROGRA~1\COMMON~1\MICROS~1\VBA",
                str(self.folders.program_files / "Common Files" / "Microsoft Shared" / "VBA"),
            ),
            (
                r"C:\Program Files\Common Files\Microsoft Shared\VBA",
                str(self.folders.program_files / "Common Files" / "Microsoft Shared" / "VBA"),
            ),
            (
                r"C:\Program Files (x86)\Common Files\Microsoft Shared\VBA",
                str(self.folders.program_files_x86 / "Common Files" / "Microsoft Shared" / "VBA"),
            ),
            (
                r"C:\Windows",
                str(self.folders.windows),
            ),
        )
        return PathRebaser(list(mappings)).apply(value)

    def _vba_acad_registry_ops(
        self,
        document: RegistryDocument,
        rebaser: PathRebaser,
        warnings: list[str],
    ) -> list[Operation]:
        """Plan the AcadVBA application entry from the AutoCAD registry files.

        Every value is planned with ``preserve_existing=True``: an external
        value already present on the machine is never taken over on first
        install, while values we create stay installer-owned and can still be
        updated by a later upgrade (ownership is tracked in the journal, not
        by this flag).
        """
        ops: list[Operation] = []
        for section in document.sections:
            if section.deleted:
                continue
            key_cf = section.key.casefold()
            if not registry_key_is_same_or_descendant(section.key, HKLM_AUTOCAD):
                continue
            if "\\applications\\acadvba" not in key_cf:
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
                            f"Unresolved legacy VBA path: {section.key} [{value.name}] -> {data}"
                        )
                ops.append(
                    SetRegistryValue(
                        section.key,
                        value.name,
                        value.kind,
                        data,
                        preserve_existing=True,
                    )
                )
        return ops

    def _reg3_core_ops(
        self,
        document: RegistryDocument,
        rebaser: PathRebaser,
        warnings: list[str],
    ) -> list[Operation]:
        ops: list[Operation] = []
        for section in document.sections:
            if section.deleted or not any(
                registry_key_is_same_or_descendant(section.key, prefix)
                for prefix in AUTOCAD_REG3_CORE_PREFIXES
            ):
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
        for section in document.sections:
            if section.deleted or not registry_key_is_same_or_descendant(section.key, allowed_root):
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
                if section.deleted:
                    continue
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
                if section.deleted:
                    continue
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
    def _versions_from_keys(reg2: RegistryDocument) -> set[str]:
        match_re = re.compile(
            rf"^{re.escape(HKLM_AUTOCAD)}\\(?P<version>R\d+\.\d+)(?:\\|$)",
            re.IGNORECASE,
        )
        versions: set[str] = set()
        for section in reg2.sections:
            if section.deleted:
                continue
            match = match_re.match(section.key)
            if match:
                versions.add(match.group("version").upper())
        return versions

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

