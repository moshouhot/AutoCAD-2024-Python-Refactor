from __future__ import annotations

import codecs
from pathlib import Path


def read_legacy_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "gb18030"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("gb18030", errors="replace"), "gb18030-replace"

