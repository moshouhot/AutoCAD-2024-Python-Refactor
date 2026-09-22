from __future__ import annotations

from acad_portable.registry import PathRebaser, RegistryDocument


def test_registry_parser_handles_strings_dword_delete_and_hex() -> None:
    document = RegistryDocument.parse(
        '''Windows Registry Editor Version 5.00

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\AutoCAD\\R24.3]
@=""
"AcadLocation"="D:\\\\00\\\\AutoCAD 2024\\\\AutoCAD 2024\\\\"
"Flag"=dword:00000001
"Blob"=hex:01,02,03,\\
  04,05
"Expand"=hex(2):25,00,55,00,53,00,45,00,52,00,50,00,52,00,4f,00,46,00,49,00,4c,00,45,00,25,00,5c,00,54,00,65,00,73,00,74,00,00,00
"Multi"=hex(7):6f,00,6e,00,65,00,00,00,74,00,77,00,6f,00,00,00,00,00
"Gone"=-
'''
    )

    assert len(document.sections) == 1
    section = document.sections[0]
    by_name = {value.name: value for value in section.values}
    assert by_name["AcadLocation"].data == "D:\\00\\AutoCAD 2024\\AutoCAD 2024\\"
    assert by_name["Flag"].data == 1
    assert by_name["Blob"].kind == "hex"
    assert "04,05" in str(by_name["Blob"].data)
    assert by_name["Expand"].kind == "expand_sz"
    assert by_name["Expand"].data == r"%USERPROFILE%\Test"
    assert by_name["Multi"].kind == "multi_sz"
    assert by_name["Multi"].data == ["one", "two"]
    assert by_name["Gone"].kind == "delete"


def test_path_rebaser_is_case_insensitive_and_prefers_longest_mapping() -> None:
    rebaser = PathRebaser(
        [
            (r"D:\OLD", r"F:\NEW"),
            (r"D:\OLD\AutoCAD 2024", r"F:\Portable\AutoCAD 2024"),
        ]
    )

    value = r"d:\old\AutoCAD 2024\acad.exe"
    assert rebaser.apply(value) == r"F:\Portable\AutoCAD 2024\acad.exe"


def test_path_rebaser_respects_directory_boundary() -> None:
    rebaser = PathRebaser([(r"C:\Users\Administrator", r"C:\Users\Administrator.DESKTOP-1")])
    assert rebaser.apply(r"C:\Users\Administrator\AppData") == r"C:\Users\Administrator.DESKTOP-1\AppData"
    assert rebaser.apply(r"C:\Users\Administrator.DESKTOP-1\AppData") == r"C:\Users\Administrator.DESKTOP-1\AppData"


def test_first_string_ignores_deleted_sections() -> None:
    document = RegistryDocument.parse(
        '''Windows Registry Editor Version 5.00

[-HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\AutoCAD\\R24.3]
"AcadLocation"="D:\\Deleted"

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Autodesk\\AutoCAD\\R24.3]
"AcadLocation"="F:\\Active"
'''
    )

    assert document.first_string("AcadLocation") == r"F:\Active"

