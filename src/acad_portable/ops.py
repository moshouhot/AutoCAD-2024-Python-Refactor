from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnsureRegistryKey:
    key: str


@dataclass(frozen=True)
class SetRegistryValue:
    key: str
    name: str
    kind: str
    data: object
    preserve_existing: bool = False


@dataclass(frozen=True)
class EnsureDirectory:
    path: Path


@dataclass(frozen=True)
class EnsureJunction:
    path: Path
    target: Path


@dataclass(frozen=True)
class CreateShortcut:
    path: Path
    target: Path
    arguments: str = ""
    working_directory: Path | None = None


@dataclass(frozen=True)
class InstallArchiveFile:
    archive: Path
    member: str
    destination: Path
    password: str | None = None
    reuse_existing: bool = False


@dataclass(frozen=True)
class WriteInstallState:
    path: Path
    payload: dict[str, object]


Operation = (
    EnsureRegistryKey
    | SetRegistryValue
    | EnsureDirectory
    | EnsureJunction
    | CreateShortcut
    | InstallArchiveFile
    | WriteInstallState
)


def operation_to_dict(operation: Operation) -> dict[str, object]:
    payload = asdict(operation)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
    payload["op"] = type(operation).__name__
    return payload

