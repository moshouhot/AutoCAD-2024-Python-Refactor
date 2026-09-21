from __future__ import annotations

import argparse
import codecs
import re
from pathlib import Path


SECTION_RE = re.compile(r"^\[(?P<deleted>-)?(?P<key>[^\]]+)\]$")


def decode(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16")
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig")
    for encoding in ("gb18030", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def parse_sections(text: str) -> list[tuple[str, list[str]]]:
    result: list[tuple[str, list[str]]] = []
    key: str | None = None
    body: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        match = SECTION_RE.match(line.strip())
        if match:
            if key is not None:
                result.append((key, body))
            key = ("-" if match.group("deleted") else "") + match.group("key")
            body = []
        elif key is not None:
            body.append(line)
    if key is not None:
        result.append((key, body))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--keys-only", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    patterns = [p.lower() for p in args.patterns]
    hits = 0
    for key, body in parse_sections(decode(args.path)):
        haystack = "\n".join([key, *body]).lower()
        if not any(pattern in haystack for pattern in patterns):
            continue
        print(f"[{key}]")
        if not args.keys_only:
            for line in body:
                if line.strip():
                    print(line)
        print()
        hits += 1
        if hits >= args.limit:
            break
    print(f"matches={hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
