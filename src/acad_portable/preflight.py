from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass

from .model import PackageLayout
from .textio import read_legacy_text


MIN_DOTNET_47_RELEASE = 460798


@dataclass(frozen=True)
class PreflightReport:
    windows: bool
    admin: bool | None
    dotnet_release: int | None
    dotnet_47_or_newer: bool | None
    autoload_ready: bool
    autoload_findings: tuple[str, ...]


def inspect_preflight(layout: PackageLayout) -> PreflightReport:
    windows = os.name == "nt"
    admin = _is_admin() if windows else None
    dotnet_release = _dotnet_release() if windows else None
    autoload_findings = inspect_autoload_chain(layout)
    return PreflightReport(
        windows=windows,
        admin=admin,
        dotnet_release=dotnet_release,
        dotnet_47_or_newer=(dotnet_release >= MIN_DOTNET_47_RELEASE) if dotnet_release is not None else None,
        autoload_ready=not autoload_findings,
        autoload_findings=autoload_findings,
    )


def inspect_autoload_chain(layout: PackageLayout) -> tuple[str, ...]:
    findings: list[str] = []
    acad_text, _ = read_legacy_text(layout.support_lsp)
    appload_text, _ = read_legacy_text(layout.appload_lsp)
    acad_lower = acad_text.casefold()
    appload_lower = appload_text.casefold()

    if '(load "appload.lsp")' not in acad_lower and "(load 'appload.lsp')" not in acad_lower:
        findings.append("acad2024.lsp does not load appload.lsp")
    if "0加载应用程序" not in appload_text:
        findings.append("appload.lsp does not reference 0加载应用程序")
    for extension in ("*.arx", "*.lsp", "*.fas", "*.vlx"):
        if extension not in appload_lower:
            findings.append(f"appload.lsp does not handle {extension}")
    return tuple(findings)


def _is_admin() -> bool | None:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return None


def _dotnet_release() -> int | None:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
        )
        try:
            value, _kind = winreg.QueryValueEx(key, "Release")
            return int(value)
        finally:
            winreg.CloseKey(key)
    except (ImportError, OSError, TypeError, ValueError):
        return None
