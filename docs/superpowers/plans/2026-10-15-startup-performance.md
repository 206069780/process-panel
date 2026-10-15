# Startup Performance Implementation Plan

> **For agentic workers:** Execute inline with executing-plans and review packaging changes at the final checkpoint. The existing desktop design and the user's performance fix request authorize this work.

**Goal:** Remove repeated runtime extraction from the normal Windows EXE startup.

**Architecture:** Use PyInstaller onedir as the default distribution and keep onefile optional. Preserve all application runtime behavior and validate both artifact shapes through source-free desktop checks.

**Tech Stack:** Python 3.12, PySide6 6.10.2, PyInstaller 6, PowerShell.

## Constraints

- Keep an independent desktop window and all process protections.
- Preserve the user's active application until the new package passes validation.
- Do not add an external runtime prerequisite.
- Only terminate processes created by verification or the exact old app during replacement.

### Task 1: Reproducible measurement

Files: `tests/startup_benchmark.py`.

- [x] Add `python -m tests.startup_benchmark --exe PATH --runs 2 --max-ready-seconds 4 --output REPORT` to measure isolated launches, actual window and live page readiness, then close each app.
- [x] Observe the original single-file artifact failing the explicit 4 second target after saving timing evidence (median 6.153 seconds).

### Task 2: Package and validate the fast distribution

Files: `Portside.spec`, `build.ps1`, `tests/exe_smoke.py`, version metadata and docs.

- [x] Default to `EXE(..., exclude_binaries=True)` plus `COLLECT`; select onefile through a task-specific environment variable set by `build.ps1 -SingleFile`.
- [x] Produce `dist/Portside/Portside.exe` and `dist/Portside-windows-x64.zip`; keep optional onefile output under `dist/singlefile/`.
- [x] Extend smoke staging to copy `_internal` and recognize the owning launcher under both modes.
- [x] Reproduce delayed initial sampling with a failing frontend test; poll initial readiness every 150ms and stop after readiness or pause.
- [x] Build, run the same timing target against the new artifact, and execute full desktop smoke plus source regressions.
- [x] Update user/developer/release docs with the whole-folder requirement and measured comparison.
- [x] Review the change, retire the old default binary after graceful close, and leave the verified package ready for source synchronization.

### Task 3: Native startup animation

Files: `panel/splash.py`, `panel/window.py`, `tests/test_window.py`, startup benchmark and docs.

- [x] Add failing checks for visible animation, immediate completion, early cancellation and initialization failure.
- [x] Show a native animated splash before WebEngine construction, hand off on page load, and clean up on every exit path.
- [x] Verify a real desktop launch and cancellation, capture the animation, then rebuild and remeasure the delivered EXE.
