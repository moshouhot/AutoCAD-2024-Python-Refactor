from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ops import (
    CreateShortcut,
    EnsureDirectory,
    EnsureJunction,
    EnsureRegistryKey,
    Operation,
    SetRegistryValue,
    WriteInstallState,
)
from .planner import InstallPlan


STATE_SCHEMA = 1


@dataclass(frozen=True)
class ApplyReport:
    operations: int
    state_path: Path


@dataclass(frozen=True)
class UninstallReport:
    registry_restored: int
    registry_removed: int
    shortcuts_restored: int
    shortcuts_removed: int
    junctions_removed: int
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class LiveDiffReport:
    registry_same: int
    registry_change: int
    registry_create: int
    registry_keys_create: int
    junction_same: int
    junction_create: int
    junction_conflict: int
    shortcut_existing: int
    shortcut_create: int
    details: tuple[str, ...]


def inspect_live_diff(
    plan: InstallPlan,
    *,
    allow_non_windows_for_tests: bool = False,
) -> LiveDiffReport:
    """Compare a Core plan to the current Windows state without modifying it."""
    if os.name != "nt" and not allow_non_windows_for_tests:
        raise RuntimeError("live diff requires Windows")

    registry_same = 0
    registry_change = 0
    registry_create = 0
    registry_keys_create = 0
    junction_same = 0
    junction_create = 0
    junction_conflict = 0
    shortcut_existing = 0
    shortcut_create = 0
    details: list[str] = []

    for operation in plan.operations:
        if isinstance(operation, EnsureRegistryKey):
            if not _registry_key_exists(operation.key):
                registry_keys_create += 1
            continue

        if isinstance(operation, SetRegistryValue):
            current = _query_registry_value(operation.key, operation.name)
            wanted = {
                "type": _registry_kind(operation.kind),
                "data": _encode_json_value(operation.data),
            }
            if current is None:
                registry_create += 1
            elif current == wanted:
                registry_same += 1
            else:
                registry_change += 1
                if len(details) < 100:
                    details.append(f"REG_CHANGE {operation.key} [{operation.name}]")
            continue

        if isinstance(operation, EnsureJunction):
            if not os.path.lexists(operation.path):
                junction_create += 1
            elif _same_path(operation.path, operation.target):
                junction_same += 1
            else:
                junction_conflict += 1
                if len(details) < 100:
                    details.append(f"JUNCTION_CONFLICT {operation.path} -> {operation.target}")
            continue

        if isinstance(operation, CreateShortcut):
            if operation.path.is_file():
                shortcut_existing += 1
            else:
                shortcut_create += 1

    return LiveDiffReport(
        registry_same=registry_same,
        registry_change=registry_change,
        registry_create=registry_create,
        registry_keys_create=registry_keys_create,
        junction_same=junction_same,
        junction_create=junction_create,
        junction_conflict=junction_conflict,
        shortcut_existing=shortcut_existing,
        shortcut_create=shortcut_create,
        details=tuple(details),
    )


class RealWindowsAdapter:
    def __init__(self, *, allow_non_windows_for_tests: bool = False) -> None:
        if os.name != "nt" and not allow_non_windows_for_tests:
            raise RuntimeError("RealWindowsAdapter requires Windows")

    def apply_plan(self, plan: InstallPlan) -> ApplyReport:
        state_op = next((op for op in plan.operations if isinstance(op, WriteInstallState)), None)
        if state_op is None:
            raise RuntimeError("install plan has no state-file operation")

        state_path = state_op.path
        state = _load_state(state_path) or _new_state()
        state["status"] = "applying"
        state["install_payload"] = state_op.payload
        _write_state(state_path, state)

        applied = 0
        try:
            for operation in plan.operations:
                if isinstance(operation, WriteInstallState):
                    continue
                self._apply(operation, state)
                applied += 1
            state["status"] = "complete"
            _write_state(state_path, state)
        except Exception:
            state["status"] = "failed"
            state["applied_operations"] = applied
            _write_state(state_path, state)
            raise
        return ApplyReport(operations=applied, state_path=state_path)

    def uninstall(self, state_path: Path) -> UninstallReport:
        state = _load_state(state_path)
        if state is None:
            raise RuntimeError(f"install state not found: {state_path}")

        conflicts: list[str] = []
        restored = 0
        removed = 0
        shortcut_restored = 0
        shortcut_removed = 0
        junction_removed = 0

        for identity, entry in reversed(list(state.get("registry_values", {}).items())):
            key, name = identity.split("\u0000", 1)
            current = _query_registry_value(key, name)
            installed = entry.get("installed")
            if not _registry_snapshot_equal(current, installed):
                conflicts.append(f"registry changed externally: {key} [{name}]")
                continue
            before = entry.get("before")
            if before is None:
                _delete_registry_value(key, name)
                removed += 1
            else:
                _set_registry_snapshot(key, name, before)
                restored += 1

        for path_text, entry in reversed(list(state.get("shortcuts", {}).items())):
            path = Path(path_text)
            installed_sha = entry.get("installed_sha256")
            if installed_sha is None:
                # The operation was journaled before creation started, but it
                # never reached a successful shortcut write. There is nothing
                # to undo and restoring/deleting here could damage unrelated
                # state.
                continue
            current_sha = _file_sha256(path) if path.is_file() else None
            if current_sha != installed_sha:
                conflicts.append(f"shortcut changed externally: {path}")
                continue
            before_b64 = entry.get("before_base64")
            if before_b64 is None:
                path.unlink(missing_ok=True)
                shortcut_removed += 1
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(before_b64))
                shortcut_restored += 1

        for path_text, target_text in reversed(list(state.get("created_junctions", {}).items())):
            path = Path(path_text)
            target = Path(target_text)
            if not os.path.lexists(path):
                continue
            if not _same_path(path, target):
                conflicts.append(f"junction changed externally: {path}")
                continue
            os.rmdir(path)
            junction_removed += 1

        for key in sorted(state.get("created_registry_keys", []), key=lambda item: item.count("\\"), reverse=True):
            _delete_registry_key_if_empty(key)

        report = UninstallReport(
            registry_restored=restored,
            registry_removed=removed,
            shortcuts_restored=shortcut_restored,
            shortcuts_removed=shortcut_removed,
            junctions_removed=junction_removed,
            conflicts=tuple(conflicts),
        )
        if conflicts:
            state["status"] = "uninstall_conflicts"
            state["uninstall_conflicts"] = conflicts
            _write_state(state_path, state)
        else:
            state_path.unlink(missing_ok=True)
        return report

    def _apply(self, operation: Operation, state: dict[str, Any]) -> None:
        if isinstance(operation, EnsureRegistryKey):
            if not _registry_key_exists(operation.key):
                created = state.setdefault("created_registry_keys", [])
                if operation.key not in created:
                    created.append(operation.key)
            _ensure_registry_key(operation.key)
            return

        if isinstance(operation, SetRegistryValue):
            identity = f"{operation.key}\u0000{operation.name}"
            values = state.setdefault("registry_values", {})
            if identity not in values:
                values[identity] = {"before": _query_registry_value(operation.key, operation.name)}
            _set_registry_value(operation)
            values[identity]["installed"] = _query_registry_value(operation.key, operation.name)
            return

        if isinstance(operation, EnsureDirectory):
            operation.path.mkdir(parents=True, exist_ok=True)
            return

        if isinstance(operation, EnsureJunction):
            if os.path.lexists(operation.path):
                if _same_path(operation.path, operation.target):
                    return
                raise RuntimeError(f"junction path already exists with another target: {operation.path}")
            operation.path.parent.mkdir(parents=True, exist_ok=True)
            _create_junction(operation.path, operation.target)
            state.setdefault("created_junctions", {})[str(operation.path)] = str(operation.target)
            return

        if isinstance(operation, CreateShortcut):
            shortcuts = state.setdefault("shortcuts", {})
            identity = str(operation.path)
            if identity not in shortcuts:
                shortcuts[identity] = {
                    "before_base64": (
                        base64.b64encode(operation.path.read_bytes()).decode("ascii")
                        if operation.path.is_file()
                        else None
                    )
                }
            _create_shortcut(operation)
            shortcuts[identity]["installed_sha256"] = _file_sha256(operation.path)
            return

        raise TypeError(f"unsupported operation: {type(operation).__name__}")


def _new_state() -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "status": "new",
        "created_registry_keys": [],
        "registry_values": {},
        "created_junctions": {},
        "shortcuts": {},
    }


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != STATE_SCHEMA:
        raise RuntimeError(f"unsupported state schema: {data.get('schema')}")
    return data


def inspect_install_state(path: Path) -> dict[str, Any]:
    """Return a compact, read-only status view for CLI/reporting."""
    if not path.is_file():
        return {"exists": False, "status": None}
    try:
        state = _load_state(path)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        return {
            "exists": True,
            "status": "invalid",
            "error": f"{type(exc).__name__}: {exc}",
        }
    assert state is not None
    return {
        "exists": True,
        "status": state.get("status"),
        "schema": state.get("schema"),
        "registry_value_count": len(state.get("registry_values", {})),
        "junction_count": len(state.get("created_junctions", {})),
        "shortcut_count": len(state.get("shortcuts", {})),
        "conflict_count": len(state.get("uninstall_conflicts", [])),
    }


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _split_registry_key(key: str):
    import winreg

    root_name, _, subkey = key.partition("\\")
    roots = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    }
    try:
        return roots[root_name.upper()], subkey
    except KeyError as exc:
        raise ValueError(f"unsupported registry root: {root_name}") from exc


def _registry_access(write: bool = False) -> int:
    import winreg

    base = winreg.KEY_WRITE if write else winreg.KEY_READ
    return base | winreg.KEY_WOW64_64KEY


def _registry_key_exists(key: str) -> bool:
    import winreg

    root, subkey = _split_registry_key(key)
    try:
        handle = winreg.OpenKey(root, subkey, 0, _registry_access(False))
    except FileNotFoundError:
        return False
    else:
        winreg.CloseKey(handle)
        return True


def _ensure_registry_key(key: str) -> None:
    import winreg

    root, subkey = _split_registry_key(key)
    handle = winreg.CreateKeyEx(root, subkey, 0, _registry_access(True))
    winreg.CloseKey(handle)


def _registry_kind(kind: str) -> int:
    import winreg

    mapping = {
        "sz": winreg.REG_SZ,
        "expand_sz": winreg.REG_EXPAND_SZ,
        "dword": winreg.REG_DWORD,
    }
    try:
        return mapping[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported registry value kind: {kind}") from exc


def _set_registry_value(operation: SetRegistryValue) -> None:
    import winreg

    root, subkey = _split_registry_key(operation.key)
    handle = winreg.CreateKeyEx(root, subkey, 0, _registry_access(True))
    try:
        winreg.SetValueEx(handle, operation.name, 0, _registry_kind(operation.kind), operation.data)
    finally:
        winreg.CloseKey(handle)


def _query_registry_value(key: str, name: str) -> dict[str, Any] | None:
    import winreg

    root, subkey = _split_registry_key(key)
    try:
        handle = winreg.OpenKey(root, subkey, 0, _registry_access(False))
    except FileNotFoundError:
        return None
    try:
        try:
            data, kind = winreg.QueryValueEx(handle, name)
        except FileNotFoundError:
            return None
        return {"type": int(kind), "data": _encode_json_value(data)}
    finally:
        winreg.CloseKey(handle)


def _set_registry_snapshot(key: str, name: str, snapshot: dict[str, Any]) -> None:
    import winreg

    root, subkey = _split_registry_key(key)
    handle = winreg.CreateKeyEx(root, subkey, 0, _registry_access(True))
    try:
        winreg.SetValueEx(handle, name, 0, int(snapshot["type"]), _decode_json_value(snapshot["data"]))
    finally:
        winreg.CloseKey(handle)


def _delete_registry_value(key: str, name: str) -> None:
    import winreg

    root, subkey = _split_registry_key(key)
    try:
        handle = winreg.OpenKey(root, subkey, 0, _registry_access(True))
    except FileNotFoundError:
        return
    try:
        try:
            winreg.DeleteValue(handle, name)
        except FileNotFoundError:
            pass
    finally:
        winreg.CloseKey(handle)


def _delete_registry_key_if_empty(key: str) -> None:
    import winreg

    root, subkey = _split_registry_key(key)
    try:
        handle = winreg.OpenKey(root, subkey, 0, _registry_access(False))
    except FileNotFoundError:
        return
    try:
        subkeys, values, _mtime = winreg.QueryInfoKey(handle)
    finally:
        winreg.CloseKey(handle)
    if subkeys or values:
        return
    try:
        if hasattr(winreg, "DeleteKeyEx"):
            winreg.DeleteKeyEx(root, subkey, winreg.KEY_WOW64_64KEY, 0)
        else:
            winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        pass


def _registry_snapshot_equal(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    return left == right


def _encode_json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, tuple):
        return {"__tuple__": [_encode_json_value(item) for item in value]}
    if isinstance(value, list):
        return [_encode_json_value(item) for item in value]
    return value


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, dict) and "__bytes__" in value:
        return base64.b64decode(value["__bytes__"])
    if isinstance(value, dict) and "__tuple__" in value:
        return tuple(_decode_json_value(item) for item in value["__tuple__"])
    if isinstance(value, list):
        return [_decode_json_value(item) for item in value]
    return value


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve(strict=False) == right.resolve(strict=False)


def _create_junction(path: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(path), str(target)],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mklink failed ({result.returncode}): {result.stdout} {result.stderr}".strip())


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_shortcut(operation: CreateShortcut) -> None:
    operation.path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "$ws = New-Object -ComObject WScript.Shell",
        f"$s = $ws.CreateShortcut({_ps_quote(str(operation.path))})",
        f"$s.TargetPath = {_ps_quote(str(operation.target))}",
        f"$s.Arguments = {_ps_quote(operation.arguments)}",
    ]
    if operation.working_directory is not None:
        lines.append(f"$s.WorkingDirectory = {_ps_quote(str(operation.working_directory))}")
    lines.append("$s.Save()")
    script = "\r\n".join(lines)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not operation.path.is_file():
        raise RuntimeError(
            f"shortcut creation failed ({result.returncode}): {result.stdout} {result.stderr}".strip()
        )


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
