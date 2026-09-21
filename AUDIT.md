# Third-party Audit Guide

本仓库采用“**先理解旧 CMD，再重新设计 Python**”路线。

第三方审计不要用“Python 是否逐行复制 CMD”作为标准，而应检查：

1. 我们是否正确理解旧安装器的重要产品职责；
2. `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 的取舍是否自洽；
3. Python 实现是否满足新的功能契约；
4. 是否把历史机器状态、危险副作用或未部署依赖错误带入 Core MVP；
5. 测试是否真正独立于实现。

## 1. 建议阅读顺序

1. `prd.md`
2. `CMD_FUNCTIONAL_SPEC.md`
3. `REGISTRY_TEMPLATE_SPEC.md`
4. `PAYLOAD_ARCHIVE_SPEC.md`
5. `RUNTIME_FEATURE_SPEC.md`
6. `PYTHON_FUNCTIONAL_REQUIREMENTS.md`
7. `DESIGN.md`
8. `IMPLEMENTATION_PLAN.md`
9. `ACCEPTANCE.md`
10. `src/acad_portable/`
11. `tests/`

## 2. 当前 Core MVP 重要边界

Core 允许：

- `reg1.dli` 中受 allowlist 约束的 HKCU AutoCAD 状态；
- `reg2.dli` 中受 allowlist 约束的 HKLM AutoCAD 产品/Application 状态；
- 显式路径 rebasing；
- AppData / LocalAppData CHS Junction；
- desktop / plotter / plot-style wizard shortcut；
- Python 自有 install-state journal。

Core 明确不包含：

- `reg3.dli` 全量导入；
- `regedge.dli`；
- `vba.dli`；
- `unreg.dli`；
- `AcadVBA` loader；
- HKCU 历史第三方插件 `Applications / AssemblyMap / Loaded` 状态；
- System32 / SysWOW64 写入；
- WebView2 伪安装；
- AcSign Windows Shell；
- taskbar pin；
- CMD 338–514 制包工具链。

## 3. 当前自动门禁

本地和 CI 至少应运行：

```text
python -m pytest -q
```

当前真实包只读/非 live 基线：

- plan operations：11,305
- plan warnings：0
- independent plan audit findings：0
- FakeWindows 两次 apply：幂等
- Windows preflight：`.NET 4.7+` 满足
- Auto-load 静态链路：PASS
- Windows 临时目录 Junction / Shortcut：PASS

## 4. 重点审计问题

### Registry parser

- `.reg/.dli` multiline hex 是否正确连接；
- `REG_EXPAND_SZ` 是否正确 UTF-16LE 解码；
- 未支持 registry type 是否会偷偷进入真实执行层。

### Path rebasing

- 目录边界匹配是否避免前缀误替换；
- 是否仍可能留下历史包路径；
- 当前用户路径和历史用户名相似时是否会重复改写。

### Core allowlist

- 是否可能穿透到 AutoCAD 之外的 HKLM/HKCU 系统树；
- `AcadVBA` 是否可能在 Core 阶段被提前注册；
- 用户历史插件状态是否可能重新进入 plan。

### RealWindowsAdapter

- install journal 是否在重复安装后仍保留第一次 before-state；
- uninstall 是否可能覆盖安装后被第三方修改的值；
- dangling junction 是否会被误认为“路径不存在”；
- shortcut 恢复逻辑是否保护安装后外部修改。

### Test oracle

不要把“planner 自己认为正确”当成唯一验收。

重点关注：

- `validate_core_plan` 是否与 planner 有独立约束；
- 真实包 smoke test；
- Windows 临时目录集成；
- 后续真实 AutoCAD GUI / LSP 验收。

## 5. 尚未完成

当前不能宣称产品完成：

- 尚未执行 Core `install --apply`；
- 尚未启动真实 AutoCAD 做 GUI/命令验收；
- 尚未验证 `0加载应用程序` 的真实启动时加载；
- VBA 属于后续 MVP-B；
- 公开 GitHub 仓库尚待创建并运行远端 CI / CodeQL。

第三方审计应允许结论为 `BLOCKED` / `FAIL`，不得因为当前单元测试全绿而直接认定产品完成。

## 6. 主审计补充：volatile registry state

在真实 Core apply 后做只读 `diff --json` 时，发现旧 `reg1.dli` 快照中的两个运行时值会被 AutoCAD 自己改变：

- `LastRunTime`
- `MiniDump\SessionStartCount`

它们属于“程序运行结果”，不是“安装契约”。如果继续由 installer 管理，重复安装会把 AutoCAD 自己的新状态写回旧快照值。

因此 Core planner 已明确排除这两个值，并增加回归测试，确保不会因为整个 `MiniDump` section 被排除而顺带丢掉其他未知值。

修复后真实只读 diff：

- registry same = 8526
- registry change = 0
- registry create = 0
- Junction same = 2
- shortcut existing = 3

这条经验应继续用于后续最小化：凡是从抓包模板进入 plan 的值，都要区分“安装状态”与“程序运行/用户活动产生的状态”。
