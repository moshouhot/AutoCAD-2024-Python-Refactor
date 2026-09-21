from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .textio import read_legacy_text


SECTION_RE = re.compile(r"^\[(?P<deleted>-)?(?P<key>[^\]]+)\]$")
VALUE_RE = re.compile(r'^(?P<name>@|"(?:\\.|[^"])*")=(?P<data>.*)$')


def _decode_quoted(token: str) -> str:
    if not (token.startswith('"') and token.endswith('"')):
        return token
    inner = token[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner) and inner[i + 1] in {'\\', '"'}:
            out.append(inner[i + 1])
            i += 2
        else:
            out.append(inner[i])
            i += 1
    return "".join(out)


@dataclass(frozen=True)
class RegistryValue:
    name: str
    kind: str
    data: object
    raw: str


@dataclass(frozen=True)
class RegistrySection:
    key: str
    deleted: bool
    values: tuple[RegistryValue, ...]


@dataclass(frozen=True)
class RegistryDocument:
    sections: tuple[RegistrySection, ...]
    encoding: str
    source: Path

    @classmethod
    def load(cls, path: Path) -> "RegistryDocument":
        text, encoding = read_legacy_text(path)
        return cls.parse(text, source=path, encoding=encoding)

    @classmethod
    def parse(cls, text: str, source: Path | None = None, encoding: str = "memory") -> "RegistryDocument":
        # Join .reg multiline hex values before parsing.
        logical_lines: list[str] = []
        pending = ""
        for raw in text.splitlines():
            line = raw.strip()
            if pending:
                pending += line
            else:
                pending = line
            if pending.endswith("\\"):
                pending = pending[:-1]
                continue
            logical_lines.append(pending)
            pending = ""
        if pending:
            logical_lines.append(pending)

        sections: list[RegistrySection] = []
        key: str | None = None
        deleted = False
        values: list[RegistryValue] = []

        def flush() -> None:
            nonlocal key, deleted, values
            if key is not None:
                sections.append(RegistrySection(key=key, deleted=deleted, values=tuple(values)))
            key = None
            deleted = False
            values = []

        for line in logical_lines:
            if not line or line.startswith(";") or line.startswith("Windows Registry Editor"):
                continue
            section_match = SECTION_RE.match(line)
            if section_match:
                flush()
                key = section_match.group("key")
                deleted = bool(section_match.group("deleted"))
                continue
            if key is None:
                continue
            value_match = VALUE_RE.match(line)
            if not value_match:
                continue
            name_token = value_match.group("name")
            name = "" if name_token == "@" else _decode_quoted(name_token)
            raw_data = value_match.group("data")
            values.append(_parse_value(name, raw_data))
        flush()
        return cls(sections=tuple(sections), encoding=encoding, source=source or Path("<memory>"))

    def first_string(self, value_name: str) -> str | None:
        for section in self.sections:
            for value in section.values:
                if value.name.casefold() == value_name.casefold() and value.kind == "sz":
                    return str(value.data)
        return None


def _parse_value(name: str, raw_data: str) -> RegistryValue:
    data = raw_data.strip()
    if data == "-":
        return RegistryValue(name=name, kind="delete", data=None, raw=raw_data)
    if data.startswith('"') and data.endswith('"'):
        return RegistryValue(name=name, kind="sz", data=_decode_quoted(data), raw=raw_data)
    if data.lower().startswith("dword:"):
        try:
            value = int(data.split(":", 1)[1], 16)
        except ValueError:
            value = data
        return RegistryValue(name=name, kind="dword", data=value, raw=raw_data)
    if data.lower().startswith("hex(2):"):
        payload = data.split(":", 1)[1]
        try:
            raw_bytes = bytes(int(token, 16) for token in payload.split(",") if token.strip())
            value = raw_bytes.decode("utf-16le").rstrip("\x00")
        except (ValueError, UnicodeDecodeError):
            return RegistryValue(name=name, kind="hex(2)", data=payload, raw=raw_data)
        return RegistryValue(name=name, kind="expand_sz", data=value, raw=raw_data)
    if data.lower().startswith("hex"):
        kind = data.split(":", 1)[0].lower()
        return RegistryValue(name=name, kind=kind, data=data.split(":", 1)[1] if ":" in data else "", raw=raw_data)
    return RegistryValue(name=name, kind="raw", data=data, raw=raw_data)


class PathRebaser:
    def __init__(self, mappings: list[tuple[str, str]]):
        cleaned = []
        for old, new in mappings:
            if old and new and old.casefold() != new.casefold():
                cleaned.append((old.rstrip("\\/"), new.rstrip("\\/")))
        self.mappings = sorted(cleaned, key=lambda item: len(item[0]), reverse=True)

    def apply(self, value: str) -> str:
        result = value
        for old, new in self.mappings:
            pattern = re.escape(old) + r"(?=[\\/;]|$)"
            result = re.sub(pattern, lambda _: new, result, flags=re.IGNORECASE)
        return result

    def contains_legacy_prefix(self, value: str) -> bool:
        return any(
            re.search(re.escape(old) + r"(?=[\\/;]|$)", value, flags=re.IGNORECASE)
            for old, _new in self.mappings
        )

