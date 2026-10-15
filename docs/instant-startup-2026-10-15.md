# 1.1.2 启动性能及独立 EXE 验证

日期：2026-10-15。Windows 11 x64，Python 3.12，psutil 7.2.2，PySide6 6.10.2，PyInstaller 6.22.3，Node.js 24.18.0。

## 最终行为

保留原有界面、图表及交互，通过独立 EXE 窗口运行。启动动画先出现，再加载内置网页渲染组件；不设置固定动画等待时长，不使用后台常驻或开机预加载。

Windows 进程采集改为一次批量系统查询。优化前约 475 个进程的刷新耗时 1.7 秒，cProfile 显示 278 次受限进程回退扫描约占 1.6 秒；优化后三次刷新约 0.054、0.022、0.021 秒。网络采集及单句柄进程身份/保护检查保留，原生查询不支持时回退 psutil。

退出清理新增显式 GUI 线程窗口销毁。原先连续窗口测试中，关闭窗口的 Python 引用循环可能在采集线程触发 GC，导致 Qt WebEngine 原生崩溃；先销毁页面，再销毁窗口和配置后，全套窗口测试通过。

## 实际 EXE 启动测量

`tests/startup_benchmark.py` 从创建 EXE 进程开始计时，分别记录原生动画、Windows 主窗口和实际页面数据就绪。数据就绪要求实时连接、CPU 值加载、初始加载提示消失，并检查打包后的查询模块。每轮隔离运行目录、关闭程序并检查工作进程退出。没有清空 Windows 文件缓存，测试过程中没有并发构建或其他功能测试。

```powershell
.\.venv\Scripts\python.exe -m tests.startup_benchmark --exe dist\Portside\Portside.exe --runs 3 --max-ready-seconds 3 --output .runtime\instant-delivered-startup.json
```

单位：秒，均为从启动开始的累计值。staging 与最终交付为同一哈希的 EXE，移到交付路径后再次测量。

| 路径 | 轮次 | 运行记录 | 启动动画 | 主窗口 | 数据就绪 |
| --- | --- | ---: | ---: | ---: | ---: |
| staging | 1 | 1.898 | 2.697 | 4.414 | 4.509 |
| staging | 2 | 0.589 | 0.627 | 1.547 | 1.651 |
| staging | 3 | 0.511 | 0.552 | 1.531 | 1.641 |
| 最终交付路径 | 1 | 2.475 | 2.515 | 5.055 | 5.175 |
| 最终交付路径 | 2 | 0.308 | 0.347 | 1.283 | 1.378 |
| 最终交付路径 | 3 | 0.300 | 0.348 | 1.174 | 1.261 |

最终交付路径的数据就绪中位数为 **1.378 秒**，主窗口为 **1.283 秒**；相比 [1.1.1](startup-performance-2026-10-15.md) 数据就绪中位数 3.571 秒减少约 61%。后两轮动画约 0.35 秒出现，数据约 1.26～1.38 秒可用。

同一构建在 staging 首轮为 4.509 秒，移到最终路径后首轮为 5.175 秒。路径变化、文件缓存、磁盘和系统负载仍带来明显波动；这些结果不能证明所有设备、每次启动都严格小于 1 秒。动画出现和界面可操作是不同的时间点。

## 验收

- Python unittest：40 项通过。包含批量采样的真实名称/创建时间/工作集、CPU 差分与 PID 重用、无逐 PID 扫描、异常回退、TCP/UDP 归属及终止后释放端口。
- Node：14 项通过，覆盖模糊/精确查询、数值排序、确认目标锁定、首屏轮询和暂停刷新。
- 窗口验证：延迟导入、动画帧变化/取消、初始化异常、页面失败、真实加载、详情复制、全屏、最小化恢复、本地 IPC 与 GUI 对象销毁。
- 最终便携 EXE 与可选单文件 EXE 分别通过完整独立验收：中文临时目录、移除 Python PATH、实际数据和模糊查询、自身/渲染进程保护、结束自行创建的 TCP/UDP 子进程、端口释放、重复/同时启动、记录缺失时唤起、取消启动与关闭后重启及工作进程清理。
- 独立静态复审通过，核对原界面入口、依赖、安全设置和窗口销毁；原生界面试验不进入交付源码。

## 交付校验

便携文件夹共 2,830 个文件、568,827,403 字节。ZIP 清单及大小与文件夹逐一核对，无重复条目，全部 CRC 通过。默认快速启动入口为 `dist/Portside/Portside.exe`，必须保留 `_internal`；可选单文件需要每次解包。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `dist/Portside/Portside.exe` | 1,953,260 | `21002d7ab6f478eb17761fcf8c8462454d378dd5ca5867436ba3cff84b60923c` |
| `dist/Portside-windows-x64.zip` | 211,978,645 | `1856aa08edb7ee7bb65724dba49a932807f35043c6a1ed2c84deffb2a29ffe05` |
| `dist/singlefile/Portside.exe` | 210,660,555 | `bae1a9f87f7888a72699cc4a4439ebfada7708b751f92d92ca71289a33a65e3e` |

`dist/SHA256SUMS.txt` 包含这三个校验值。EXE 文件资源版本和产品版本分别为 1.1.2.0 与 1.1.2。旧交付文件保存在本地历史目录。

根目录 `preview.png` 为最终打包界面的实际 CDP 截图；普通运行不启用调试端口。原生启动动画截图沿用 [startup.png](images/startup.png)。本地详细证据在 `.runtime/instant-python-tests.log`、`instant-node-tests.log`、`instant-portable-smoke-report.json`、`instant-singlefile-smoke-report.json`、`instant-startup-report.json`、`instant-delivered-startup.json`、`instant-archive-verification.log` 和 `instant-artifact-report.json`，不进入 Git。
