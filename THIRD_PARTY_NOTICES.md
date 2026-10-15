# 第三方组件说明

Portside 使用以下主要第三方组件。本文件列出项目及许可来源，不替代各依赖随包提供的完整许可、版权和第三方声明。

| 组件 | 用途 | 许可与来源 |
| --- | --- | --- |
| Python | 随应用提供的运行时 | [Python 许可](https://docs.python.org/3/license.html) |
| psutil | 系统资源、进程与网络信息 | [BSD 3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| PySide6 / Qt for Python | 桌面窗口及 Qt Python 绑定 | [Qt for Python 许可说明](https://doc.qt.io/qtforpython-6/licenses.html)，包含 LGPLv3 / GPLv3 / 商业许可选项，具体以所用组件为准 |
| Qt / Qt WebEngine | 内置界面渲染，包含 Chromium 等依赖 | [Qt 许可](https://doc.qt.io/qt-6/licensing.html)、[Qt WebEngine 许可及第三方代码](https://doc.qt.io/qt-6/qtwebengine-licensing.html) |
| PyInstaller | 应用构建及引导程序 | [GPL 及分发例外](https://pyinstaller.org/en/stable/license.html) |
| Pillow | 构建图标、验收截图 | [Pillow 许可](https://pillow.readthedocs.io/en/stable/about.html#license) |

运行和构建依赖版本约束分别位于 `requirements.txt`、`requirements-build.txt`。实际构建版本可通过以下命令记录：

```powershell
.\.venv\Scripts\python.exe -m pip freeze
```

发布包含 Qt / Chromium 的二进制时，应随发布附件提供与所用版本匹配的许可和第三方声明，并按对应许可提供所需的源码获取方式及其他材料。请从实际构建环境及对应版本的官方发行包整理，不能用本文件代替完整材料。
