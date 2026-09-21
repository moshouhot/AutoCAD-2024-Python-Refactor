# MVP-A Live Acceptance Report

> 2026-09-21，clean-host final candidate evidence.

## Candidate

- branch: `mvp-a/live-acceptance`
- implementation commit: `a46c33b` (`fix: add traced AcadObject core registration`)
- pytest: **40 passed**
- plan: **11,559 operations / 0 warnings / 0 audit findings**

## Clean ownership baseline

- installer state was absent;
- HKLM AutoCAD 2024 / R24.3 product root was absent;
- no `acad.exe` process was running;
- read-only diff before the final cycle was baseline-like: `1 same / 8655 create / 2880 keys_create`;
- HKCU was allowed to retain runtime/external-plugin state created by previous AutoCAD execution because owned uninstall intentionally does not scrub non-journal state;
- preflight Windows/admin/.NET/autoload-static checks passed.

## Fresh install

`python -m acad_portable install --apply`

- result: PASS
- actual operations: **11,558**
- post-install diff: registry **8656 same / 0 change / 0 create**
- junctions: **2 same**
- shortcuts: **3 existing**
- conflicts: 0

Final journal recorded:

- created registry keys: **2880**
- registry values: **8656**
- junctions: **2**
- shortcuts: **3**

Both AppData and LocalAppData CHS junctions targeted the current package `AutoCAD 2024\ACAOE\CHS`.

## Startup blocker and minimal fix

Frida trace showed `acad.exe` calling `CheckCOMServerRelativePaths -> InstallUserData` and failing to open:

`HKCR\CLSID\{E89B39BB-5AE4-4C52-9011-B70FC663F249}\InProcServer32`

with `rc=2`.

The matching `reg3.dli` subtree is exactly:

- CLSID default: `AcadObject`
- `InProcServer32`: `axdb.dll`
- `ThreadingModel`: `Apartment`

Controlled A/B:

- CLSID present -> `Autodesk AutoCAD 2024 - [Drawing1.dwg]`
- CLSID removed -> `AutoCAD 错误中断`

No adjacent CLSID or whole-reg3 import was added.

## Real AutoCAD acceptance

Final candidate launch:

- real image: current F: project `AutoCAD 2024\acad.exe`
- main window: `Autodesk AutoCAD 2024 - [Drawing1.dwg]`
- no `AutoCAD 错误中断`
- COM ROT: `AutoCAD.Application.24` available
- command probe: `USERR1 0 -> 12.345 -> 0`

Auto-load:

- a temporary unique LSP was placed in `0加载应用程序`;
- normal AutoCAD startup automatically created `__mvp_a_autoload_marker.txt`;
- the probe LSP and marker were deleted after the test.

## Runtime drift and repeat install

After normal AutoCAD execution, read-only diff showed 48 changed planned HKCU GPU/Certification values and 1 planned value absent. This is runtime state written by AutoCAD itself, not a startup blocker.

After closing AutoCAD, a second `install --apply`:

- PASS
- post-repeat diff returned to **8656 same / 0 change / 0 create**
- journal cardinality remained stable.

## Owned uninstall

`python -m acad_portable uninstall --apply`

Result:

- registry restored: **1**
- registry removed: **8655**
- shortcuts restored: **2**
- shortcuts removed: **1**
- junctions removed: **2**
- conflicts: **0**

Post-uninstall:

- installer state absent;
- `AcadObject` CLSID absent;
- HKLM `SOFTWARE\Autodesk\AutoCAD\R24.3` absent;
- plan diff returned to the same baseline-like `1 same / 8655 create / 2880 keys_create`;
- HKCU retained **36 keys / 80 values** written by AutoCAD runtime and external ApplicationPlugins (GPU identity, `Loaded`, external `Applications`, profile/runtime state). These were not owned by the Python journal and were intentionally preserved by owned uninstall.

## Verdict before third-party review

`MVP-A CORE LIVE FUNCTIONAL PASS`

Not yet claimed:

- final third-party source/evidence audit for this branch;
- per-group minimality proof for every existing selected reg3 Core candidate;
- separate direct-click test of the desktop shortcut;
- VBA (MVP-B).
