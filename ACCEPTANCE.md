# Acceptance

## A. Phase 1 / 设计门禁

- [x] CMD 514 行控制结构已拆解。
- [x] 安装/卸载/备份/恢复与制包工具链已分离。
- [x] 7 个 `.dli` 已统计和职责分类。
- [x] 5 个关键归档已只读列目录。
- [x] CHS 当前状态与出厂基线已区分。
- [x] 279 个 AutoCAD Application loader 已做包内覆盖验证；文件型缺失 0。
- [x] Python MVP 产品边界已写入 `PYTHON_FUNCTIONAL_REQUIREMENTS.md`。

## B. P1 Package Model

- [ ] 能从项目根发现当前 AutoCAD 包。
- [ ] `acad.exe` / ACAOE / CHS / legacy templates 缺失时给出明确错误。
- [ ] 能正确读取 GB18030/UTF-16 legacy 输入。
- [ ] `status` 不修改系统。

## C. P2 Registry plan

- [ ] 正确解析 `reg1.dli` / `reg2.dli`。
- [ ] 只允许预期 HKCU/HKLM AutoCAD roots。
- [ ] 所有 legacy AcadLocation 路径都能转换为当前 root。
- [ ] plan 中不存在旧 `D:\00\AutoCAD 2024\...` 残留。
- [ ] Core plan 不包含 `reg3.dli` / `regedge.dli` / `vba.dli` / `unreg.dli` 全量导入。
- [ ] Core plan 不包含 System32/SysWOW64 写入。

## D. P3 Fake install

- [ ] 两个 CHS Junction 指向 `ACAOE/CHS`。
- [ ] 普通安装不重置当前 CHS。
- [ ] desktop shortcut 指向当前 `acad.exe /nologo`。
- [ ] wizard shortcut 目标正确。
- [ ] auto-load 链路存在且可被静态验证。
- [ ] 第二次执行生成等价目标状态。
- [ ] uninstall 只删除本工具拥有的状态。

## E. Non-live regression

- [ ] 全量 pytest PASS。
- [ ] 所有静态分析工具可重复运行。
- [ ] `git status` 只含预期源码/文档变化。
- [ ] 未执行真实 CMD 安装器。
- [ ] 未写 System32/SysWOW64。

## F. MVP-A 真机验收

- [ ] Python Core install 成功。
- [ ] AutoCAD 2024 启动到可操作状态。
- [ ] 运行中 image path 为当前绿色包 `acad.exe`。
- [ ] 关键 AutoCAD 命令可执行。
- [ ] AppData / LocalAppData CHS 均解析到正确目标。
- [ ] 当前 CHS 用户状态未被普通安装 reset。
- [ ] desktop shortcut 可正常启动。
- [ ] `0加载应用程序` 测试 LSP 自动加载成功。
- [ ] 重复 install 可用。
- [ ] Core uninstall 不进行大范围共享状态清理。

## G. VBA（MVP-B）

Core MVP-A 通过之前不进入。

- [ ] `VBALOAD`
- [ ] `VBAIDE`
- [ ] 普通宏执行
- [ ] 若承诺 Forms：UserForm 显示、控件和事件

## 最终状态规则

单元测试 PASS 不等于真机 PASS；真机 PASS 也不等于第三方审计 PASS。

最终交付至少需要：

1. 实现验证；
2. 非 live 回归；
3. 真机功能验收；
4. 独立审计。
