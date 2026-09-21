# Core MVP Live Acceptance

> 这是给“本地 AI / 真机操作员”的窄任务说明。它只负责执行已经审查好的 Core MVP 真机验收，不做架构设计、不改产品范围、不自行进入 VBA/WebView2/AcSign。

## 1. 前置状态

项目：

`F:\Nextcloud\project\AutoCAD 2024.1.9 绿色完整版`

在执行真实安装前，必须先保存：

- `git status --short`
- `git rev-parse HEAD`
- `python -m pytest -q`
- `python -m acad_portable --root . status --json`
- `python -m acad_portable --root . plan --json`

要求：

- pytest PASS；
- plan warnings = 0；
- audit findings = 0；
- Windows/admin/.NET preflight PASS。

如果任何一项不满足，STOP，不要 `--apply`。

## 2. 本轮授权范围

允许 Core MVP 做：

- AutoCAD 自有 HKCU/HKLM Core registry 写入；
- AppData / LocalAppData 两个 CHS Junction；
- desktop AutoCAD shortcut；
- CHS 中两个 wizard shortcuts；
- 写 Python installer state。

本轮禁止：

- System32 / SysWOW64；
- WebView2；
- AcSign Shell；
- VBA / FM20；
- `reg3.dli` 全量导入；
- `regedge.dli`；
- `vba.dli`；
- `unreg.dli`；
- 旧 CMD / EXE 安装器；
- D:/F: 目录重命名或 junction 替换实验。

发现新问题时记录证据并返回，不要自主扩大范围。

## 3. Apply

只有前置门禁全部 PASS 后执行：

```text
python -m acad_portable --root . install --apply
```

记录：

- 完整 stdout/stderr；
- exit code；
- `.python-installer-state.json` 是否生成；
- `status --json` 中 installer state。

不要手工修注册表来“帮助通过”。

## 4. 真机 Core 验收

### A. AutoCAD 启动

启动当前项目：

`AutoCAD 2024\acad.exe`

确认：

- 进入可操作界面；
- 不是秒退；
- 运行中 image path 正是本项目 `acad.exe`；
- 能执行至少一个基础命令并正常返回。

### B. CHS Junction

验证：

- `%LOCALAPPDATA%\Autodesk\AutoCAD 2024\R24.3\chs`
- `%APPDATA%\Autodesk\AutoCAD 2024\R24.3\chs`

均解析到：

`AutoCAD 2024\ACAOE\CHS`

且普通安装没有把当前 CHS reset 为 `guanfang.dll` 基线。

### C. Desktop shortcut

确认快捷方式：

- target 是本项目 `acad.exe`；
- arguments 是 `/nologo`；
- 可以正常启动本项目 AutoCAD。

### D. Auto-load

在 `0加载应用程序` 放一个**最小、可识别且可删除的测试 LSP**，例如只设置一个唯一系统变量/打印唯一标记，不做其他系统修改。

重启 AutoCAD，证明：

- 测试 LSP 自动加载；
- 证据能区分“自动加载成功”和“人工 LOAD 成功”。

测试结束删除该测试 LSP。

## 5. Repeat install

关闭 AutoCAD 后再次执行：

```text
python -m acad_portable --root . install --apply
```

要求：

- 成功；
- 当前 CHS 不被 reset；
- 两个 Junction 仍正确；
- shortcut 正常；
- installer journal 的原始 before-state 没有被第二次 install 覆盖。

## 6. Uninstall 验收

确认 AutoCAD 已退出后执行：

```text
python -m acad_portable --root . uninstall --apply
```

要求：

- 只恢复/删除 Python installer 管理的状态；
- 两个由本工具创建的 Junction 被移除；
- Python 创建的 shortcut 被删除/恢复旧版本；
- 不执行 System32 / WebView2 / Forms / AcSign 清理；
- 若有 external-change conflict，必须保留外部状态并如实报告，不得强制清理。

## 7. 最终报告

只报告证据，不给自己做最终认证。至少返回：

1. HEAD SHA；
2. pytest 结果；
3. preflight / plan 结果；
4. 第一次 apply exit code；
5. AutoCAD 是否真实进入可操作界面；
6. 运行中 image path；
7. 两个 CHS Junction 实际目标；
8. desktop shortcut 实际目标/参数；
9. Auto-load 测试证据；
10. 第二次 install 结果；
11. uninstall 结果与 conflicts；
12. 是否有任何超出授权范围的写入（预期应为否）。

最终 PASS / FAIL 由主审计者根据证据判断。
