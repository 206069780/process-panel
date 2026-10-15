# Portside Desktop Window Implementation Plan

> **For agentic workers:** Execute inline and use requesting-code-review at the final review checkpoint. Track completed steps below. This project is not a Git repository.

**Goal:** Deliver a standalone Windows EXE that opens its own dashboard window.

**Architecture:** Keep the monitor, guarded process actions, and loopback API. Add a Qt desktop shell with local IPC activation. Use an owned Win32 mutex for startup coordination and package Qt WebEngine into the onefile executable.

**Tech Stack:** Python 3.12, psutil, PySide6 6.10.2, PyInstaller 6.

## Global Constraints

- No external browser is opened.
- No Python or WebView2 installation is required on the target machine.
- Closing the window shuts down the service and monitor.
- Process termination retains identity validation and critical-process protections.

### Task 1: Desktop lifecycle and startup coordination

Files: `panel/desktop.py`, `panel/window.py`, `main.py`, `tests/test_desktop.py`, `tests/test_window.py`.

- [x] Add regression tests for desktop default startup, no browser launch, window lifecycle and same-instance activation.
- [x] Run the new tests and observe failure before implementation.
- [x] Implement owned mutex with zero-timeout acquisition and abandoned-lock recovery; scope name to executable, privilege and runtime directory.
- [x] Add `run_desktop(server, name)` to create the Qt window and a QLocalServer for focus requests. Duplicate launches use QLocalSocket, without relying on JSON record discovery.
- [x] Restrict navigation to the local origin, support fullscreen and clipboard, and prevent external windows.
- [x] Run tests including actual Qt rendering, close, activation and minimized-window restoration.

### Task 2: Standalone packaging and verification

Files: `Portside.spec`, `requirements-build.txt`, `build.ps1`, `tests/exe_smoke.py`, `README.md`, `static/index.html`.

- [x] Bundle Qt WebEngine and assets; remove tray-only runtime dependency and browser instructions.
- [x] Build with PyInstaller; verify a clean build after dependency PATH isolation, then rebuild final changes to `.runtime/staged-dist` while preserving the user's running copy.
- [x] Run `python -m unittest discover -v` and `node --test tests/test_model.mjs tests/test_ui_lifecycle.mjs` (30 and 12 passed).
- [x] Run packaged EXE test from a source-free Chinese directory, with default runtime discovery; check a visible native window, duplicate activation, real process actions, graceful close and relaunch.
- [x] Capture the rendered desktop window and request independent review. Correct material findings before delivery.
- [x] Update verification evidence and leave the corrected EXE ready to use.

### Additional user requirement: fuzzy search

- [x] Match ordinary query fragments across process name, PID, ports and addresses; retain explicit exact query prefixes.
- [x] Verify source tests and the packaged module; update query examples and help text.
- [x] Reject overlapping Windows socket binds and fall back to an available service port, with regression coverage.
