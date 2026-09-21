# DateGPT

DateGPT is a local desktop visual-novel runtime built with a PySide6 frontend
and a Python/LangChain backend.

## Architecture

```text
PySide6 desktop
    │  JSONL over stdin/stdout (QProcess)
    ▼
Python backend
    │
    ├─ cartridge/scenario loader
    ├─ session + Save state
    ├─ controls and onboarding
    ├─ LangChain agent/tools
    └─ structured VN presentation
```

The desktop client is the only application frontend. The backend owns game
state, model calls, cartridge access, rollback/edit/regenerate, and persistence.

## Run

Use one repository-level virtual environment for the whole application.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python desktop\main.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python desktop/main.py
```

The desktop process starts `BACKEND/backend.py` with the same Python
interpreter and communicates with it asynchronously through Qt `QProcess`.

## Repository layout

- `desktop/` — PySide6 application UI and backend client.
- `BACKEND/` — DateGPT engine, protocol, tests, model integration, and local
  runtime data.
- `.scaffolding/` — managed runtime/onboarding prompts.
- `requirements.txt` — shared application dependencies.

Scenario content is installed as cartridges and remains separate from the
application code.

## Current presentation model

Each LLM turn produces one validated structured response made of ordered
narration/dialogue/system segments. A segment may select zero or more registered
asset references. The backend emits presentation events only after the single
LLM call finishes and validates; partial structured token streaming is not used.

See `desktop/README.md` for UI behavior and `BACKEND/PROTOCOL.md` for the
JSONL protocol.
