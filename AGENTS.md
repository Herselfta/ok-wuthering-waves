# Agent Instructions

## Python

- When running Python commands in this repository, use the local virtual environment if it exists.
- On Windows/PowerShell, prefer `.\.venv\Scripts\python.exe` when present.
- On POSIX shells, prefer `./.venv/bin/python` when present.
- Fall back to `python` only when no local `.venv` interpreter exists.
- Prefer invoking the interpreter directly, for example `.\.venv\Scripts\python.exe -m pytest`, instead of relying on shell activation.

## Environment

- The `.venv` is uv-managed and has no `pip` module. Install packages with `uv pip install --python .venv/Scripts/python.exe <packages>`.

## Dependency sync after upstream merges

- A machine hook auto-syncs deps when a merge changes `requirements.txt`: `.githooks/post-merge` (versioned). Activate per checkout with `git config core.hooksPath .githooks` (machine-local config, re-run after a fresh clone). It runs `uv pip install --python .venv/Scripts/python.exe -r requirements.txt`, skips silently when requirements.txt is unchanged, and warns with the manual command if `.venv` or `uv` is missing.
- Upstream merges that regenerate `requirements.txt` must be followed by re-syncing the venv, or the app crashes on startup with `ModuleNotFoundError`.
  - Incident 2026-11-04: commit 9dff2c92 migrated the GUI to `ok.ui.qt.kit` and bumped ok-script 2.0.22 → 3.0.0b3 (+ new ok-pyside-minimal), but the venv kept the old package. `start.ps1` died at `src/gui/CharacterCodeTab.py:21` with `ModuleNotFoundError: No module named 'ok.ui.qt.kit'`. Fixed via `uv pip install --python .venv/Scripts/python.exe "ok-script[ocr,qt]==3.0.0b3" "ok-pyside-minimal==6.12.0.post2"`; start.ps1 verified working.
- `configs/custom_teams/*/*.py` currently load with `[WinError 5] 拒绝访问` warnings (CustomCharLoader skips those folders). Non-fatal; ACL/lock issue, unresolved as of 2026-11-04.
