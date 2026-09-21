from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import validate_core_plan
from .config import FeatureConfig
from .model import PackageError, PackageLayout
from .ops import operation_to_dict
from .planner import InstallPlanner
from .preflight import inspect_preflight
from .real_windows import RealWindowsAdapter, inspect_install_state, inspect_live_diff


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acad-portable")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project/package root")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="inspect package inputs without changing the system")
    status.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", help="build the Core MVP install plan without applying it")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--full", action="store_true", help="include every operation in JSON output")

    install = sub.add_parser("install", help="validate Core plan; apply only with --apply")
    install.add_argument("--apply", action="store_true", help="perform real Windows changes")

    uninstall = sub.add_parser("uninstall", help="restore state owned by the Python installer")
    uninstall.add_argument("--apply", action="store_true", help="perform real Windows changes")

    diff = sub.add_parser("diff", help="compare Core plan to current Windows state without writing")
    diff.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        layout = PackageLayout.discover(args.root)
    except PackageError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.command == "status":
        return _status(layout, args.json)
    if args.command == "plan":
        return _plan(layout, args.json, args.full)
    if args.command == "install":
        return _install(layout, args.apply)
    if args.command == "uninstall":
        return _uninstall(layout, args.apply)
    if args.command == "diff":
        return _diff(layout, args.json)
    return 2


def _status(layout: PackageLayout, as_json: bool) -> int:
    config = FeatureConfig.load(layout.config)
    preflight = inspect_preflight(layout)
    installer_state = inspect_install_state(layout.acaoe / ".python-installer-state.json")
    payload = {
        "project_root": str(layout.project_root),
        "autocad_root": str(layout.autocad_root),
        "acad_exe": str(layout.acad_exe),
        "acaoe": str(layout.acaoe),
        "chs": str(layout.chs),
        "config_encoding": config.encoding,
        "config": config.values,
        "autoload": {
            "acad2024_lsp": layout.support_lsp.exists(),
            "appload_lsp": layout.appload_lsp.exists(),
            "extensions_dir": layout.extensions_dir.exists(),
            "ready": preflight.autoload_ready,
            "findings": list(preflight.autoload_findings),
        },
        "preflight": {
            "windows": preflight.windows,
            "admin": preflight.admin,
            "dotnet_release": preflight.dotnet_release,
            "dotnet_47_or_newer": preflight.dotnet_47_or_newer,
        },
        "installer_state": installer_state,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"AutoCAD root : {layout.autocad_root}")
        print(f"ACAOE        : {layout.acaoe}")
        print(f"CHS          : {layout.chs}")
        print(f"Config       : {len(config.values)} entries ({config.encoding})")
        print(f"Auto-load    : {'ready' if preflight.autoload_ready else 'incomplete'}")
        print(f"Admin        : {preflight.admin}")
        print(f".NET release : {preflight.dotnet_release}")
        print(f"Installer    : {installer_state.get('status') or 'not-installed'}")
    return 0 if preflight.autoload_ready else 1


def _plan(layout: PackageLayout, as_json: bool, full: bool) -> int:
    plan = InstallPlanner(layout).build()
    findings = validate_core_plan(plan, layout)
    payload: dict[str, object] = {
        "metadata": plan.metadata,
        "summary": plan.summary(),
        "warnings": list(plan.warnings),
        "audit_findings": [
            {"code": finding.code, "message": finding.message} for finding in findings
        ],
        "operation_count": len(plan.operations),
    }
    if full:
        payload["operations"] = [operation_to_dict(op) for op in plan.operations]

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"Product      : {plan.metadata['product']} {plan.metadata['version']}")
        print(f"AutoCAD root : {plan.metadata['autocad_root']}")
        print(f"Operations   : {len(plan.operations)}")
        for name, count in sorted(plan.summary().items()):
            print(f"  {name}: {count}")
        print(f"Warnings     : {len(plan.warnings)}")
        for warning in plan.warnings[:20]:
            print(f"  - {warning}")
        print(f"Audit        : {len(findings)} findings")
        for finding in findings[:20]:
            print(f"  - {finding.code}: {finding.message}")
    return 0 if not plan.warnings and not findings else 1


def _install(layout: PackageLayout, apply: bool) -> int:
    plan = InstallPlanner(layout).build()
    findings = validate_core_plan(plan, layout)
    if plan.warnings or findings:
        print(f"REFUSED: plan has {len(plan.warnings)} warnings and {len(findings)} audit findings")
        return 2

    preflight = inspect_preflight(layout)
    if not preflight.windows or preflight.admin is not True or preflight.dotnet_47_or_newer is not True:
        print("REFUSED: Windows/admin/.NET preflight is not satisfied")
        return 2

    if not apply:
        print(f"DRY-RUN PASS: {len(plan.operations)} operations; no system changes made")
        print("Run again with --apply only after reviewing `plan` output.")
        return 0

    report = RealWindowsAdapter().apply_plan(plan)
    print(f"APPLIED: {report.operations} operations")
    print(f"STATE: {report.state_path}")
    return 0


def _uninstall(layout: PackageLayout, apply: bool) -> int:
    state_path = layout.acaoe / ".python-installer-state.json"
    if not state_path.is_file():
        print(f"No Python installer state found: {state_path}")
        return 1
    if not apply:
        print(f"DRY-RUN: uninstall state exists at {state_path}; no changes made")
        return 0
    report = RealWindowsAdapter().uninstall(state_path)
    print(
        "UNINSTALL: "
        f"registry restored={report.registry_restored}, removed={report.registry_removed}, "
        f"shortcuts restored={report.shortcuts_restored}, removed={report.shortcuts_removed}, "
        f"junctions removed={report.junctions_removed}, conflicts={len(report.conflicts)}"
    )
    for conflict in report.conflicts:
        print(f"  CONFLICT: {conflict}")
    return 0 if not report.conflicts else 1


def _diff(layout: PackageLayout, as_json: bool) -> int:
    plan = InstallPlanner(layout).build()
    findings = validate_core_plan(plan, layout)
    if plan.warnings or findings:
        print(f"REFUSED: plan has {len(plan.warnings)} warnings and {len(findings)} audit findings")
        return 2
    report = inspect_live_diff(plan)
    payload = {
        "registry": {
            "same": report.registry_same,
            "change": report.registry_change,
            "create": report.registry_create,
            "keys_create": report.registry_keys_create,
        },
        "junctions": {
            "same": report.junction_same,
            "create": report.junction_create,
            "conflict": report.junction_conflict,
        },
        "shortcuts": {
            "existing": report.shortcut_existing,
            "create": report.shortcut_create,
        },
        "details": list(report.details),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "Registry     : "
            f"same={report.registry_same} change={report.registry_change} "
            f"create={report.registry_create} keys_create={report.registry_keys_create}"
        )
        print(
            "Junctions    : "
            f"same={report.junction_same} create={report.junction_create} conflict={report.junction_conflict}"
        )
        print(f"Shortcuts    : existing={report.shortcut_existing} create={report.shortcut_create}")
        for detail in report.details[:20]:
            print(f"  - {detail}")
    return 0 if report.junction_conflict == 0 else 1

