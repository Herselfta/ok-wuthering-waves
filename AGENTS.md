# Agent Instructions

## Python

- When running Python commands in this repository, use the local virtual environment if it exists.
- On Windows/PowerShell, prefer `.\.venv\Scripts\python.exe` when present.
- On POSIX shells, prefer `./.venv/bin/python` when present.
- Fall back to `python` only when no local `.venv` interpreter exists.
- Prefer invoking the interpreter directly, for example `.\.venv\Scripts\python.exe -m pytest`, instead of relying on shell activation.

## Environment

- The `.venv` is uv-managed and has no `pip` module. Install packages with `uv pip install --python .venv/Scripts/python.exe <packages>`.
- `requirements.txt` is the single dependency source of truth (CI, tests, and `pyappify.yml` all read it). `uv.lock` is untracked and gitignored as of 2026-11-17.
- Never run a bare `uv sync`: it ignores `requirements.txt` and reconciles against `uv.lock`, rewriting the lock and rebuilding the venv from it. Use `uv pip install --python .venv/Scripts/python.exe -r requirements.txt` instead. If a lock-based sync is ever genuinely needed, use `uv sync --locked` so a stale lock fails loudly instead of silently rewriting the environment.
- If `pip` is invoked after activating the venv, it resolves to the *system* Python's pip, because this venv has no `pip.exe` and PATH lookup falls through. Prefer `uv pip install --python .venv/Scripts/python.exe ...`.

## Dependency sync after upstream merges

- A machine hook auto-syncs deps when a merge changes `requirements.txt`: `.githooks/post-merge` (versioned). Activate per checkout with `git config core.hooksPath .githooks` (machine-local config, re-run after a fresh clone). It runs `uv pip install --python .venv/Scripts/python.exe -r requirements.txt`, skips silently when requirements.txt is unchanged, and warns with the manual command if `.venv` or `uv` is missing.
- Upstream merges that regenerate `requirements.txt` must be followed by re-syncing the venv, or the app crashes on startup with `ModuleNotFoundError`.
  - Incident 2026-11-04: commit 9dff2c92 migrated the GUI to `ok.ui.qt.kit` and bumped ok-script 2.0.22 → 3.0.0b3 (+ new ok-pyside-minimal), but the venv kept the old package. `start.ps1` died at `src/gui/CharacterCodeTab.py:21` with `ModuleNotFoundError: No module named 'ok.ui.qt.kit'`. Fixed via `uv pip install --python .venv/Scripts/python.exe "ok-script[ocr,qt]==3.0.0b3" "ok-pyside-minimal==6.12.0.post2"`; start.ps1 verified working.
- Incident 2026-11-17: an interrupted dependency operation left `ok-pyside-minimal` and `onnxocr-ppocrv6` half-uninstalled — dist-info dirs intact, but 54 of 83 files gone (`PySide6/QtCore.pyd`, `Qt6Core.dll`, all `onnxocr/*.py`). `start.ps1` died with `ModuleNotFoundError: No module named 'PySide6.QtCore'` and `onnxocr.onnx_paddleocr`. Detect with a RECORD-vs-disk check over `site-packages/*.dist-info/RECORD`; fix with a cache-only reinstall: `uv pip install --offline --python .venv/Scripts/python.exe --reinstall --no-deps "ok-pyside-minimal==6.12.0.post2" "onnxocr-ppocrv6==0.0.1"` (`--no-deps` is required — offline resolution fails on `pyclipper`).
- `config.py`'s `custom_tabs` can reference deleted modules after a merge resolves in favor of a branch that kept a tab. As of 2026-11-17 `src.gui.CharacterCodeTab` was removed in d0a59291 but the entry survived the merge; `MainWindow` crashed with `ModuleNotFoundError: No module named 'src.gui.CharacterCodeTab'`. Verify every entry in `custom_tabs`, `onetime_tasks`, `trigger_tasks`, and `scene` is importable after merging.
- `configs/custom_teams/*/*.py` currently load with `[WinError 5] 拒绝访问` warnings (CustomCharLoader skips those folders). Non-fatal; ACL/lock issue, unresolved as of 2026-11-04.
