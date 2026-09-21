from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .textio import read_legacy_text


@dataclass(frozen=True)
class FeatureConfig:
    values: dict[str, str]
    encoding: str

    @classmethod
    def load(cls, path: Path) -> "FeatureConfig":
        text, encoding = read_legacy_text(path)
        values: dict[str, str] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", ";")) or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return cls(values=values, encoding=encoding)

    def enabled(self, key: str, default: bool = False) -> bool:
        value = self.values.get(key)
        if value is None:
            return default
        return value.strip() in {"1", "true", "True", "yes", "on"}

