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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acad-portable")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project/package root")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="inspect package inputs without changing the system")
    status.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", help="build the Core MVP install plan without applying it")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--full", action="store_true", help="include every operation in JSON output")
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
    return 2


def _status(layout: PackageLayout, as_json: bool) -> int:
    config = FeatureConfig.load(layout.config)
    preflight = inspect_preflight(layout)
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

