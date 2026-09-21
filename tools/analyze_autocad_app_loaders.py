from __future__ import annotations

import argparse
import codecs
import json
import re
from collections import Counter
from pathlib import Path


SECTION_RE = re.compile(r"^\[(?P<key>[^\]]+)\]$")
LOADER_RE = re.compile(r'^"LOADER"="(?P<value>.*)"$', re.IGNORECASE)
ACAD_LOCATION_RE = re.compile(r'^"AcadLocation"="(?P<value>.*)"$', re.IGNORECASE)


def decode(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16")
    return data.decode("gb18030", errors="replace")


def unescape_reg_string(value: str) -> str:
    return value.replace("\\\\", "\\")


def classify(loader: str) -> str:
    lowered = loader.lower()
    if "://" in loader:
        return "virtual_protocol"
    if ":\\" not in loader:
        return "relative"
    if "\\autodesk\\applicationplugins\\" in lowered:
        return "application_plugins"
    if "\\common files\\autodesk shared\\" in lowered:
        return "autodesk_shared"
    if "\\windows\\" in lowered:
        return "windows"
    return "absolute_other"


def infer_captured_root(loaders: list[str]) -> str | None:
    candidates = []
    for loader in loaders:
        lowered = loader.lower()
        marker = "\\autocad 2024\\"
        pos = lowered.find(marker)
        if pos >= 0:
            candidates.append(loader[: pos + len(marker)])
    if not candidates:
        return None
    return Counter(candidates).most_common(1)[0][0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reg2", type=Path, required=True)
    parser.add_argument("--autocad-root", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    text = decode(args.reg2)
    current_key = ""
    records: list[dict] = []
    all_loaders: list[str] = []
    acad_location: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        section = SECTION_RE.match(line)
        if section:
            current_key = section.group("key")
            continue
        location_match = ACAD_LOCATION_RE.match(line)
        if location_match and acad_location is None:
            acad_location = unescape_reg_string(location_match.group("value")).rstrip("\\/") + "\\"

        loader_match = LOADER_RE.match(line)
        if not loader_match or "\\Applications\\" not in current_key:
            continue
        loader = unescape_reg_string(loader_match.group("value"))
        all_loaders.append(loader)
        records.append({"key": current_key, "loader": loader})

    captured_root = acad_location or infer_captured_root(all_loaders)
    stats = Counter()
    missing = []

    for record in records:
        loader = record["loader"]
        kind = classify(loader)
        record["kind"] = kind
        stats[kind] += 1

        candidate: Path | None = None
        if kind == "relative":
            candidate = args.autocad_root / loader
        elif captured_root and loader.lower().startswith(captured_root.lower()):
            rel = loader[len(captured_root) :].lstrip("\\/")
            candidate = args.autocad_root / Path(rel)
            record["kind"] = "autocad_root"
            stats[kind] -= 1
            stats["autocad_root"] += 1

        if candidate is not None:
            record["candidate"] = str(candidate)
            record["exists"] = candidate.exists()
            if not record["exists"]:
                missing.append(record)

    result = {
        "application_loader_count": len(records),
        "captured_root": captured_root,
        "kinds": dict(stats),
        "mapped_missing_count": len(missing),
        "mapped_missing": missing,
        "records": records,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"loaders={len(records)} captured_root={captured_root!r}")
    print("kinds=" + json.dumps(dict(stats), ensure_ascii=False, sort_keys=True))
    print(f"mapped_missing={len(missing)}")
    for item in missing[:50]:
        print(f"MISSING {item['key']} -> {item['loader']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
