from __future__ import annotations

import argparse
import codecs
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


SECTION_RE = re.compile(r"^\[(?P<deleted>-)?(?P<key>[^\]]+)\]$")
VALUE_RE = re.compile(r'^(?:@|"[^"]*")\s*=')
FILE_EXT_RE = re.compile(r"(?i)\.(?:dll|exe|arx|crx|dbx|cpl|tlb|olb|ocx|lnk)(?:$|[\s,;])")


CATEGORY_RULES = [
    ("vba", ("acadvba", "acvba", "vba enabler", "vbaserver")),
    ("forms2", ("forms.", "fm20", "microsoft forms", "{0d452ee1", "{8bd21d")),
    ("webview2", ("edgeupdate", "webview2", "ebwebview", "msedgewebview2")),
    ("acsign", ("acsign", "digital signatures", "propertysheethandlers")),
    ("file_association", ("classes\\.dwg", "autocad.drawing", "shellcommon", "openwith")),
    ("shell_extension", ("shellex", "shell extensions", "approved")),
    ("property_system", ("propertysystem", "propertyhandler", "progid")),
    ("installer_metadata", ("installer\\", "uninstall\\", "upgradecodes", "userdata\\s-1-5-18\\products")),
    ("autocad_core", ("autodesk\\autocad", "objectdbx", "hardcopy", "drawing check")),
]


def decode_registry(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"

    for encoding in ("gb18030", "utf-8"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def classify(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name, needles in CATEGORY_RULES if any(n in lowered for n in needles)]


def normalize_ref(ref: str) -> str:
    return ref.strip().strip('"').replace("\\\\", "\\")


def extract_refs(line: str) -> list[str]:
    # Registry paths are overwhelmingly quoted. Splitting first avoids a
    # pathological backtracking regex on very large exported value lines.
    refs: list[str] = []
    parts = line.split('"')
    for index in range(1, len(parts), 2):
        candidate = parts[index].strip()
        if candidate and FILE_EXT_RE.search(candidate + " "):
            refs.append(normalize_ref(candidate))
    return refs


def parse_template(path: Path) -> dict:
    text, encoding = decode_registry(path)
    sections: list[dict] = []
    current: dict | None = None

    for raw in text.splitlines():
        line = raw.strip()
        match = SECTION_RE.match(line)
        if match:
            key = match.group("key")
            current = {
                "key": key,
                "deleted": bool(match.group("deleted")),
                "value_count": 0,
                "categories": classify(key),
                "file_refs": [],
            }
            sections.append(current)
            continue

        if current is None or not line or line.startswith(";"):
            continue

        if VALUE_RE.match(line):
            current["value_count"] += 1
        for ref in extract_refs(line):
            normalized = normalize_ref(ref)
            if normalized not in current["file_refs"]:
                current["file_refs"].append(normalized)
        for category in classify(line):
            if category not in current["categories"]:
                current["categories"].append(category)

    categories = Counter()
    roots = Counter()
    file_refs = set()
    deleted_sections = 0
    values = 0
    categorized_examples: dict[str, list[str]] = defaultdict(list)

    for section in sections:
        values += section["value_count"]
        deleted_sections += int(section["deleted"])
        root = section["key"].split("\\", 1)[0]
        roots[root] += 1
        file_refs.update(section["file_refs"])
        for category in section["categories"]:
            categories[category] += 1
            examples = categorized_examples[category]
            if len(examples) < 8 and section["key"] not in examples:
                examples.append(section["key"])

    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "encoding": encoding,
        "section_count": len(sections),
        "deleted_section_count": deleted_sections,
        "value_count": values,
        "roots": dict(roots),
        "categories": dict(categories),
        "category_examples": dict(categorized_examples),
        "file_refs": sorted(file_refs, key=str.lower),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    files = sorted(args.directory.glob("*.dli"), key=lambda p: p.name.lower())
    result = {
        "source_directory": str(args.directory),
        "template_count": len(files),
        "templates": [parse_template(path) for path in files],
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in result["templates"]:
        cats = ",".join(sorted(item["categories"])) or "-"
        print(
            f"{item['file']}: sections={item['section_count']} "
            f"values={item['value_count']} deleted={item['deleted_section_count']} "
            f"refs={len(item['file_refs'])} categories={cats}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
