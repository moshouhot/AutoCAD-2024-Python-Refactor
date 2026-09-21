from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

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


@dataclass
class FakeWindowsState:
    registry: dict[str, dict[str, tuple[str, object]]] = field(default_factory=dict)
    directories: set[str] = field(default_factory=set)
    junctions: dict[str, str] = field(default_factory=dict)
    shortcuts: dict[str, tuple[str, str, str | None]] = field(default_factory=dict)
    state_files: dict[str, dict[str, object]] = field(default_factory=dict)

    def snapshot(self) -> "FakeWindowsState":
        return deepcopy(self)


class FakeWindowsAdapter:
    def __init__(self, state: FakeWindowsState | None = None):
        self.state = state or FakeWindowsState()

    def apply_plan(self, plan: InstallPlan) -> None:
        for operation in plan.operations:
            self.apply(operation)

    def apply(self, operation: Operation) -> None:
        if isinstance(operation, EnsureRegistryKey):
            self.state.registry.setdefault(operation.key, {})
            return
        if isinstance(operation, SetRegistryValue):
            values = self.state.registry.setdefault(operation.key, {})
            values[operation.name] = (operation.kind, operation.data)
            return
        if isinstance(operation, EnsureDirectory):
            self.state.directories.add(str(operation.path))
            return
        if isinstance(operation, EnsureJunction):
            path = str(operation.path)
            target = str(operation.target)
            existing = self.state.junctions.get(path)
            if existing is not None and existing != target:
                raise RuntimeError(f"junction target conflict: {path} -> {existing}, wanted {target}")
            self.state.junctions[path] = target
            return
        if isinstance(operation, CreateShortcut):
            self.state.shortcuts[str(operation.path)] = (
                str(operation.target),
                operation.arguments,
                str(operation.working_directory) if operation.working_directory else None,
            )
            return
        if isinstance(operation, WriteInstallState):
            self.state.state_files[str(operation.path)] = deepcopy(operation.payload)
            return
        raise TypeError(f"unsupported operation: {type(operation).__name__}")

