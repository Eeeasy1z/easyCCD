# AGENTS.md

Repository guidance for autonomous coding agents working in `easyCCD`.

## 1) Project snapshot

- Language/style: Python 3.13+ conventions (`list[int]`, `X | None`, `from __future__ import annotations`)
- App type: Desktop GUI (PySide6 + pyqtgraph) with serial communication
- Entry point: `src/main.py`
- Runtime deps (`requirements.txt`): `PySide6`, `pyserial`, `pyqtgraph`, `numpy`
- Current maturity: MVP-level; no formal lint/type/test/build toolchain configured yet

## 2) Repository layout

- `src/main.py` — app bootstrap (`QApplication`, `MainWindow`)
- `src/ui/` — UI composition + event handling (`main_window.py`)
- `src/ui/widgets/` — reusable widgets (`waveform_widget.py`, `data_table_widget.py`)
- `src/comm/` — serial I/O manager + frame parsing (`serial_manager.py`)
- `src/core/` — business logic (`filter_pipeline.py`)
- `src/core/filters/` — filter ABC + concrete filters (`mean`, `median`, `gaussian`)
- `src/utils/` — helpers and mock generators
- `tests/` — package exists; currently no concrete `test_*.py` files

## 3) Build / run / lint / test commands

This repo currently has **no configured scripts** (`pyproject.toml`, `setup.cfg`, `tox.ini`, `Makefile`,
and CI workflows are absent). Use these practical defaults.

### Environment setup

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Run app

```bash
python src/main.py
```

### Tests (including single-test commands)

Current status:
- `tests/` exists
- no concrete `test_*.py` modules yet
- no pytest dependency configured

Baseline command (stdlib unittest):

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Single-test examples (when tests are added):

```bash
# Single test module
python -m unittest tests.test_filter_pipeline

# Single test class
python -m unittest tests.test_filter_pipeline.FilterPipelineTests

# Single test method
python -m unittest tests.test_filter_pipeline.FilterPipelineTests.test_apply_pipeline
```

### Lint / format / typecheck

No linters/formatters/type checkers are configured today. Do **not** assume these commands exist unless tooling is explicitly added.

If tooling is introduced later, typical commands would be:
- `ruff check .`
- `black --check .`
- `mypy src`

### Lightweight sanity check

```bash
python -m compileall src tests
```

## 4) Coding conventions observed in this repo

Follow existing patterns unless a deliberate refactor changes standards.

### Imports

1. Keep `from __future__ import annotations` at top of modules.
2. Group imports with blank lines: stdlib → third-party → local imports.
3. Prefer explicit imports; avoid wildcard imports.
4. In `src/`, local imports are package-style absolute (`from core.filter_pipeline import FilterPipeline`).

### Formatting

1. 4-space indentation, no tabs.
2. Keep spacing around operators/commas consistent.
3. Use blank lines between logical blocks/classes/functions.
4. No strict line-length tool is configured; prefer readability.

### Types and annotations

1. Add annotations for parameters and return values.
2. Use modern built-in generics (`list[int]`, `dict[str, int | float]`).
3. Use `X | None` instead of `Optional[X]` in new code.
4. Keep type hints inline (no legacy type comments).

### Naming

1. `snake_case` for functions, methods, variables.
2. `PascalCase` for classes.
3. `UPPER_CASE` for constants/class constants (`HEADER`, `PAYLOAD_LEN`, `POINT_COUNT`).
4. Prefix private/internal members with `_`.

### Error handling

1. Validate inputs early; raise specific exceptions (`ValueError`, `TypeError`, `KeyError`).
2. Catch narrow exceptions when possible (`except (TypeError, ValueError)` etc.).
3. Broad `except Exception` is acceptable only at UI/callback safety boundaries.
4. For recoverable failures, use graceful fallback (e.g., return raw data, update status labels).

### Architecture patterns

1. Keep algorithmic logic in `src/core/`, not inside UI widgets.
2. Filters implement `FilterBase.apply(...)` and expose `name` + `default_params`.
3. `FilterPipeline` composes ordered filter execution.
4. Use Qt signal/slot bridge patterns for thread-safe UI updates from serial callbacks.
5. Preserve payload assumptions where present (128 points, clamped uint8-friendly values).

## 5) Testing guidance for future changes

1. Core filter changes: add tests in `tests/test_filter_pipeline.py` or `tests/test_filters_*.py`.
2. Serial parsing changes: add deterministic frame parsing tests.
3. Keep UI-heavy tests limited unless a Qt test harness is added.
4. Prefer deterministic fixtures over random-only assertions.

## 6) Agent operating rules for this repository

1. Before editing, inspect neighboring modules and match local style/patterns.
2. Keep changes scoped; avoid unrelated refactors.
3. If adding dependencies/tools, update `requirements.txt` and document commands.
4. If adding lint/test/type tooling, also add config files and update this AGENTS.md.
5. Never claim test/lint/build success without running commands and capturing output.

## 7) Cursor / Copilot rules check

During this analysis, these files were searched and **not found**:

- `.cursorrules`
- `.cursor/rules/`
- `.github/copilot-instructions.md`

If they are added later, fold their guidance into this file and resolve any conflicts explicitly.

## 8) Known gaps

1. No formal build command exists yet.
2. No configured lint/format/typecheck command exists yet.
3. `tests/` exists but currently has no concrete test modules.

For non-trivial changes, include a brief “verification performed” note listing exact commands run.
