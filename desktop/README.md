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

Create a desktop environment and install PySide6:

```bash
python3 -m venv .venv-desktop
source .venv-desktop/bin/activate
pip install -r desktop/requirements.txt
python desktop/main.py
```

By default the frontend looks for `BACKEND/backend.py`. For the backend Python
interpreter it prefers the existing `BACKEND/datevenv` and falls back to the
interpreter that launched the desktop UI.

You can override that:

```bash
python desktop/main.py --backend-python /path/to/backend/python
```

or set `DATEGPT_BACKEND_PYTHON`.

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

Not implemented yet:

- turn rollback/edit/regenerate
- structured speaker/narration output
- 2-3 line dialogue paging/streaming
- cartridge asset rendering
- rich existing-character picker
