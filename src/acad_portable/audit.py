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
    SetRegistryValue,
    WriteInstallState,
)
from .planner import HKCU_AUTOCAD, HKLM_AUTOCAD, InstallPlan


@dataclass(frozen=True)
class PlanFinding:
    code: str
    message: str


def validate_core_plan(plan: InstallPlan, layout: PackageLayout) -> tuple[PlanFinding, ...]:
    findings: list[PlanFinding] = []
    allowed_roots = (HKCU_AUTOCAD.casefold(), HKLM_AUTOCAD.casefold())
    supported_registry_kinds = {"sz", "expand_sz", "dword"}

    for warning in plan.warnings:
        findings.append(PlanFinding("PLAN_WARNING", warning))

    for operation in plan.operations:
        if isinstance(operation, (EnsureRegistryKey, SetRegistryValue)):
            key_cf = operation.key.casefold()
            if not key_cf.startswith(allowed_roots):
                findings.append(PlanFinding("REGISTRY_ROOT", operation.key))
            if "\\applications\\acadvba" in key_cf:
                findings.append(PlanFinding("VBA_IN_CORE", operation.key))
            if key_cf.startswith(HKCU_AUTOCAD.casefold()) and "\\applications" in key_cf:
                findings.append(PlanFinding("USER_PLUGIN_IN_CORE", operation.key))

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
                    _check_loader(findings, operation.data, layout)

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
            if not operation.target.exists():
                findings.append(PlanFinding("SHORTCUT_TARGET_MISSING", str(operation.target)))

        if isinstance(operation, WriteInstallState):
            if operation.path.parent != layout.acaoe:
                findings.append(PlanFinding("STATE_LOCATION", str(operation.path)))

    return tuple(findings)


def _check_no_system_target(findings: list[PlanFinding], path: Path, code: str) -> None:
    lowered = str(path).replace("/", "\\").casefold()
    if "\\windows\\system32" in lowered or "\\windows\\syswow64" in lowered:
        findings.append(PlanFinding(code, str(path)))


def _check_loader(findings: list[PlanFinding], loader: str, layout: PackageLayout) -> None:
    if "://" in loader:
        return
    candidate = Path(loader)
    if not candidate.is_absolute():
        candidate = layout.autocad_root / loader
    if not candidate.exists():
        findings.append(PlanFinding("LOADER_MISSING", str(candidate)))

