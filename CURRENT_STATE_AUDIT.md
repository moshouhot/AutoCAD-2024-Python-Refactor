# Current Live State Audit

> 2026-09-21，只读审计。本文档描述当前机器状态，不执行任何系统写入。

## 1. 当前结论

当前机器**不能**作为 F: 新项目 Core MVP 的可信验收基线。

原因不是 Python planner 没有做路径 rebasing，而是：

1. Python installer journal 明确记录当时安装值指向 F: 新项目；
2. 当前真实注册表中大量对应值已经被改回 D: 的既有 AutoCAD 2024 环境；
3. 少量用户配置还指向 E: 的历史 AutoCAD 2024.1.8 环境；
4. 因此当前 live registry 是一个**后续发生过外部写入/环境漂移**的混合状态。

在来源尚未完全追溯前，禁止把当前 `status=complete` 解读成“最新 Python Core 已通过真机验收”。

---

## 2. Python journal 事实

当前状态文件：

`AutoCAD 2024/ACAOE/.python-installer-state.json`

只读检查：

- `status = complete`
- journal registry values = **8656**
- created registry keys = **2891**
- created junctions = **2**
- shortcuts = **3**
- `install_payload.autocad_root` = F: 新项目路径

抽样 journal 明确记录：

- `AutodeskSharedFolder` 安装值为 F:
- `Applications\AcadApp\LOADER` 安装值为 F:

因此可以排除“当时 planner 根本没有把 D: 改成 F:”这一解释。

---

## 3. 当前真实注册表与 journal 的漂移

使用只读工具：

`python tools/analyze_live_state_drift.py`

结果：

- journal values = **8656**
- same = **8378**
- changed = **278**
- missing = **0**

278 个 changed 中：

- **267**：journal 为 F:，当前变为 D:
- **1**：journal 为 F:，当前变为其他盘（E:）
- **10**：其他差异，例如用户 Temp 的长路径/8.3 短路径变化

按 hive：

- HKCU changed = **17**
- HKLM changed = **261**

这不是随机几个运行时值漂移，而是大规模产品路径被重写。

---

## 4. 当前注册表主路径

当前只读查询：

`HKLM\SOFTWARE\Autodesk\AutoCAD\R24.3\ACAD-7101:804\AcadLocation`

实际值：

`D:\Program Files\Autodesk\AutoCAD 2024.1.9\AutoCAD 2024\`

抽样还包括：

- `HKLM ... Applications\AcadApp\LOADER` → D:
- `HKCU ... AutodeskSharedFolder` → D:
- `SupportFolder / ACADDRV / ACADHELP` → D:
- `ACAD / ColorBookLocation` 中还出现 E:\AutoCAD_2024.1.8

所以当前机器同时存在 F: journal、D: 当前产品注册和 E: 历史用户配置痕迹。

---

## 5. 最新候选代码状态

当前 HEAD 的只读结果：

### Tests

`python -m pytest -q`

→ **36 passed**

### Plan

`python -m acad_portable plan`

→

- operations = **11,554**
- warnings = **0**
- audit findings = **0**

旧文档中的 `11,305` 已过期。

### Current diff

`python -m acad_portable diff --json`

当前 latest-plan 对 live registry：

- same = 8375
- change = **278**
- create = 0
- keys_create = 0
- Junction same = 2
- shortcut existing = 3

注意：plan diff 与 journal drift 工具的 same 数略有不同，是因为最新 planner 已在 journal 之后继续调整了 Core 范围；共同事实是 **278 个当前值需要改变**。

---

## 6. 产品/代码判断

当前证据支持：

### 已证明

- Python planner 能生成 F: rebased registry 值；
- 至少一次真实 apply 曾把 F: 值写入 journal；
- rollback/journal 机制此前有真实失败回滚证据；
- 当前候选代码 31 tests PASS；
- 当前候选 plan 没有 System32/SysWOW64 写入；
- 当前候选 plan 仍通过自身 audit gate。

### 未证明

- F: Core 目前能稳定启动 AutoCAD；
- 当前 `status=complete` 对应的 live system 仍保持该次安装结果；
- 278 个值是谁、在什么时间、通过什么操作改回 D:/E:；
- 最新 11,554-operation plan 已经过新的真机验收。

### 当前状态

`MVP-A Core = CANDIDATE / LIVE BLOCKED`

不是 PASS，也不是因为 Python 静态实现已经失败，而是当前 live 环境已失去单一来源基线。

---

## 7. 当前操作边界

在完成环境基线决策前：

- 不执行 `install --apply`；
- 不执行 `uninstall --apply`；
- 不运行旧 CMD 安装/卸载；
- 不通过覆盖注册表来“试试看”；
- 不进入 VBA / Forms / WebView2 / AcSign。

允许继续：

- 只读 registry / file / package 分析；
- Python 源码审计；
- 单元测试；
- plan / diff / status；
- 文档和 GitHub 第三方审计。

---

## 8. 下一步

先把现有 Python 视为**候选实现**，按新的产品路线重新审核：

1. Phase 1 事实是否完整；
2. `PYTHON_FUNCTIONAL_REQUIREMENTS.md` 的产品取舍是否成立；
3. Core planner 是否只实现被批准的职责；
4. 哪些 registry 状态真的是安装契约，哪些是运行时/用户状态；
5. 再决定新的独立 live 验收环境，而不是直接修当前 D:/E:/F: 混合状态。

