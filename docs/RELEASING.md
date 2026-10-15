# GitHub 发布指南

仓库地址：<https://github.com/206069780/process-panel>。

源码和文档使用 Git 管理；生成的 EXE 使用 GitHub Releases 分发。当前 EXE 约 201 MiB，超过 GitHub 普通 Git 单文件 100 MiB 限制，`dist/` 已加入 `.gitignore`。

## 更新版本

保持以下位置一致：

- `windows-version.txt`：文件版本元组、产品版本元组及字符串。
- `static/index.html`：侧栏显示版本。
- `CHANGELOG.md`：该版本的功能、修复及行为变化。

## 构建与验收

在可交互的 Windows x64 桌面执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
.\.venv\Scripts\python.exe -m unittest discover -v
node --test tests/test_model.mjs tests/test_ui_lifecycle.mjs
.\.venv\Scripts\python.exe -m tests.exe_smoke
```

确认独立窗口、查询、测试进程结束和退出清理均通过，并检查 `.runtime/exe-desktop-preview.png`。构建前关闭正在运行的同路径输出 EXE，以免文件被锁定。

为交付文件生成校验文件：

```powershell
$artifactHash = (Get-FileHash -LiteralPath .\dist\Portside.exe -Algorithm SHA256).Hash.ToLowerInvariant()
"$artifactHash  Portside.exe" | Set-Content -LiteralPath .\dist\SHA256SUMS.txt -Encoding ascii
```

在验证记录中写明测试系统、依赖版本、文件大小和哈希。不同构建环境生成的 EXE 哈希可能不同，以对应发布附件的校验文件为准。

## 推送源码

已有仓库直接提交并推送；从本地新项目首次上传时使用：

```powershell
git init -b main
git remote add origin git@github.com:206069780/process-panel.git
git add .
git diff --cached --stat
git commit -m "docs: prepare Portside project for GitHub"
git push -u origin main
```

推送前检查暂存列表。虚拟环境、缓存、运行记录、构建中间产物与 EXE 不应在其中。已存在 `origin` 时通过 `git remote -v` 核对地址，不必再次添加。

## 创建 Release

1. 在仓库的 Releases 页面选择“Draft a new release”。
2. 基于已验证提交创建版本标签，例如 `v1.1.0`。
3. 将对应的更新日志写入发布说明，标明 Windows x64 和独立桌面窗口。
4. 上传 `dist/Portside.exe`、`dist/SHA256SUMS.txt` 及与本次打包依赖匹配的第三方许可材料，检查附件完整后发布。

当前项目未配置自动发布工作流，推送源码不会自动上传 EXE。第三方许可材料的整理依据见[第三方组件说明](../THIRD_PARTY_NOTICES.md)。

如果已安装并登录 GitHub CLI，也可执行以下命令创建发布草稿，再在网页检查附件并发布：

```powershell
gh release create v1.1.0 --target main --draft --title "Portside 1.1.0" --notes-file CHANGELOG.md .\dist\Portside.exe .\dist\SHA256SUMS.txt
```

完成后从 Releases 重新下载 EXE，核对 SHA-256，再检查独立运行。
