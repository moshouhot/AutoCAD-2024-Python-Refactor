from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .model import PackageLayout
from .ops import (
    CreateShortcut,
    EnsureDirectory,
    EnsureJunction,
    EnsureRegistryKey,
    InstallArchiveFile,
    SetRegistryValue,
    WriteInstallState,
)
from .planner import (
    AUTOCAD_APPLICATION_COM_PREFIXES,
    AUTOCAD_REG3_CORE_PREFIXES,
    HKCU_AUTOCAD,
    HKLM_AUTOCAD,
    InstallPlan,
    VBA_RUNTIME_REGISTRY_PREFIXES,
    registry_key_is_same_or_descendant,
)


@dataclass(frozen=True)
class PlanFinding:
    code: str
    message: str


def validate_core_plan(plan: InstallPlan, layout: PackageLayout) -> tuple[PlanFinding, ...]:
    findings: list[PlanFinding] = []
    vba_enabled = bool(plan.metadata.get("vba_enabled", False))
    planned_files = {
        operation.destination.resolve(strict=False)
        for operation in plan.operations
        if isinstance(operation, InstallArchiveFile)
    }
    allowed_roots = (
        HKCU_AUTOCAD.casefold(),
        HKLM_AUTOCAD.casefold(),
        *(prefix.casefold() for prefix in AUTOCAD_REG3_CORE_PREFIXES),
        *(
            (prefix.casefold() for prefix in VBA_RUNTIME_REGISTRY_PREFIXES)
            if vba_enabled
            else ()
        ),
    )
    supported_registry_kinds = {"sz", "expand_sz", "dword"}

    for warning in plan.warnings:
        findings.append(PlanFinding("PLAN_WARNING", warning))

    for operation in plan.operations:
        if isinstance(operation, (EnsureRegistryKey, SetRegistryValue)):
            key_cf = operation.key.casefold()
            if not any(
                registry_key_is_same_or_descendant(operation.key, root)
                for root in allowed_roots
            ):
                findings.append(PlanFinding("REGISTRY_ROOT", operation.key))
            if "\\applications\\acadvba" in key_cf and not vba_enabled:
                findings.append(PlanFinding("VBA_IN_CORE", operation.key))
            if registry_key_is_same_or_descendant(operation.key, HKCU_AUTOCAD) and "\\applications" in key_cf:
                findings.append(PlanFinding("USER_PLUGIN_IN_CORE", operation.key))
            if vba_enabled and any(
                registry_key_is_same_or_descendant(operation.key, prefix)
                for prefix in VBA_RUNTIME_REGISTRY_PREFIXES
            ):
                text = operation.key
                if isinstance(operation, SetRegistryValue):
                    text += f" {operation.name} {operation.data}"
                lowered = text.casefold()
                if "\\installer\\" in lowered or "\\classes\\installer\\" in lowered:
                    findings.append(PlanFinding("VBA_INSTALLER_METADATA", operation.key))
                if "fm20" in lowered or "microsoft forms" in lowered or "\\forms." in lowered:
                    findings.append(PlanFinding("VBA_FORMS_IN_BASE", operation.key))

        if isinstance(operation, SetRegistryValue):
            if operation.kind not in supported_registry_kinds:
                findings.append(
                    PlanFinding(
                        "REGISTRY_TYPE",
                        f"{operation.key} [{operation.name}] type={operation.kind}",
                    )
                )
            if isinstance(operation.data, str):
                for old in plan.metadata.get("legacy_path_prefixes", []):
                    pattern = re.escape(str(old).rstrip("\\/")) + r"(?=[\\/;]|$)"
                    if re.search(pattern, operation.data, flags=re.IGNORECASE):
                        findings.append(
                            PlanFinding(
                                "LEGACY_PATH",
                                f"{operation.key} [{operation.name}] -> {operation.data}",
                            )
                        )
                        break
                if operation.name.casefold() == "loader" and "\\applications\\" in operation.key.casefold():
                    _check_loader(findings, operation.data, layout, planned_files)

        if isinstance(operation, EnsureJunction):
            if operation.target != layout.chs:
                findings.append(PlanFinding("JUNCTION_TARGET", f"{operation.path} -> {operation.target}"))
            _check_no_system_target(findings, operation.path, "JUNCTION_PATH")
            _check_no_system_target(findings, operation.target, "JUNCTION_TARGET_SYSTEM")

        if isinstance(operation, EnsureDirectory):
            _check_no_system_target(findings, operation.path, "DIRECTORY_SYSTEM")

        if isinstance(operation, CreateShortcut):
            _check_no_system_target(findings, operation.path, "SHORTCUT_SYSTEM")
            _check_no_system_target(findings, operation.target, "SHORTCUT_TARGET_SYSTEM")
            if operation.path.parent.exists() and not operation.path.parent.is_dir():
                findings.append(
                    PlanFinding("SHORTCUT_PARENT_NOT_DIRECTORY", str(operation.path.parent))
                )
            if not operation.target.exists():
                findings.append(PlanFinding("SHORTCUT_TARGET_MISSING", str(operation.target)))

        if isinstance(operation, InstallArchiveFile):
            if not vba_enabled:
                findings.append(PlanFinding("VBA_FILE_WITHOUT_FEATURE", str(operation.destination)))
            if operation.archive != layout.vba_archive:
                findings.append(PlanFinding("VBA_ARCHIVE", str(operation.archive)))
            _check_no_system_target(findings, operation.destination, "VBA_FILE_SYSTEM")
            lowered = str(operation.destination).replace("/", "\\").casefold()
            if "\\program files\\" not in lowered and "\\program files (x86)\\" not in lowered:
                findings.append(PlanFinding("VBA_FILE_ROOT", str(operation.destination)))
            member_cf = operation.member.replace("\\", "/").casefold()
            if member_cf.startswith("windows/") or "/fm20" in member_cf:
                findings.append(PlanFinding("VBA_FORMS_IN_BASE", operation.member))

        if isinstance(operation, WriteInstallState):
            if operation.path.parent != layout.acaoe:
                findings.append(PlanFinding("STATE_LOCATION", str(operation.path)))

    return tuple(findings)


def _check_no_system_target(findings: list[PlanFinding], path: Path, code: str) -> None:
    lowered = str(path).replace("/", "\\").casefold()
    if "\\windows\\system32" in lowered or "\\windows\\syswow64" in lowered:
        findings.append(PlanFinding(code, str(path)))


def _check_loader(
    findings: list[PlanFinding],
    loader: str,
    layout: PackageLayout,
    planned_files: set[Path] | None = None,
) -> None:
    if "://" in loader:
        return
    candidate = Path(loader)
    if not candidate.is_absolute():
        candidate = layout.autocad_root / loader
    if candidate.exists():
        return
    if planned_files and candidate.resolve(strict=False) in planned_files:
        return
    findings.append(PlanFinding("LOADER_MISSING", str(candidate)))

