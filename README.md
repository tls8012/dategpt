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

In source/development mode the desktop process starts a second copy of
`desktop/main.py --backend-worker` under the same repository virtual
environment and communicates with it asynchronously through Qt `QProcess`.
Packaged builds start the same DateGPT executable in `--backend-worker` mode,
so end users do not need Python or a virtual environment.

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


## Packaged desktop builds

DateGPT uses PyInstaller one-folder bundles. Packaged users do not install
Python, PySide6, LangChain, or provider SDKs separately.

Build locally:

```bash
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean packaging/DateGPT.spec
```

Outputs:

- macOS: `dist/DateGPT.app`
- Windows: `dist/DateGPT/DateGPT.exe`

Packaged mutable data is stored outside the application bundle:

- macOS: `~/Library/Application Support/DateGPT/`
- Windows: `%APPDATA%\DateGPT\`

Set `DATEGPT_HOME` to override that root for development/testing.
