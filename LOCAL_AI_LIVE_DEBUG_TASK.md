# 本地 AI 任务：AutoCAD 2024 启动缺失注册项定位

项目：

`F:\Nextcloud\project\AutoCAD 2024.1.9 绿色完整版`

## 当前事实

- `main` 已完成 MVP-A non-live 收口；
- clean live install 已成功执行；
- 安装后 `diff` 为：8653 registry same / 0 change / 0 create，2 junction same，3 shortcuts existing；
- repeat install 幂等；
- `AcadLocation` 与 `AutodeskSharedFolder` 均指向当前 F: 项目；
- 真实启动 `AutoCAD 2024\acad.exe` 仍进入 `AutoCAD 错误中断`；
- 错误正文明确提示“运行 AutoCAD 所需的注册表项被删除或更改”；
- 当前 `reg1 + reg2 + selected reg3 Core allowlist` 仍不足；
- 历史上已补过 `AutoCAD.Application` COM bootstrap，但 clean live 环境证明还不够。

## 目标

**只定位启动时缺失/不正确的最小 Core 注册表依赖。**

优先使用本机已有 Frida 17.5.2；如果你判断更适合，也可以使用官方 Sysinternals Process Monitor，但不要为了工具安装扩大系统改动。

重点抓：

- `acad.exe` 启动阶段对注册表的 Open/Query；
- `NAME NOT FOUND` / `PATH NOT FOUND`；
- 与 AutoCAD / Autodesk / COM / CLSID / TypeLib / ObjectDBX / DwgCommon / Hardcopy / Drawing Check 直接相关的缺失项；
- 当前 `reg3.dli` / `reg4.dli` 中是否存在对应原始 section/value；
- 哪些缺失明显属于 Windows Installer / Edge / Forms / AcSign / Shell 等非 Core 噪音，应排除。

## 边界

本轮只诊断：

- 不修改 Python 产品代码；
- 不写注册表；
- 不导入 reg3/reg4；
- 不改 System32/SysWOW64；
- 不执行旧 CMD；
- 不执行 uninstall；
- 可以启动/关闭**本轮自己启动的 acad.exe PID**；
- 可以在 `evidence-local/mvp-a-live-20260921T1642/local-ai-debug/` 写 trace、脚本、报告。

## 完成标准

返回一个短报告，必须包含：

1. 实际使用的追踪方法；
2. 真实启动 PID / image path；
3. 与启动失败最相关的缺失注册项，按证据强度排序；
4. 每个候选项在 `reg3.dli` / `reg4.dli` 的对应来源；
5. 明确排除的噪音组；
6. 建议的**最小候选补集**，但不要实际写入；
7. 原始证据路径。

如果无法得到可靠 trace，明确写 BLOCKED，不要靠猜测列出大批注册表。

