from __future__ import annotations

import base64
import contextlib
import copy
import ctypes
import hashlib
import json
import ntpath
import os
import stat
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
    InstallArchiveFile,
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
    files_removed: int
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class LiveDiffReport:
    registry_same: int
    registry_change: int
    registry_external_preserved: int
    registry_create: int
    registry_keys_create: int
    junction_same: int
    junction_create: int
    junction_conflict: int
    shortcut_existing: int
    shortcut_create: int
    file_same: int
    file_reuse: int
    file_create: int
    file_conflict: int
    details: tuple[str, ...]
    file_upgrade: int = 0
    registry_retire: int = 0
    file_retire: int = 0


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
    registry_external_preserved = 0
    registry_create = 0
    registry_keys_create = 0
    junction_same = 0
    junction_create = 0
    junction_conflict = 0
    shortcut_existing = 0
    shortcut_create = 0
    file_same = 0
    file_reuse = 0
    file_create = 0
    file_conflict = 0
    file_upgrade = 0
    registry_retire = 0
    file_retire = 0
    details: list[str] = []

    state_op = next((op for op in plan.operations if isinstance(op, WriteInstallState)), None)
    prior_state = _load_state(state_op.path) if state_op is not None else None
    prior_values = (prior_state or {}).get("registry_values", {})
    prior_files = (prior_state or {}).get("created_files", {})
    planned_registry_ids = {
        _registry_identity(operation.key, operation.name)
        for operation in plan.operations
        if isinstance(operation, SetRegistryValue)
    }
    planned_destinations = {
        _windows_path_key(operation.destination)
        for operation in plan.operations
        if isinstance(operation, InstallArchiveFile)
    }

    for operation in plan.operations:
        if isinstance(operation, EnsureRegistryKey):
            if not _registry_key_exists(operation.key):
                registry_keys_create += 1
            continue

        if isinstance(operation, SetRegistryValue):
            current = _query_registry_value(operation.key, operation.name)
            identity = _registry_identity(operation.key, operation.name)
            prior_entry = prior_values.get(identity)
            if prior_entry is not None:
                # Ownership is decided before the wanted-value fast path: a
                # journaled value that was released or changed externally is
                # reported as external even when the current bytes happen to
                # equal the new wanted value.  An entry that is still
                # installer-owned is judged by the wanted value, and
                # ``preserve_existing`` must never block our own upgrade.
                if prior_entry.get("released") or not _registry_snapshot_equal(
                    current, prior_entry.get("installed")
                ):
                    registry_external_preserved += 1
                    if len(details) < 100:
                        details.append(
                            f"REG_EXTERNAL_PRESERVED {operation.key} [{operation.name}]"
                        )
                elif current is not None and _registry_operation_matches_snapshot(
                    operation, current
                ):
                    registry_same += 1
                else:
                    registry_change += 1
                    if len(details) < 100:
                        details.append(f"REG_CHANGE {operation.key} [{operation.name}]")
            elif current is None:
                registry_create += 1
            elif _registry_operation_matches_snapshot(operation, current):
                registry_same += 1
            elif operation.preserve_existing:
                registry_external_preserved += 1
                if len(details) < 100:
                    details.append(
                        f"REG_EXTERNAL_PRESERVED {operation.key} [{operation.name}]"
                    )
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
            continue

        if isinstance(operation, InstallArchiveFile):
            payload = _read_archive_member(operation)
            wanted_sha = hashlib.sha256(payload).hexdigest()
            # Reparse/symlink destinations and parents are conflicts, checked
            # before any existence or hash classification.  A symlink to an
            # existing file would otherwise be misread as same/reuse/upgrade,
            # and a dangling one would be misread as a create.
            if _is_reparse_or_symlink(operation.destination) or _has_reparse_ancestor(
                operation.destination
            ):
                file_conflict += 1
                if len(details) < 100:
                    details.append(
                        f"FILE_CONFLICT {operation.destination} (reparse point)"
                    )
            elif not os.path.lexists(operation.destination):
                file_create += 1
            elif not operation.destination.is_file():
                file_conflict += 1
                if len(details) < 100:
                    details.append(f"FILE_CONFLICT {operation.destination} (not a regular file)")
            else:
                current_sha = _file_sha256(operation.destination)
                kind, _entry_key = _classify_existing_archive(
                    prior_files, operation, current_sha, wanted_sha
                )
                if kind == "same":
                    file_same += 1
                elif kind == "upgrade":
                    file_upgrade += 1
                    if len(details) < 100:
                        details.append(f"FILE_UPGRADE {operation.destination}")
                elif kind == "reuse":
                    file_reuse += 1
                    if len(details) < 100:
                        details.append(f"FILE_REUSE_EXISTING {operation.destination}")
                else:
                    file_conflict += 1
                    if len(details) < 100:
                        details.append(f"FILE_CONFLICT {operation.destination}")

    # Retirement reporting: the apply reconciliation passes retire prior
    # registry values and archive files that are absent from the new plan.
    # Those actions were previously invisible to a diff, so they are counted
    # here as dedicated aggregates instead of being folded into change/upgrade.
    # This pass is strictly read-only and mirrors the reconciliation branches
    # (reparse before hash, ownership before wanted value) without writing.
    for identity in prior_values:
        if identity in planned_registry_ids:
            continue
        registry_retire += 1
        key, name = identity.split("\u0000", 1)
        entry = prior_values[identity]
        current = _query_registry_value(key, name)
        installed = entry.get("installed")
        if entry.get("released") or not _registry_snapshot_equal(current, installed):
            detail = (
                f"REG_RETIRE_EXTERNAL {key} [{name}] "
                "(release ownership, preserve external value)"
            )
        elif entry.get("before") is None:
            detail = f"REG_RETIRE {key} [{name}] (will remove)"
        else:
            detail = f"REG_RETIRE {key} [{name}] (will restore previous value)"
        if len(details) < 100:
            details.append(detail)

    for path_text, entry in prior_files.items():
        path = Path(path_text)
        if _windows_path_key(path) in planned_destinations:
            continue
        file_retire += 1
        installed_sha = entry.get("installed_sha256")
        # Reparse checks stay ahead of existence/hashing, exactly as the
        # reconciliation pass does: never hash or claim a delete through a
        # link that could have been swapped in.
        if _is_reparse_or_symlink(path) or _has_reparse_ancestor(path):
            detail = f"FILE_RETIRE_RELEASED_REPARSE {path}"
        elif not os.path.lexists(path):
            detail = f"FILE_RETIRE_MISSING {path} (already absent)"
        elif not path.is_file() or _file_sha256(path) != installed_sha:
            detail = (
                f"FILE_RETIRE_RELEASED_EXTERNAL {path} "
                "(release ownership, preserve external file)"
            )
        else:
            detail = f"FILE_RETIRE {path} (will remove)"
        if len(details) < 100:
            details.append(detail)

    return LiveDiffReport(
        registry_same=registry_same,
        registry_change=registry_change,
        registry_external_preserved=registry_external_preserved,
        registry_create=registry_create,
        registry_keys_create=registry_keys_create,
        junction_same=junction_same,
        junction_create=junction_create,
        junction_conflict=junction_conflict,
        shortcut_existing=shortcut_existing,
        shortcut_create=shortcut_create,
        file_same=file_same,
        file_reuse=file_reuse,
        file_create=file_create,
        file_conflict=file_conflict,
        details=tuple(details),
        file_upgrade=file_upgrade,
        registry_retire=registry_retire,
        file_retire=file_retire,
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

        # Read-all-before-mutate: every archive member the plan requires is
        # extracted and validated up front, before the state file or any
        # registry/junction/shortcut/destination mutation happens.  A bad
        # password, a corrupt archive or a missing member therefore fails with
        # zero system changes instead of after a partial apply.  The bytes are
        # cached for this single apply only and reused by the matching
        # InstallArchiveFile operation, so no member is ever read twice.
        archive_payloads: dict[int, bytes] = {}
        for index, operation in enumerate(plan.operations):
            if isinstance(operation, InstallArchiveFile):
                archive_payloads[index] = _read_archive_member(operation)

        prior_state = _load_state(state_path)
        _preflight_archive_destinations(plan.operations, archive_payloads, prior_state)

        state = prior_state or _new_state()
        state["status"] = "applying"
        state["install_payload"] = state_op.payload
        _write_state(state_path, state)

        applied = 0
        # Apply-local rollback journal for destructive retirement of
        # installer-owned archive files.  Payload bytes are deliberately kept
        # here and never written into the persistent state file: the journal
        # only has to survive this one apply call.  ``ownership_snapshot``
        # captures the file-ownership maps immediately before retirement so a
        # later failure can put ownership back the way it was, instead of
        # leaving a restored file that the journal has already disowned.
        rollback_journal: list[tuple[Path, bytes]] = []
        ownership_snapshot: tuple[dict[str, Any], dict[str, Any]] | None = None
        try:
            for index, operation in enumerate(plan.operations):
                if isinstance(operation, WriteInstallState):
                    continue
                self._apply(operation, state, archive_payloads.get(index))
                applied += 1
            self._reconcile_retired_registry_ownership(plan, state)
            ownership_snapshot = (
                copy.deepcopy(state.setdefault("created_files", {})),
                copy.deepcopy(state.setdefault("retired_files", {})),
            )
            self._reconcile_retired_file_ownership(plan, state, rollback_journal)
            state["status"] = "complete"
            _write_state(state_path, state)
        except Exception as exc:
            # Undo only this round's destructive file retirements.  Ordinary
            # plan operations and registry reconciliation keep their existing
            # failure semantics; this is not a whole-install transaction and
            # makes no crash-transactional claim.
            rollback_failure = _rollback_retired_files(
                rollback_journal, ownership_snapshot, state
            )
            state["status"] = "failed"
            state["applied_operations"] = applied
            state_write_failure: Exception | None = None
            try:
                _write_state(state_path, state)
            except Exception as write_exc:  # pragma: no cover - defensive
                state_write_failure = write_exc
            if rollback_failure is not None or state_write_failure is not None:
                problems: list[str] = []
                if rollback_failure is not None:
                    problems.append(f"retired-file rollback failed: {rollback_failure}")
                if state_write_failure is not None:
                    problems.append(f"failed-state write failed: {state_write_failure}")
                raise RuntimeError("; ".join(problems)) from exc
            raise
        return ApplyReport(operations=applied, state_path=state_path)

    def _reconcile_retired_registry_ownership(
        self,
        plan: InstallPlan,
        state: dict[str, Any],
    ) -> None:
        """Release registry ownership that disappeared from an upgraded plan.

        Only values recorded in our journal are eligible.  If the current
        value still equals the snapshot installed by the previous plan, the
        original value is restored (or the value is deleted when it did not
        exist before).  If anything else has changed it, ownership is simply
        released and the external value is preserved.
        """
        planned_value_ids = {
            _registry_identity(operation.key, operation.name)
            for operation in plan.operations
            if isinstance(operation, SetRegistryValue)
        }
        planned_keys = {
            operation.key.rstrip("\\").casefold()
            for operation in plan.operations
            if isinstance(operation, (EnsureRegistryKey, SetRegistryValue))
        }

        values = state.setdefault("registry_values", {})
        retired = state.setdefault("retired_registry_values", {})
        for identity, entry in list(values.items()):
            if identity in planned_value_ids:
                continue
            key, name = identity.split("\u0000", 1)
            current = _query_registry_value(key, name)
            installed = entry.get("installed")

            if entry.get("released") or not _registry_snapshot_equal(current, installed):
                retired[identity] = {
                    "action": "released_external",
                    "snapshot": current,
                }
                del values[identity]
                continue

            before = entry.get("before")
            if before is None:
                _delete_registry_value(key, name)
                action = "removed"
            else:
                _set_registry_snapshot(key, name, before)
                action = "restored"
            retired[identity] = {
                "action": action,
                "before": before,
                "installed": installed,
            }
            del values[identity]

        created_keys = state.setdefault("created_registry_keys", [])
        for key in sorted(
            [
                item
                for item in created_keys
                if item.rstrip("\\").casefold() not in planned_keys
            ],
            key=lambda item: item.count("\\"),
            reverse=True,
        ):
            _delete_registry_key_if_empty(key)
            if not _registry_key_exists(key):
                created_keys.remove(key)

    def _reconcile_retired_file_ownership(
        self,
        plan: InstallPlan,
        state: dict[str, Any],
        rollback_journal: list[tuple[Path, bytes]],
    ) -> None:
        """Release installer-owned archive files that left the upgraded plan.

        Only files recorded in our journal are eligible.  A file that still
        matches the hash we installed is deleted and ownership is dropped; a
        file that is missing or was changed externally is left in place and
        ownership is released.  Retired entries are recorded under
        ``retired_files`` so a later uninstall never touches them again.

        Before a still-owned file is unlinked its full payload is read and
        appended to ``rollback_journal`` (newest last).  ``apply_plan`` uses
        that journal to restore the bytes and the ownership maps when any
        later step fails, so the destructive delete is reversible for the
        lifetime of this apply call.
        """
        planned_destinations = {
            _windows_path_key(operation.destination)
            for operation in plan.operations
            if isinstance(operation, InstallArchiveFile)
        }
        created = state.setdefault("created_files", {})
        retired = state.setdefault("retired_files", {})
        for path_text, entry in list(created.items()):
            path = Path(path_text)
            if _windows_path_key(path) in planned_destinations:
                continue
            installed_sha = entry.get("installed_sha256")
            # The helper performs the reparse check before opening, then binds
            # read/hash/delete to a single Windows file handle under the parent
            # directory lock.  A sharing/permission failure raises instead of
            # being classified, so apply fails loudly rather than silently
            # disowning a file that may still be ours.
            result = _delete_owned_file_by_handle(path, installed_sha)
            if result.outcome == "external":
                action = (
                    "released_reparse"
                    if result.reason == "reparse"
                    else "released_external"
                )
                retired[path_text] = {
                    "action": action,
                    "installed_sha256": installed_sha,
                }
                del created[path_text]
                continue
            if result.outcome == "missing":
                retired[path_text] = {"action": "missing"}
                del created[path_text]
                continue
            # The file was deleted through the locked handle; keep its exact
            # payload so a later failure can restore it and re-own it.
            assert result.payload is not None
            rollback_journal.append((path, result.payload))
            retired[path_text] = {
                "action": "removed",
                "installed_sha256": installed_sha,
            }
            del created[path_text]

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
        files_removed = 0

        for path_text, entry in reversed(list(state.get("created_files", {}).items())):
            path = Path(path_text)
            installed_sha = entry.get("installed_sha256")
            try:
                result = _delete_owned_file_by_handle(path, installed_sha)
            except OSError as exc:
                # Busy/permission/sharing failure: fail closed and keep
                # ownership so a later retry can finish the job.
                conflicts.append(f"installer-owned file could not be removed: {path}: {exc}")
                continue
            if result.outcome == "removed":
                files_removed += 1
            elif result.outcome == "missing":
                # Genuinely missing: nothing to undo.  Ownership is dropped so
                # a later uninstall does not keep retrying a nonexistent path.
                pass
            elif result.reason == "reparse":
                conflicts.append(f"file is or is below a reparse point: {path}")
                continue
            elif result.reason == "non-file":
                # An existing non-file object (directory, device, ...) has
                # replaced our installer-owned file.  Deleting it would
                # destroy external data, so it is a conflict and the state
                # journal is kept for a later, informed decision.
                conflicts.append(
                    "installer-owned file replaced by an external non-file: "
                    f"{path}"
                )
                continue
            else:
                conflicts.append(f"file changed externally: {path}")
                continue
            # Completed (removed or confirmed absent): drop the ownership
            # entry so a later uninstall does not re-process it.
            del state["created_files"][path_text]

        for identity, entry in reversed(list(state.get("registry_values", {}).items())):
            if entry.get("released"):
                del state["registry_values"][identity]
                continue
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
            del state["registry_values"][identity]

        for path_text, entry in reversed(list(state.get("shortcuts", {}).items())):
            path = Path(path_text)
            installed_sha = entry.get("installed_sha256")
            if installed_sha is None:
                # The operation was journaled before creation started, but it
                # never reached a successful shortcut write. There is nothing
                # to undo and restoring/deleting here could damage unrelated
                # state.
                del state["shortcuts"][path_text]
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
            del state["shortcuts"][path_text]

        for path_text, target_text in reversed(list(state.get("created_junctions", {}).items())):
            path = Path(path_text)
            target = Path(target_text)
            if not os.path.lexists(path):
                del state["created_junctions"][path_text]
                continue
            if not _same_path(path, target):
                conflicts.append(f"junction changed externally: {path}")
                continue
            os.rmdir(path)
            junction_removed += 1
            del state["created_junctions"][path_text]

        for key in sorted(state.get("created_registry_keys", []), key=lambda item: item.count("\\"), reverse=True):
            _delete_registry_key_if_empty(key)
            # Only prune an identity we can confirm is gone, so a stale
            # non-empty external key is never dropped from the journal.
            if not _registry_key_exists(key):
                state["created_registry_keys"].remove(key)

        report = UninstallReport(
            registry_restored=restored,
            registry_removed=removed,
            shortcuts_restored=shortcut_restored,
            shortcuts_removed=shortcut_removed,
            junctions_removed=junction_removed,
            files_removed=files_removed,
            conflicts=tuple(conflicts),
        )
        if conflicts:
            state["status"] = "uninstall_conflicts"
            state["uninstall_conflicts"] = conflicts
            _write_state(state_path, state)
        else:
            state_path.unlink(missing_ok=True)
        return report

    def _apply(
        self,
        operation: Operation,
        state: dict[str, Any],
        archive_payload: bytes | None = None,
    ) -> None:
        if isinstance(operation, EnsureRegistryKey):
            canonical_key = operation.key.rstrip("\\").casefold()
            if not _registry_key_exists(operation.key):
                created = state.setdefault("created_registry_keys", [])
                if canonical_key not in created:
                    created.append(canonical_key)
            _ensure_registry_key(operation.key)
            return

        if isinstance(operation, SetRegistryValue):
            identity = _registry_identity(operation.key, operation.name)
            values = state.setdefault("registry_values", {})
            current = _query_registry_value(operation.key, operation.name)
            entry = values.get(identity)
            if entry is not None:
                # Ownership is decided before the wanted-value fast path: a
                # journaled value that was changed externally is released even
                # when the external bytes happen to equal the new wanted value,
                # so uninstall can never treat them as installer-owned.  An
                # entry that is still installer-owned falls through and is
                # updated to the new wanted value.
                if entry.get("released"):
                    entry["released_snapshot"] = current
                    return
                if not _registry_snapshot_equal(current, entry.get("installed")):
                    entry["released"] = True
                    entry["released_snapshot"] = current
                    return
            else:
                # The wanted-value fast path only applies when there is no
                # journal entry: with no ownership to protect, a current value
                # that already matches is a no-op.
                if current is not None and _registry_operation_matches_snapshot(operation, current):
                    return
                if operation.preserve_existing and current is not None:
                    return
                entry = {"before": current}
                values[identity] = entry
                state.setdefault("retired_registry_values", {}).pop(identity, None)
            _set_registry_value(operation)
            entry["installed"] = _query_registry_value(operation.key, operation.name)
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

        if isinstance(operation, InstallArchiveFile):
            if archive_payload is None:
                raise RuntimeError(
                    "archive payload was not preflighted for this operation"
                )
            payload = archive_payload
            wanted_sha = hashlib.sha256(payload).hexdigest()
            created = state.setdefault("created_files", {})
            # lexists() is the single existence gate: it is True for dangling
            # symlinks and other reparse points whose target is missing, which
            # exists() reports as absent.  A present-but-not-regular-file
            # destination must never be written through, so the create/write
            # path below is reachable only when lexists reports the
            # destination absent.
            if os.path.lexists(operation.destination):
                _reject_reparse_path(operation.destination)
                if not operation.destination.is_file():
                    raise RuntimeError(
                        f"file destination exists but is not a file: {operation.destination}"
                    )
                current_sha = _file_sha256(operation.destination)
                kind, entry_key = _classify_existing_archive(
                    created, operation, current_sha, wanted_sha
                )
                if kind == "same":
                    return
                if kind == "upgrade":
                    # Installer-owned and unchanged: a safe upgrade.  The
                    # previous ownership entry stays intact until the new bytes
                    # are atomically in place, so a failed write cannot lose it.
                    assert entry_key is not None
                    pending = dict(created[entry_key])
                    pending.update(
                        {
                            "installed_sha256": wanted_sha,
                            "archive": str(operation.archive),
                            "member": operation.member,
                        }
                    )
                    state.setdefault("pending_files", {})[entry_key] = pending
                    _atomic_upgrade_owned_bytes(
                        operation.destination,
                        payload,
                        created[entry_key].get("installed_sha256"),
                    )
                    created[entry_key] = pending
                    state.get("pending_files", {}).pop(entry_key, None)
                    return
                if kind == "reuse":
                    # Journaled but changed externally, or unowned: preserve the
                    # existing bytes.  If it was ours, release ownership rather
                    # than silently adopting the external file.
                    if entry_key is not None:
                        retired = state.setdefault("retired_files", {})
                        retired[entry_key] = {
                            "action": "released_external",
                            "installed_sha256": created[entry_key].get(
                                "installed_sha256"
                            ),
                        }
                        del created[entry_key]
                    return
                raise RuntimeError(
                    "refusing to overwrite existing shared file with different content: "
                    f"{operation.destination}"
                )
            _reject_reparse_path(operation.destination)
            operation.destination.parent.mkdir(parents=True, exist_ok=True)
            _reject_reparse_path(operation.destination)
            entry_key = str(operation.destination)
            canonical_key = _windows_path_key(entry_key)
            pending = {
                "installed_sha256": wanted_sha,
                "archive": str(operation.archive),
                "member": operation.member,
            }
            # Record intent in memory before the destination is exposed so the
            # apply_plan failure handler can persist a diagnosable journal.
            # Any canonical-equivalent stale intent is dropped first so a
            # later failure can never read a duplicate entry with an old hash.
            pending_files = state.setdefault("pending_files", {})
            for stale_key in [
                key
                for key in pending_files
                if key != entry_key and _windows_path_key(key) == canonical_key
            ]:
                del pending_files[stale_key]
            pending_files[entry_key] = pending
            _atomic_create_bytes(operation.destination, payload)
            # The new bytes are in place.  Collapse every canonical-equivalent
            # stale ownership key onto the path spelling actually written, so
            # the next same/upgrade/uninstall round cannot be misled by an old
            # installed hash.  Unrelated canonical paths are left untouched,
            # and prior ``created_files`` ownership is preserved until the
            # write succeeds, so a write failure keeps it intact.
            for stale_key in [
                key
                for key in created
                if key != entry_key and _windows_path_key(key) == canonical_key
            ]:
                del created[stale_key]
            created[entry_key] = pending
            pending_files.pop(entry_key, None)
            return

        raise TypeError(f"unsupported operation: {type(operation).__name__}")


def _new_state() -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "status": "new",
        "created_registry_keys": [],
        "registry_values": {},
        "retired_registry_values": {},
        "created_junctions": {},
        "created_files": {},
        "retired_files": {},
        "pending_files": {},
        "shortcuts": {},
    }


def _registry_identity(key: str, name: str) -> str:
    """Canonical, case-insensitive identity for a registry value.

    Windows registry key and value names are case-insensitive, so the journal
    must use a single normalized identity everywhere it compares or looks up
    an entry.  The raw spelling is intentionally not preserved here: the
    journal only ever needs the canonical form.
    """
    return f"{key.rstrip(chr(92)).casefold()}\u0000{name.casefold()}"


def _windows_path_key(path: Path | str) -> str:
    """Stable, host-independent identity for a Windows-style path.

    ``/`` and ``\\`` are equivalent separators and Windows paths are
    case-insensitive, so both are folded here.  This deliberately avoids
    ``Path.resolve()``/``Path.is_absolute()``: those follow the *host* OS
    semantics and would misclassify ``C:\\Program Files\\...`` on POSIX.
    """
    return ntpath.normpath(str(path).replace("/", "\\")).casefold()


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != STATE_SCHEMA:
        raise RuntimeError(f"unsupported state schema: {data.get('schema')}")
    _normalize_state_identity(data)
    return data


def _normalize_state_identity(state: dict[str, Any]) -> None:
    """Migrate schema-1 journals whose identity keys are not canonical.

    Older journals stored the raw ``key\u0000name`` spelling.  Every map that
    keys on registry identity or on Windows file path identity is rewritten to
    the canonical form so apply / diff / reconcile / uninstall all agree.
    A collision after casefolding means two distinct entries collapse onto one
    identity; that is ambiguous, so the journal is rejected rather than
    silently dropping one of them.
    """
    for section in ("registry_values", "retired_registry_values"):
        mapping = state.get(section)
        if not isinstance(mapping, dict):
            continue
        normalized: dict[str, Any] = {}
        for identity, entry in mapping.items():
            if "\u0000" not in identity:
                raise RuntimeError(f"invalid registry identity in journal: {identity!r}")
            key, name = identity.split("\u0000", 1)
            canonical = _registry_identity(key, name)
            if canonical in normalized:
                raise RuntimeError(
                    "ambiguous registry identity after case folding: "
                    f"{identity!r} conflicts with an existing journal entry"
                )
            normalized[canonical] = entry
        state[section] = normalized

    created_keys = state.get("created_registry_keys")
    if isinstance(created_keys, list):
        canonical_keys: list[str] = []
        for key in created_keys:
            canonical = key.rstrip("\\").casefold()
            if canonical not in canonical_keys:
                canonical_keys.append(canonical)
        state["created_registry_keys"] = canonical_keys

    # File maps deliberately keep their raw filesystem path keys: those keys
    # are used to open/delete real files, and canonical Windows spelling is
    # not a valid POSIX path.  Ownership lookups go through
    # ``_windows_path_key`` instead, which is host-independent.


def _find_file_entry_key(mapping: dict[str, Any], path: Path | str) -> str | None:
    canonical = _windows_path_key(path)
    for key in mapping:
        if _windows_path_key(key) == canonical:
            return key
    return None


def _find_file_entry(mapping: dict[str, Any], path: Path | str) -> Any | None:
    key = _find_file_entry_key(mapping, path)
    return mapping[key] if key is not None else None


def _classify_existing_archive(
    journal: dict[str, Any],
    operation: InstallArchiveFile,
    current_sha: str | None,
    wanted_sha: str,
) -> tuple[str, str | None]:
    """Classify an existing regular-file destination the same way apply does.

    Returns ``(kind, entry_key)`` where ``kind`` is one of ``same``,
    ``upgrade``, ``reuse`` or ``conflict``.  ``inspect_live_diff`` and
    ``_apply`` both route through this so a diff can never disagree with what
    apply would do.  Ownership is decided by the journaled installed hash, not
    by the wanted hash: external bytes that happen to match the new payload are
    still an external change, not a silent adoption.
    """
    entry_key = _find_file_entry_key(journal, operation.destination)
    if entry_key is not None:
        installed_sha = journal[entry_key].get("installed_sha256")
        if installed_sha is not None and current_sha == installed_sha:
            # Still installer-owned and unchanged.  Identical payload is a
            # no-op; a different payload is a safe upgrade.
            return ("same" if current_sha == wanted_sha else "upgrade"), entry_key
        # Journaled but changed externally (even if the external bytes happen
        # to equal the new payload): never silently adopted.
        if operation.reuse_existing:
            return "reuse", entry_key
        return "conflict", entry_key
    if current_sha == wanted_sha:
        return "same", None
    if operation.reuse_existing:
        return "reuse", None
    return "conflict", None


def _preflight_archive_destinations(
    operations: tuple[Operation, ...],
    archive_payloads: dict[int, bytes],
    prior_state: dict[str, Any] | None,
) -> None:
    """Fail archive destination conflicts before any install mutation.

    Archive payloads have already been fully read/validated when this helper is
    called.  This second, read-only gate checks the destinations against the
    *pre-apply* ownership journal so a strict conflict, reparse path, or
    non-regular target cannot be discovered only after the state file or an
    earlier registry/junction/shortcut operation has been modified.

    The normal ``_apply(InstallArchiveFile)`` checks remain authoritative at
    mutation time; this is an early fail-fast gate, not a replacement for those
    runtime re-checks.
    """
    created_files = (prior_state or {}).get("created_files", {})

    for index, operation in enumerate(operations):
        if not isinstance(operation, InstallArchiveFile):
            continue

        payload = archive_payloads[index]
        wanted_sha = hashlib.sha256(payload).hexdigest()
        destination = operation.destination

        _reject_reparse_path(destination)
        if not os.path.lexists(destination):
            continue
        if not destination.is_file():
            raise RuntimeError(
                f"file destination exists but is not a file: {destination}"
            )

        current_sha = _file_sha256(destination)
        kind, _entry_key = _classify_existing_archive(
            created_files, operation, current_sha, wanted_sha
        )
        if kind == "conflict":
            raise RuntimeError(
                "refusing to overwrite existing shared file with different content: "
                f"{destination}"
            )


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
        "file_count": len(state.get("created_files", {})),
        "shortcut_count": len(state.get("shortcuts", {})),
        "conflict_count": len(state.get("uninstall_conflicts", [])),
    }


def _rollback_retired_files(
    rollback_journal: list[tuple[Path, bytes]],
    ownership_snapshot: tuple[dict[str, Any], dict[str, Any]] | None,
    state: dict[str, Any],
) -> Exception | None:
    """Undo this apply call's destructive file retirements.

    Successful deletions are restored in reverse order through the project's
    own atomic-write path (never a bare ``write_bytes``), then the journal's
    file-ownership maps are reset to the pre-retirement snapshot so a restored
    file is still recorded as installer-owned instead of silently disowned.
    Restoration is attempted for every entry even if an earlier one fails, and
    the caller is told about any failure so it can fail loudly rather than
    reporting a clean rollback.  Returns ``None`` when nothing failed.
    """
    problems: list[str] = []
    for path, payload in reversed(rollback_journal):
        try:
            # A rollback must never replace a file another process recreated
            # after our retirement unlink.  Publish the old bytes only when
            # the path is still absent; an occupied path is a loud rollback
            # conflict and is preserved verbatim.
            _atomic_create_bytes(path, payload)
        except Exception as exc:  # noqa: BLE001 - aggregated below
            problems.append(f"{path}: {exc}")
    if ownership_snapshot is not None:
        created_snapshot, retired_snapshot = ownership_snapshot
        state["created_files"] = created_snapshot
        state["retired_files"] = retired_snapshot
    if problems:
        return RuntimeError("; ".join(problems))
    return None


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
    mapping = {
        # Stable Win32 registry type IDs. Keeping these local avoids importing
        # winreg in pure classification tests that run on non-Windows CI.
        "sz": 1,  # REG_SZ
        "expand_sz": 2,  # REG_EXPAND_SZ
        "dword": 4,  # REG_DWORD
        "multi_sz": 7,  # REG_MULTI_SZ
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


def _registry_operation_matches_snapshot(
    operation: SetRegistryValue,
    snapshot: dict[str, Any],
) -> bool:
    wanted = {
        "type": _registry_kind(operation.kind),
        "data": _encode_json_value(operation.data),
    }
    if snapshot == wanted:
        return True
    if (
        operation.kind == "sz"
        and operation.name.casefold() == "vbe71dllpath"
        and snapshot.get("type") == _registry_kind("sz")
        and isinstance(snapshot.get("data"), str)
        and isinstance(operation.data, str)
    ):
        return _same_path(Path(snapshot["data"]), Path(operation.data))
    return False


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


class _Filetime(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class _FileDispositionInfo(ctypes.Structure):
    # FILE_DISPOSITION_INFO: a single BOOLEAN.  Passing a one-byte structure
    # (rather than a lone ctypes boolean) keeps ``ctypes.sizeof`` honest for
    # the ``dwBufferSize`` argument of SetFileInformationByHandle.
    _fields_ = [("DeleteFile", ctypes.c_ubyte)]


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", ctypes.c_uint32),
        ("ftCreationTime", _Filetime),
        ("ftLastAccessTime", _Filetime),
        ("ftLastWriteTime", _Filetime),
        ("dwVolumeSerialNumber", ctypes.c_uint32),
        ("nFileSizeHigh", ctypes.c_uint32),
        ("nFileSizeLow", ctypes.c_uint32),
        ("nNumberOfLinks", ctypes.c_uint32),
        ("nFileIndexHigh", ctypes.c_uint32),
        ("nFileIndexLow", ctypes.c_uint32),
    ]


# Directory open flags/rights used by the Windows parent-chain lock.
_FILE_LIST_DIRECTORY = 0x0001
_FILE_READ_ATTRIBUTES = 0x0080
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_INVALID_HANDLE_VALUE = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1

# Rights/flags used by the handle-bound owned-file deletion path.
_GENERIC_READ = 0x80000000
_DELETE = 0x00010000
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_ERROR_HANDLE_EOF = 38
_FILE_DISPOSITION_INFO_CLASS = 4
_HANDLE_READ_CHUNK = 1024 * 1024

_KERNEL32: Any = None


def _get_kernel32():
    """Return ``kernel32`` with explicit signatures, loading it once.

    Explicit ``restype``/``argtypes`` matter: without them ctypes truncates
    the 64-bit ``HANDLE`` returned by ``CreateFileW`` to a 32-bit int, which
    would silently break handle comparisons and ``CloseHandle``.
    """
    global _KERNEL32
    if _KERNEL32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        )
        kernel32.GetFileInformationByHandle.restype = ctypes.c_int
        kernel32.GetFileInformationByHandle.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(_ByHandleFileInformation),
        )
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.ReadFile.restype = ctypes.c_int
        kernel32.ReadFile.argtypes = (
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        )
        kernel32.SetFileInformationByHandle.restype = ctypes.c_int
        kernel32.SetFileInformationByHandle.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        )
        _KERNEL32 = kernel32
    return _KERNEL32


def _open_locked_directory(kernel32, directory: Path) -> int:
    """Open ``directory`` and hold it against rename/delete.

    ``FILE_SHARE_READ | FILE_SHARE_WRITE`` deliberately omits
    ``FILE_SHARE_DELETE``: on Windows a delete/rename of the directory entry
    needs delete access, so withholding the share bit while holding a data
    access right (``FILE_LIST_DIRECTORY``) makes a concurrent rename fail with
    a sharing violation instead of silently redirecting our write.  A
    read-attributes-only handle is *not* sufficient -- empirically the rename
    still succeeds -- so the list-directory right is required too.

    ``FILE_FLAG_OPEN_REPARSE_POINT`` makes the handle refer to the directory
    entry itself, so the metadata check below sees a planted junction rather
    than its target.  Any failure raises instead of falling back to an
    unlocked write.
    """
    handle = kernel32.CreateFileW(
        str(directory),
        _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ByHandleFileInformation()
    if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(error)
    attributes = info.dwFileAttributes
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        kernel32.CloseHandle(handle)
        raise RuntimeError(
            f"refusing to write below a reparse-point directory: {directory}"
        )
    if not attributes & _FILE_ATTRIBUTE_DIRECTORY:
        kernel32.CloseHandle(handle)
        raise RuntimeError(f"expected a directory while locking the parent chain: {directory}")
    return handle


def _iter_directory_chain(target: Path):
    """Yield each real directory from the filesystem anchor down to ``target``.

    The anchor itself (``C:\\`` or a UNC share root) cannot be renamed or
    replaced by another process, so it is used as the immovable base and only
    the components below it are locked.  Relative paths are already frozen to
    absolute by the caller, so this never walks out of the intended tree.
    """
    anchor = Path(target.anchor)
    try:
        parts = target.relative_to(anchor).parts
    except ValueError:
        parts = target.parts
    current = anchor
    for part in parts:
        current = current / part
        yield current


@contextlib.contextmanager
def _locked_parent_chain(path: Path):
    """Hold every existing directory of ``path.parent`` against rename/delete.

    Yields the frozen absolute destination path (``abspath`` normalizes ``..``
    lexically but never resolves symlinks) so the caller performs its reparse
    checks, temp creation and ``os.replace`` on exactly the path that was
    locked.  On a non-Windows host this is a transparent pass-through: it
    keeps the existing portable behaviour instead of pretending to offer the
    Windows anti-race guarantee.
    """
    if os.name != "nt":
        yield path
        return

    frozen = Path(os.path.abspath(str(path)))
    kernel32 = _get_kernel32()
    handles: list[int] = []
    try:
        for directory in _iter_directory_chain(frozen.parent):
            handles.append(_open_locked_directory(kernel32, directory))
        yield frozen
    finally:
        for handle in reversed(handles):
            kernel32.CloseHandle(handle)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Expose ``payload`` at ``path`` atomically, never leaving a partial file.

    The bytes are written to a sibling temp file in the same directory, flushed
    and fsynced, then moved into place with ``os.replace``.  A failure at any
    point removes the temp file, so the destination is either untouched or
    complete; it is never truncated.  On Windows the whole sequence runs while
    every directory in ``path.parent`` is held open without
    ``FILE_SHARE_DELETE``, so a concurrent process cannot rename a parent
    directory and swap in a junction between the reparse check and the
    replace; the reparse guard is still re-checked immediately before the
    replace.  This closes the partial-write and parent-swap windows but does
    not claim to be crash-transactional.
    """
    with _locked_parent_chain(path) as locked_path:
        _reject_reparse_path(locked_path)
        fd, temp_name = tempfile.mkstemp(
            prefix=locked_path.name + ".", suffix=".tmp", dir=locked_path.parent
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _reject_reparse_path(locked_path)
            os.replace(temp_name, locked_path)
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _publish_temp_no_replace(temp_name: str, destination: Path) -> None:
    """Publish a complete sibling temp file without replacing ``destination``.

    Windows ``rename`` is non-replacing.  POSIX ``rename`` replaces, so use a
    hard-link publish there instead; the sibling temp file guarantees the same
    filesystem.  Both forms fail atomically when another process wins the
    destination name, preserving that external file.
    """
    if os.name == "nt":
        os.rename(temp_name, destination)
        return
    os.link(temp_name, destination)


def _atomic_create_bytes_locked(locked_path: Path, payload: bytes) -> None:
    """Atomically create ``locked_path`` while its parent chain is held.

    The destination must remain absent.  This is deliberately different from
    ``_atomic_write_bytes``: archive ownership must never overwrite a file that
    appeared after the installer's earlier absence check.
    """
    _reject_reparse_path(locked_path)
    if os.path.lexists(locked_path):
        raise FileExistsError(f"refusing to replace concurrently created file: {locked_path}")
    fd, temp_name = tempfile.mkstemp(
        prefix=locked_path.name + ".", suffix=".tmp", dir=locked_path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _reject_reparse_path(locked_path)
        _publish_temp_no_replace(temp_name, locked_path)
    finally:
        try:
            os.unlink(temp_name)
        except OSError:
            pass


def _atomic_create_bytes(path: Path, payload: bytes) -> None:
    """Create a complete file atomically without ever replacing an occupant."""
    with _locked_parent_chain(path) as locked_path:
        _atomic_create_bytes_locked(locked_path, payload)


@dataclass(frozen=True)
class OwnedFileDeletion:
    """Outcome of a handle-bound owned-file deletion attempt.

    ``outcome`` is one of ``removed`` (the file was deleted and ``payload``
    holds the exact bytes that were read back through the locked handle),
    ``missing`` (the path genuinely did not exist) or ``external`` (the path
    is no longer safely ours and was left untouched; ``reason`` names why).
    Operational failures (sharing/permission/metadata/read/disposition) are
    raised as ``OSError`` instead of being classified, so callers fail closed
    rather than silently releasing ownership of a busy file.
    """

    outcome: str
    payload: bytes | None = None
    reason: str | None = None


def _read_all_from_handle(kernel32, handle: int) -> bytes:
    """Read every byte of an open file handle, looping until a zero-byte read.

    The loop (rather than a single read sized from the initial metadata) is
    deliberate: it keeps reading to EOF and never trusts a size captured
    before the handle was locked.
    """
    buffer = ctypes.create_string_buffer(_HANDLE_READ_CHUNK)
    chunks: list[bytes] = []
    while True:
        read = ctypes.c_uint32(0)
        ok = kernel32.ReadFile(
            handle,
            buffer,
            _HANDLE_READ_CHUNK,
            ctypes.byref(read),
            None,
        )
        if not ok:
            error = ctypes.get_last_error()
            if error == _ERROR_HANDLE_EOF:
                break
            raise ctypes.WinError(error)
        if read.value == 0:
            break
        chunks.append(buffer.raw[: read.value])
    return b"".join(chunks)


def _delete_owned_file_by_handle(
    path: Path,
    expected_sha256: str | None,
) -> OwnedFileDeletion:
    """Delete ``path`` only when it is still the exact file we installed.

    On Windows this binds read/hash/delete to one file object instead of
    re-opening the path: the parent directory chain is held against
    rename/delete by ``_locked_parent_chain``, and the target is opened with
    ``GENERIC_READ | DELETE | FILE_READ_ATTRIBUTES`` and a share mode of
    ``FILE_SHARE_READ`` only (no ``FILE_SHARE_WRITE`` / ``FILE_SHARE_DELETE``).
    That blocks a concurrent same-name replacement, rename or content edit
    between the hash and the delete.  ``FILE_FLAG_OPEN_REPARSE_POINT`` keeps
    the handle on the directory entry itself so a planted link is seen, not
    followed.  The bytes are read through that same handle, and the delete is
    requested with ``SetFileInformationByHandle(FileDispositionInfo)`` on the
    same handle; the pathname is never reopened for hashing or deletion.

    Non-Windows hosts keep the existing portable behaviour; that fallback
    makes no Windows handle-level race guarantee.
    """
    if os.name != "nt":
        return _delete_owned_file_portable(path, expected_sha256)

    # Reparse classification stays ahead of opening so a swapped-in link is
    # never opened, hashed or deleted through.
    if _is_reparse_or_symlink(path) or _has_reparse_ancestor(path):
        return OwnedFileDeletion("external", reason="reparse")

    # Acquire the parent-directory lock separately so that a genuinely absent
    # parent chain is classified as ``missing`` while every failure *inside*
    # the locked window (metadata, read, disposition) keeps propagating as an
    # OSError for the caller to fail closed on.
    lock = _locked_parent_chain(path)
    try:
        frozen = lock.__enter__()
    except FileNotFoundError:
        return OwnedFileDeletion("missing")
    try:
        return _delete_owned_file_at_locked_path(frozen, expected_sha256)
    finally:
        lock.__exit__(None, None, None)


def _delete_owned_file_at_locked_path(
    frozen: Path,
    expected_sha256: str | None,
) -> OwnedFileDeletion:
    """Windows target-handle delete while the caller holds the parent chain."""
    kernel32 = _get_kernel32()
    handle = kernel32.CreateFileW(
        str(frozen),
        _GENERIC_READ | _DELETE | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
            return OwnedFileDeletion("missing")
        raise ctypes.WinError(error)
    try:
        info = _ByHandleFileInformation()
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        attributes = info.dwFileAttributes
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            return OwnedFileDeletion("external", reason="reparse")
        if attributes & _FILE_ATTRIBUTE_DIRECTORY:
            return OwnedFileDeletion("external", reason="non-file")
        if expected_sha256 is None:
            return OwnedFileDeletion("external", reason="no recorded hash")

        payload = _read_all_from_handle(kernel32, handle)
        current_sha = hashlib.sha256(payload).hexdigest()
        if current_sha != expected_sha256:
            return OwnedFileDeletion("external", reason="hash mismatch")

        disposition = _FileDispositionInfo(1)
        if not kernel32.SetFileInformationByHandle(
            handle,
            _FILE_DISPOSITION_INFO_CLASS,
            ctypes.byref(disposition),
            ctypes.sizeof(disposition),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return OwnedFileDeletion("removed", payload=payload)
    finally:
        kernel32.CloseHandle(handle)


def _atomic_upgrade_owned_bytes(
    path: Path,
    payload: bytes,
    expected_sha256: str | None,
) -> None:
    """Upgrade only the exact installer-owned file, never a concurrent replacement.

    On Windows the parent chain stays locked across handle-bound verification,
    deletion and non-replacing publication of the new payload.  The target
    handle denies write/delete sharing while it is hashed and removed.  If an
    external process wins the now-free pathname before publication, creation
    fails and that external file is preserved; rollback also refuses to
    replace it.
    """
    if os.name != "nt":
        deleted = _delete_owned_file_portable(path, expected_sha256)
        if deleted.outcome != "removed" or deleted.payload is None:
            raise RuntimeError(
                f"owned file changed before upgrade: {path} ({deleted.reason or deleted.outcome})"
            )
        try:
            _atomic_create_bytes(path, payload)
        except Exception as exc:
            try:
                _atomic_create_bytes(path, deleted.payload)
            except Exception as rollback_exc:
                raise RuntimeError(
                    f"archive upgrade failed and rollback could not restore {path}: {rollback_exc}"
                ) from exc
            raise
        return

    if _is_reparse_or_symlink(path) or _has_reparse_ancestor(path):
        raise RuntimeError(f"owned file became a reparse path before upgrade: {path}")
    lock = _locked_parent_chain(path)
    try:
        frozen = lock.__enter__()
    except FileNotFoundError as exc:
        raise RuntimeError(f"owned file disappeared before upgrade: {path}") from exc
    try:
        # Prepare and durably flush the complete new payload *before* touching
        # the installed file.  Disk-full/temp-write failures therefore leave
        # the old owned file intact and never require rollback.
        fd, temp_name = tempfile.mkstemp(
            prefix=frozen.name + ".", suffix=".tmp", dir=frozen.parent
        )
        try:
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                # fd belongs to fdopen once entered; if fdopen itself failed,
                # close the raw descriptor before propagating.
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise

            deleted = _delete_owned_file_at_locked_path(frozen, expected_sha256)
            if deleted.outcome != "removed" or deleted.payload is None:
                raise RuntimeError(
                    f"owned file changed before upgrade: {path} ({deleted.reason or deleted.outcome})"
                )
            try:
                _publish_temp_no_replace(temp_name, frozen)
                temp_name = ""
            except Exception as exc:
                try:
                    _atomic_create_bytes_locked(frozen, deleted.payload)
                except Exception as rollback_exc:
                    raise RuntimeError(
                        f"archive upgrade failed and rollback could not restore {path}: {rollback_exc}"
                    ) from exc
                raise
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
    finally:
        lock.__exit__(None, None, None)


def _delete_owned_file_portable(
    path: Path,
    expected_sha256: str | None,
) -> OwnedFileDeletion:
    """Portable fallback for ``_delete_owned_file_by_handle`` (non-Windows).

    Keeps the pre-existing reparse-before-hash, hash-then-unlink ordering.
    Unlike the Windows path it cannot bind the hash to the delete, so it is
    only used where no Windows handle-level guarantee is available.
    """
    if _is_reparse_or_symlink(path) or _has_reparse_ancestor(path):
        return OwnedFileDeletion("external", reason="reparse")
    if not os.path.lexists(path):
        return OwnedFileDeletion("missing")
    if not path.is_file():
        return OwnedFileDeletion("external", reason="non-file")
    if expected_sha256 is None:
        return OwnedFileDeletion("external", reason="no recorded hash")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        return OwnedFileDeletion("external", reason="hash mismatch")
    path.unlink()
    return OwnedFileDeletion("removed", payload=payload)


def _is_reparse_or_symlink(path: Path) -> bool:
    """True when ``path`` exists and is a symlink or Windows reparse point.

    Uses ``lstat`` so the check sees the link itself rather than its target.
    ``st_file_attributes`` is only present on Windows, which keeps this
    working on Python 3.11 while remaining a no-op on POSIX.
    """
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        # ENOENT and ENOTDIR both mean there is no target object at this
        # pathname.  ENOTDIR is deterministic path-shape evidence (one of the
        # parent components is a regular file), not a transient metadata
        # failure.  Let the caller's ancestor walk report that parent as a
        # non-directory.  Other OSErrors (PermissionError, I/O errors, etc.)
        # still propagate so ownership is never silently released.
        return False
    except OSError:
        # Metadata failure is not evidence that ownership changed.  Propagate
        # it so callers fail closed and retain ownership for a later retry.
        raise
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _iter_ancestors(path: Path):
    """Yield every ancestor of ``path`` from its parent up to the filesystem root."""
    current = path.parent
    while True:
        yield current
        parent = current.parent
        if parent == current:
            return
        current = parent


def _has_reparse_ancestor(path: Path) -> bool:
    return any(_is_reparse_or_symlink(ancestor) for ancestor in _iter_ancestors(path))


def _reject_reparse_path(path: Path) -> None:
    """Refuse to create/write ``path`` through a symlink or reparse point.

    Both the destination itself and every already-existing parent component
    are checked.  Without the ancestor check an attacker who can plant a
    symlink/junction in a parent directory could redirect our mkdir/write/
    replace outside the planned tree.  A concurrent swap between this check
    and the write is closed on Windows by ``_locked_parent_chain``; on other
    hosts the portable fallback keeps only this check.
    """
    if _is_reparse_or_symlink(path):
        raise RuntimeError(f"refusing to write through a reparse point: {path}")
    for ancestor in _iter_ancestors(path):
        if _is_reparse_or_symlink(ancestor):
            raise RuntimeError(
                f"refusing to write below a reparse point in a parent directory: {path}"
            )
        if os.path.lexists(ancestor) and not ancestor.is_dir():
            raise RuntimeError(
                f"refusing to write below a non-directory parent component: {ancestor}"
            )


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member_parts(member: str) -> tuple[str, ...]:
    """Split an archive member into path components, refusing unsafe ones.

    Separator normalization is allowed, but rooted/drive semantics are never
    stripped.  Absolute paths, UNC paths, drive-relative/drive-absolute paths,
    empty members, and ``..`` traversal all fail closed before extraction.
    The returned parts are the single source used to build the extractor target.
    """
    normalized = member.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise RuntimeError(f"unsafe archive member path: {member}")
    if ntpath.splitdrive(normalized)[0]:
        raise RuntimeError(f"unsafe archive member path: {member}")

    relative = Path(normalized)
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError(f"unsafe archive member path: {member}")
    if relative.is_absolute():
        raise RuntimeError(f"unsafe archive member path: {member}")
    return parts


def _validated_extracted_member(temp_root: Path, member: str) -> Path:
    """Return the resolved path of an extracted member, refusing any escape.

    Extraction tools honour symlink/reparse entries, so a tampered archive can
    make the requested member -- or a parent directory inside the extraction
    root -- a link that points outside ``temp_root``.  Before the payload is
    read, the extraction root and every component of the member path are
    lstat-checked for symlink/reparse attributes, then both paths are resolved
    with ``strict=True`` and the member must land strictly inside the root.
    Any failure raises ``RuntimeError``; nothing is ever read through a link.
    """
    parts = _safe_member_parts(member)

    if _is_reparse_or_symlink(temp_root):
        raise RuntimeError(
            f"archive extraction root is a reparse point: {temp_root}"
        )
    current = temp_root
    for part in parts:
        current = current / part
        if _is_reparse_or_symlink(current):
            raise RuntimeError(
                f"archive member traverses a reparse point: {current}"
            )

    try:
        resolved_root = temp_root.resolve(strict=True)
        resolved_member = current.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            f"archive member could not be resolved: {member}: {exc}"
        ) from exc

    if resolved_member == resolved_root or not resolved_member.is_relative_to(
        resolved_root
    ):
        raise RuntimeError(
            f"archive member escapes the extraction root: {member} -> {resolved_member}"
        )
    return resolved_member


def _read_archive_member(operation: InstallArchiveFile) -> bytes:
    parts = _safe_member_parts(operation.member)
    member = "/".join(parts)

    with tempfile.TemporaryDirectory(prefix="acad-portable-archive-") as temp_dir:
        temp_root = Path(temp_dir)
        bundled_helper = operation.archive.parent.parent / "hui7za.dll"
        if bundled_helper.is_file():
            command = [
                str(bundled_helper),
                "x",
                str(operation.archive),
                member,
                f"-o{temp_root}",
                "-y",
            ]
            if operation.password is not None:
                command.append(f"-p{operation.password}")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="mbcs",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"bundled 7-Zip extraction failed ({result.returncode}): "
                    f"{result.stdout} {result.stderr}".strip()
                )
        else:
            try:
                import py7zr
            except ImportError as exc:
                raise RuntimeError(
                    "no bundled 7-Zip helper found and py7zr is unavailable"
                ) from exc
            try:
                with py7zr.SevenZipFile(
                    operation.archive, mode="r", password=operation.password
                ) as archive:
                    archive.extract(path=temp_root, targets=[member])
            except Exception as exc:
                raise RuntimeError(
                    f"Python archive extraction failed for {operation.archive}: {exc}"
                ) from exc
        extracted = _validated_extracted_member(temp_root, member)
        if not extracted.is_file():
            raise RuntimeError(
                f"archive member was not extracted: {operation.archive} :: {operation.member}"
            )
        return extracted.read_bytes()
