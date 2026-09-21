# DateGPT PySide6 desktop prototype

This directory is a standalone desktop frontend for the existing DateGPT
backend. It does not replace the Ren'Py files yet.

## Why QProcess

The backend already exposes a line-delimited JSON protocol over stdin/stdout.
Qt's QProcess integrates that protocol with the GUI event loop directly, so the
desktop frontend does not need a socket server, a Python polling queue, or a
frontend reader thread.

stderr is treated as diagnostic output and is available in the optional debug
dock.

## Run

Use one repository-level virtual environment for both the desktop UI and the
DateGPT backend.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python desktop/main.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python desktop\main.py
```

The frontend launches `BACKEND/backend.py` with the exact same
`sys.executable` that is running the PySide application. There is no second
backend virtual environment.

## Implemented in this prototype

- installed cartridge list
- local/GitHub cartridge install entry
- explicit New Game / Continue buttons
- non-mutating game-instance listing
- onboarding mode buttons
- free text onboarding/gameplay input
- model provider/model/API-key settings dialog
- semantic checkpoint button
- toggleable backend debug dock
- QProcess signal-based backend transport
- sparse turn journal with rollback/edit/regenerate

Not implemented yet:

- structured speaker/narration output
- 2-3 line dialogue paging/streaming
- cartridge asset rendering
- rich existing-character picker
