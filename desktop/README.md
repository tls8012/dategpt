# DateGPT Desktop

This directory contains the official DateGPT PySide6 frontend. DateGPT runs as
this desktop client plus the Python backend; there is no secondary game-engine
frontend.

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

In source mode the frontend launches the same desktop entrypoint again as
`--backend-worker` under the current interpreter. In packaged mode it launches
the packaged DateGPT executable itself as `--backend-worker`. The JSONL
transport is identical in both cases.

## Implemented

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
- structured narration/dialogue/system presentation with per-segment asset IDs
- resolved transparent character SCG rendering (up to three assets per segment)
- Space-based sentence paging
- resume-time restoration of the latest conversation presentation
- Help and Continue actions without typing commands
- on-demand Enter input panel
- language / initiative / world consistency settings
- dynamic scenario-specific string controls from the active cartridge
- dialogue overlay inside the stage/background area

Keyboard interaction in the game page:

- Space: advance to the next structured presentation segment
- Enter: open the free-text input panel
- Ctrl+Enter: send free-text input
- Escape: close the input panel

Presentation is intentionally non-streaming: one LLM call completes and validates
the structured response before its segments are shown.

Not implemented yet:

- dedicated background/event-CG layer and transitions
- rich existing-character picker
