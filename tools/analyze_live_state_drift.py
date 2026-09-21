from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _load_current_registry_value(key_path: str, value_name: str):
    import winreg

    roots = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    }
    root_name, subkey = key_path.split("\\", 1)
    root = roots.get(root_name)
    if root is None:
        return None
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            data, reg_type = winreg.QueryValueEx(key, value_name)
            return {"type": reg_type, "data": data}
    except FileNotFoundError:
        return None


def main() -> int:
    state_path = Path("AutoCAD 2024/ACAOE/.python-installer-state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    values = state.get("registry_values", {})

    total = 0
    same = 0
    missing = 0
    changed = 0
    changed_roots = Counter()
    path_drift = Counter()
    examples: list[dict[str, object]] = []

    for compound, journal in values.items():
        key_path, value_name = compound.split("\0", 1)
        installed = journal.get("installed")
        current = _load_current_registry_value(key_path, value_name)
        total += 1
        if current == installed:
            same += 1
            continue
        if current is None:
            missing += 1
            continue

        changed += 1
        changed_roots[key_path.split("\\", 1)[0]] += 1
        old_data = installed.get("data") if isinstance(installed, dict) else None
        new_data = current.get("data") if isinstance(current, dict) else None
        if isinstance(old_data, str) and isinstance(new_data, str):
            old_upper = old_data.upper()
            new_upper = new_data.upper()
            if old_upper.startswith("F:\\") and new_upper.startswith("D:\\"):
                path_drift["F_TO_D"] += 1
            elif old_upper.startswith("F:\\"):
                path_drift["F_TO_OTHER"] += 1
            elif new_upper.startswith("D:\\"):
                path_drift["OTHER_TO_D"] += 1
            else:
                path_drift["OTHER_CHANGE"] += 1
        else:
            path_drift["NON_STRING_CHANGE"] += 1

        if len(examples) < 20:
            examples.append(
                {
                    "key": key_path,
                    "value": value_name,
                    "installed": old_data,
                    "current": new_data,
                }
            )

    result = {
        "state_path": str(state_path),
        "status": state.get("status"),
        "journal_values": total,
        "same": same,
        "changed": changed,
        "missing": missing,
        "changed_roots": dict(changed_roots),
        "path_drift": dict(path_drift),
        "examples": examples,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
