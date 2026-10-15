# 开发指南

## 环境

- Windows x64；当前实机验证环境为 Windows 11。
- Python 3.12 x64，建议与已验证构建保持一致。
- Node.js 24，用于前端测试和打包后的页面探测。
- 首次安装依赖需要联网。终端应位于项目根目录。

运行依赖见 `requirements.txt`；构建及完整测试依赖见 `requirements-build.txt`。Node 测试使用内置模块，无需 `npm install`。

## 准备与运行

```powershell
git clone git@github.com:206069780/process-panel.git
cd process-panel
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py
```

不必激活虚拟环境，直接调用其中的 Python。也可以在环境准备完成后运行 `start.cmd`。

```powershell
.\.venv\Scripts\python.exe main.py --port 0 --runtime-dir .runtime\development
```

`--port 0` 让系统分配空闲端口；`--runtime-dir` 隔离运行记录和实例锁，便于并行调试。默认启动始终显示桌面窗口。

## 目录结构

```text
main.py                 启动、参数、实例锁和清理
panel/
  desktop.py            权限检测、运行记录、Windows 互斥锁
  window.py             Qt 窗口、内置页面、本地 IPC 和生命周期
  splash.py             原生启动动画、加载状态和取消按钮
  monitor.py            进程及网络采集、后台刷新、快照缓存
  processes.py          进程详情、身份校验和受保护的结束操作
  server.py             回环 HTTP 服务、会话和来源校验
  tray.py               构建图标及 Windows 提权辅助函数
static/
  index.html            中文界面
  styles.css            样式
  app.js                数据加载、交互、详情及结束确认
  model.mjs             搜索、筛选、排序、分页和格式化
tests/                  Python、Node 与打包验收
assets/portside.ico      应用图标，可通过构建脚本重新生成
Portside.spec           PyInstaller 目录 / 单文件打包配置
build.ps1               Windows 构建入口
windows-version.txt     EXE 版本资源
docs/                   使用、设计、开发和发布文档
```

`panel/tray.py` 的文件名来自早期实现；当前应用通过窗口关闭退出，不使用托盘入口。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
node --test tests/test_model.mjs tests/test_ui_lifecycle.mjs
```

Python 测试包括真实 Qt 窗口、剪贴板、本地网络监听与可丢弃子进程，需要可交互的 Windows 桌面。Node 测试覆盖查询模型及结束请求期间的界面状态。1.1.0 的验证基线为 Python 30 项、Node 12 项通过。

## 打包与独立运行验收

先关闭正在使用同一输出文件的应用，然后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
.\.venv\Scripts\python.exe -m tests.exe_smoke
```

构建脚本创建或复用 `.venv/`，安装依赖、生成图标，输出 `dist\Portside\Portside.exe`、其 `_internal` 组件及 `dist\Portside-windows-x64.zip`。默认目录模式避免每次启动重复解包。打包配置会限制依赖扫描 PATH，防止开发工具目录中的不兼容 ICU DLL 被意外收集。

独立验收将 EXE 及同目录 `_internal` 复制到中文临时目录，使用隔离的用户配置，移除 Python 路径，再检查窗口、实际页面数据、重复启动、最小化恢复、TCP / UDP 归属、结束测试进程、端口释放以及关闭清理。只为验收进程开启 Qt 调试端口；正常启动不启用它。

可选单文件模式与验收：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SingleFile
.\.venv\Scripts\python.exe -m tests.exe_smoke --exe dist\singlefile\Portside.exe
```

结果和截图写入 `.runtime/`，该目录不进入版本控制。验收时请等待标有“自动验证”的窗口自行完成。

## 测量启动性能

```powershell
.\.venv\Scripts\python.exe -m tests.startup_benchmark --runs 3
```

记录启动到内部服务、启动动画、主窗口显示和实际数据界面就绪的时间，并在每次测量后关闭测试实例。可用 `--exe PATH` 选择其他构建，`--output PATH` 保存比较结果，`--max-ready-seconds 4` 设置本机验证门槛。默认不设与硬件相关的强制上限。测量过程中不要同时构建或执行其他测试。

## 修改约定

查询规则集中在 `static/model.mjs`，修改时同步更新测试和用户示例。结束进程的身份检查与保护逻辑集中在 `panel/processes.py`；不要通过界面绕过它。内部接口发生变化时同步维护[架构说明](ARCHITECTURE.md)，版本变更同步维护[更新日志](../CHANGELOG.md)。
