from __future__ import annotations

import argparse
from pathlib import Path

from acad_portable.registry import RegistryDocument


RUNTIME_MARKERS = (
    "vba7.1",
    "vbe7.dll",
    "vbeui.dll",
    "vbeuires.dll",
    "apc71.dll",
    "apc71itl.dll",
    "vbe7intl.dll",
    "vbeuiintl.dll",
    "vbe6ext.olb",
)

RUNTIME_TYPELIB_GUIDS = (
    "{000204EF-0000-0000-C000-000000000046}",
    "{0002E157-0000-0000-C000-000000000046}",
    "{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}",
    "{A6128B1F-4A3A-40B6-B5CE-5FE8DE3D88E9}",
)

RUNTIME_PREFIXES = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk\AutoCAD\R24.3\AutoCAD 2024 VBA Enabler",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{2F967C44-B1F0-485E-957C-97538BCAD2DE}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{943FA227-E90C-47DA-987B-C4DD13E48CB4}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{95C9DCCD-A44A-4034-84BB-D7912DF5711F}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\{CFE9F29B-E1B6-4240-AED7-360846769314}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{000204EF-0000-0000-C000-000000000046}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{0002E157-0000-0000-C000-000000000046}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\TypeLib\{A6128B1F-4A3A-40B6-B5CE-5FE8DE3D88E9}",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\VBA",
)


def under_prefix(key: str, prefix: str) -> bool:
    key_cf = key.rstrip("\\").casefold()
    prefix_cf = prefix.rstrip("\\").casefold()
    return key_cf == prefix_cf or key_cf.startswith(prefix_cf + "\\")


def is_installer_key(key: str) -> bool:
    lowered = key.casefold()
    return "\\installer\\" in lowered or "\\classes\\installer\\" in lowered


def is_forms_text(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in ("fm20", "forms.", "microsoft forms", "msforms"))


def section_text(section) -> str:
    parts = [section.key]
    for value in section.values:
        parts.extend((value.name, str(value.data)))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    document = RegistryDocument.load(args.path)
    selected = []
    for section in document.sections:
        if section.deleted or is_installer_key(section.key):
            continue
        text = section_text(section)
        lowered = text.casefold()
        if is_forms_text(text):
            continue
        if "autocad 2024 vba enabler" in section.key.casefold() or any(
            marker in lowered for marker in RUNTIME_MARKERS
        ):
            selected.append(section)

    print(f"candidates={len(selected)}")
    for section in selected:
        print(f"[{section.key}]")
        for value in section.values:
            print(f"  {value.name!r} {value.kind} {value.data!r}")

    expanded = [
        section
        for section in document.sections
        if not section.deleted and any(under_prefix(section.key, prefix) for prefix in RUNTIME_PREFIXES)
    ]
    print(f"expanded={len(expanded)}")
    kinds = sorted({value.kind for section in expanded for value in section.values})
    print(f"kinds={kinds}")
    for section in expanded:
        print(f"EXPANDED [{section.key}]")
        for value in section.values:
            print(f"  {value.name!r} {value.kind} {value.data!r}")

    progid_prefixes = sorted(
        {
            section.key
            for section in document.sections
            if section.key.casefold().startswith(
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Classes\MSAPC.".casefold()
            )
        }
    )
    progid_roots = sorted(
        {
            "\\".join(key.split("\\")[:5])
            for key in progid_prefixes
        }
    )

    interface_roots: set[str] = set()
    for section in document.sections:
        key_cf = section.key.casefold()
        if not key_cf.startswith(
            "HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\Interface\\".casefold()
        ):
            continue
        text_cf = section_text(section).casefold()
        if any(guid.casefold() in text_cf for guid in RUNTIME_TYPELIB_GUIDS):
            parts = section.key.split("\\")
            if len(parts) >= 5:
                interface_roots.add("\\".join(parts[:5]))

    closure_prefixes = tuple(progid_roots) + tuple(sorted(interface_roots))
    closure = [
        section
        for section in document.sections
        if not section.deleted
        and any(under_prefix(section.key, prefix) for prefix in closure_prefixes)
    ]
    print(f"progid_roots={len(progid_roots)}")
    for prefix in progid_roots:
        print(f"PROGID_ROOT {prefix}")
    print(f"interface_roots={len(interface_roots)}")
    for prefix in sorted(interface_roots):
        print(f"INTERFACE_ROOT {prefix}")
    print(f"closure_sections={len(closure)}")
    closure_kinds = sorted({value.kind for section in closure for value in section.values})
    print(f"closure_kinds={closure_kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
