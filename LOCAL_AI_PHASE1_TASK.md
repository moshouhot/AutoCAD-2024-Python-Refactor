# 本地 AI 任务：Phase 1 批量资源盘点

项目：

`F:\Nextcloud\project\AutoCAD 2024.1.9 绿色完整版`

## 目标

只做**只读批量盘点**，为主 AI 的 `CMD_FUNCTIONAL_SPEC.md` 提供原始事实。

不要做产品判断，不要改 Python，不要运行安装器，不要修改 Windows。

## 扫描对象

优先顺序：

1. `AutoCAD 2024\ACAOE\reg1.dli`
2. `reg2.dli`
3. `reg3.dli`
4. `reg4.dli`
5. `regedge.dli`
6. `vba.dli`
7. `unreg.dli`
8. `default.dll`
9. `guanfang.dll`
10. `Tohomedrive.dll`
11. `app\VBA.dll`
12. `app\auedgewebview.dll`

## 对 `.dli` 输出

每个文件至少统计：

- 总 registry key/value 数；
- HKCU / HKLM / Classes / Installer 等主要根分布；
- `AcadLocation`、AutoCAD 产品根、Profiles、Shell、COM/CLSID、TypeLib、VBA、WebView2 等主题；
- 所有引用磁盘绝对路径的值；
- 所有指向 DLL/EXE/ARX/OLB/TLB 的路径；
- 明显依赖其他归档成员的注册项；
- 不要只贴全文，按主题整理并保留可追溯来源。

## 对归档输出

只读列出成员，不解包到系统目录。

每个归档至少输出：

- 成员总数；
- 目录结构；
- 目标看起来落到 Program Files / Common Files / Windows / System32 / SysWOW64 / 用户目录的成员；
- EXE/DLL/ARX/TLB/OLB/CPL 等关键文件；
- 和 `.dli` 注册表路径能对应上的成员；
- 无法解释用途的成员。

## 重点关联

请建立以下“注册 → 文件”映射：

- VBA / AcadVBA → `VBA.dll`
- Forms / FM20 → `VBA.dll` 或 `Tohomedrive.dll`
- AcSign / Shell Extension → `Tohomedrive.dll`
- EdgeUpdate / EBWebView → `auedgewebview.dll`
- CHS/default registry → `guanfang.dll` / `default.dll`

## 证据输出

在项目下新建：

`analysis/local-ai-phase1/`

建议至少包含：

- `DLI_SUMMARY.md`
- `ARCHIVE_SUMMARY.md`
- `REGISTRY_FILE_MAP.md`
- `UNKNOWN_ITEMS.md`
- 原始机器可读 JSON/CSV（如有）

不要修改已有冻结 evidence；只写上述新目录。

## 完成标准

完成后只汇报：

- 扫描文件清单；
- 关键计数；
- 最重要的 10~20 条可证明事实；
- UNKNOWN；
- 输出文件路径。

不要给出“Python 应该如何实现”的最终建议；由主 AI 根据这些证据继续 Phase 1/2。

