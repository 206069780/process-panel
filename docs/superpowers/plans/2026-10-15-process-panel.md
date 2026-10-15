# Process Panel Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. Complete the work in this session; user already authorized implementation.

**Goal:** Build a usable local Windows process and port dashboard with verified process termination.

**Architecture:** A loopback Python HTTP server serves static browser assets and a token-protected JSON API. psutil supplies cached snapshots and process identity checks; browser modules perform filtering, sorting, and rendering.

**Tech Stack:** Python 3.12, psutil 7, standard-library unittest and HTTP server, HTML/CSS, native JavaScript modules, Node built-in tests.

## Global Constraints

- 独立存放于 `D:\yz2\process-panel`。
- 服务仅监听 `127.0.0.1`，页面与 API 同源。
- 使用真实进程和 TCP / UDP 数据；保护关键进程、工具本身及其启动进程。
- 结束操作同时匹配 PID 与启动时间；实际测试只结束测试自行创建的进程。
- 中文深色界面；不需要前端构建工具。

## Task 1: System data and process operations

Files: `panel/monitor.py`, `panel/processes.py`, `tests/helpers.py`, `tests/test_processes.py`, `requirements.txt`.

Interfaces: `Monitor.refresh() -> dict`, `Monitor.snapshot() -> dict`, `process_detail(pid: int) -> dict`, `terminate_process(pid: int, create_time: float) -> dict`; `PanelError(status, message)` provides user-facing errors.

- [x] Write real child-process tests for TCP/UDP discovery, process detail, mismatched creation time, protected processes, termination and released port.
- [x] Run `python -m unittest tests.test_processes -v`; confirm missing implementation causes failure.
- [x] Implement process identity validation using `psutil.Process(pid).create_time()`, protected ancestors and Windows critical-process detection. Collect snapshots using `psutil.process_iter` and `psutil.net_connections`.
- [x] Run tests with the virtual environment interpreter; require every process test to pass and always clean up children.

## Task 2: HTTP boundary and browser dashboard

Files: `panel/server.py`, `main.py`, `static/index.html`, `static/styles.css`, `static/app.js`, `static/model.mjs`, `tests/test_server.py`, `tests/test_model.mjs`.

Interfaces: `PanelServer(port=0, monitor=None)` exposes `.token`, `.server_address`, `.serve_forever()`. Endpoints: `GET /api/snapshot`, `GET /api/processes/{pid}`, `POST /api/refresh`, `POST /api/processes/{pid}/terminate` with JSON `{"create_time": number}`. Responses are JSON; errors use `{"error": string}`.

- [x] Write API tests for missing token, foreign origin/host, valid reads, invalid JSON and process identity. Write JavaScript tests for exact numeric port/PID matching, text search, filters, sort and pagination.
- [x] Run `python -m unittest tests.test_server -v` and `node --test tests/test_model.mjs`; confirm expected failures.
- [x] Implement exact static path allowlist, loopback binding, per-instance token, Origin/Host validation, CSP and bounded JSON requests.
- [x] Implement responsive sidebar, resource cards with session sparkline charts, searchable/sortable paginated tables, process detail dialog, explicit termination confirmation, refresh controls and error messages.
- [x] Run both suites and use the browser to inspect real data, searches, dialogs and refresh controls.

## Task 3: Launch, review and delivery

User amendment: deliver a standalone Windows EXE. Files: `panel/desktop.py`, `panel/tray.py`, `Portside.spec`, `windows-version.txt`, `build.ps1`, `requirements-build.txt`, `assets/portside.ico`, `README.md`, `.gitignore`, `tests/test_desktop.py`, `tests/test_ui_lifecycle.mjs`, `tests/exe_smoke.py`.

- [x] Provide a single-file windowed EXE with embedded Python, bundled static assets, tray open/admin/quit menu, per-instance runtime records and a named mutex for duplicate launches. Source build script installs dependencies into `.venv`.
- [x] Run the complete backend and JavaScript suites, syntax checks and the real HTTP process-termination scenario.
- [x] Request independent code review; fix any important findings, then rerun affected checks.
- [x] Leave the tested dashboard running and provide the launcher path and local URL.
