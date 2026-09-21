from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re

from acad_portable.registry import RegistryDocument, RegistrySection


OLD_PACKAGE_ROOTS = (
    r"D:\00\AutoCAD 2024\AutoCAD 2024",
    r"E:\AutoCAD_2024.1.8\AutoCAD 2024",
)

EXCLUDED_NEEDLES = (
    "edgeupdate",
    "webview2",
    "msedge",
    "acsignext",
    "acsignicon",
    "acsignopt",
    "digital signatures",
    "forms.",
    "fm20",
    "vba enabler",
    "genuine service",
    "\\installer\\",
    "\\package cache\\",
)

AUTOCAD_PROGID_RE = re.compile(
    r"(?i)^HKEY_(?:CURRENT_USER|LOCAL_MACHINE)\\SOFTWARE\\Classes\\"
    r"(?:AutoCAD|acad\.|AcDb|ObjectDBX|AcSm|AcSt|AcTc|AcScene|AcModelDoc)"
)

AUTOCAD_EXT_RE = re.compile(
    r"(?i)^HKEY_(?:CURRENT_USER|LOCAL_MACHINE)\\SOFTWARE\\Classes\\"
    r"\.(?:dwg|dwt|dws|dxf|dst)$"
)

OBJECT_RE = re.compile(
    r"(?i)^(HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\"
    r"(?:CLSID|TypeLib|Interface|AppID)\\[^\\]+)"
)


def section_text(section: RegistrySection) -> str:
    chunks = [section.key]
    for value in section.values:
        chunks.extend((value.name, str(value.data)))
    return "\n".join(chunks)


def object_root(key: str) -> str | None:
    match = OBJECT_RE.match(key)
    return match.group(1) if match else None


def direct_reason(section: RegistrySection) -> str | None:
    key_cf = section.key.casefold()
    text_cf = section_text(section).casefold()

    if any(needle in text_cf for needle in EXCLUDED_NEEDLES):
        return None

    if key_cf.startswith(r"hkey_current_user\software\autodesk\dwgcommon"):
        return "autodesk_dwgcommon"

    if key_cf.startswith("hkey_local_machine\\software\\autodesk\\"):
        if any(
            excluded in key_cf
            for excluded in (
                r"\installer",
                r"\genuine service",
                r"\web services",
                r"\updates",
            )
        ):
            return None
        return "autodesk_machine"

    if AUTOCAD_PROGID_RE.match(section.key):
        return "autocad_progid"

    if AUTOCAD_EXT_RE.match(section.key):
        return "autocad_extension"

    if any(root.casefold() in text_cf for root in OLD_PACKAGE_ROOTS):
        return "package_path_reference"

    return None


def main() -> int:
    path = Path("AutoCAD 2024") / "ACAOE" / "reg3.dli"
    document = RegistryDocument.load(path)

    direct: dict[str, str] = {}
    grouped: dict[str, list[RegistrySection]] = defaultdict(list)
    for section in document.sections:
        root = object_root(section.key)
        if root:
            grouped[root].append(section)
        reason = direct_reason(section)
        if reason:
            direct[section.key] = reason

    # COM-style objects must be kept as an object, not one leaf at a time.
    owned_objects: dict[str, str] = {}
    for root, sections in grouped.items():
        reasons = [direct_reason(section) for section in sections]
        reasons = [reason for reason in reasons if reason]
        if reasons:
            joined = "\n".join(section_text(section).casefold() for section in sections)
            if not any(needle in joined for needle in EXCLUDED_NEEDLES):
                owned_objects[root] = Counter(reasons).most_common(1)[0][0]

    selected: list[tuple[RegistrySection, str]] = []
    for section in document.sections:
        reason = direct.get(section.key)
        root = object_root(section.key)
        if reason:
            selected.append((section, reason))
        elif root and root in owned_objects:
            selected.append((section, f"object:{owned_objects[root]}"))

    reasons = Counter(reason for _section, reason in selected)
    roots = Counter(section.key.split("\\", 1)[0] for section, _reason in selected)
    summary = {
        "source_sections": len(document.sections),
        "selected_sections": len(selected),
        "selected_values": sum(len(section.values) for section, _reason in selected),
        "owned_com_objects": len(owned_objects),
        "reasons": dict(reasons),
        "hive_roots": dict(roots),
        "sample_keys": [section.key for section, _reason in selected[:100]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
