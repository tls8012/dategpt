# DateGPT Backend Protocol

The Ren'Py frontend and Python backend communicate using newline-delimited JSON
(JSONL) over stdin/stdout.

DateGPT v1 intentionally supports exactly one active game session per backend
process. Opening another session replaces the current active session. There is
no protocol-level session_id; persistent play identity is the existing GAME_ID.

## Common request field

Requests should include a frontend-generated request_id. Every response/event
caused by that request echoes the same value.

```json
{"type":"ping","request_id":"renpy-1"}
```

## Session lifecycle

### open_session

```json
{
  "type": "open_session",
  "request_id": "renpy-2",
  "scenario_path": "/path/to/distribution",
  "prompt_path": "/path/to/prompts",
  "game_id": null,
  "new_game": false,
  "distribution_url": "",
  "manifest_url": ""
}
```

scenario_path and prompt_path may be omitted when DATEGPT_SCENARIO_DIR and
DATEGPT_PROMPT_DIR are configured.

Success:

```json
{
  "type": "session_opened",
  "request_id": "renpy-2",
  "game_name": "...",
  "game_id": "...",
  "is_new": true,
  "needs_setup": true,
  "controls": {},
  "has_welcome": true
}
```

If multiple compatible GAME_ID directories exist and none was selected:

```json
{
  "type": "instance_selection_required",
  "request_id": "renpy-2",
  "game_ids": ["...", "..."]
}
```

### setup_session

Used only when session_opened.needs_setup is true.

```json
{
  "type": "setup_session",
  "request_id": "renpy-3",
  "play_mode": "observer",
  "player_character_mode": "none",
  "main_character": "none",
  "controls": {},
  "current": {}
}
```

### get_session_state / close_session

These inspect or clear the one active in-process session.

## Gameplay

### play

```json
{
  "type": "play",
  "request_id": "renpy-10",
  "text": "*문을 연다*",
  "controls": {
    "language": "한국어",
    "initiative": "medium",
    "world_consistency": "medium",
    "paused": false
  }
}
```

The frontend may send the current controls on every player request. The backend
applies them before constructing the turn context.

A long operation may first emit:

```json
{"type":"status","request_id":"renpy-10","message":"메세지 처리중..."}
```

and finally:

```json
{"type":"reply","request_id":"renpy-10","text":"..."}
```

The legacy message type say is accepted as a compatibility alias for play so the
current Ren'Py text-input path does not need to change immediately.

### checkpoint

Runs the runtime's semantic save command without appending that maintenance turn
to ordinary conversation history.

```json
{"type":"checkpoint","request_id":"renpy-11"}
```

Success returns checkpoint_complete.

## Deterministic controls/settings

These do not invoke an LLM:

- get_controls
- set_control
- get_model_settings
- set_model
- set_api_key
- clear_api_key

The existing text commands are adapters over the same backend state.

## Errors

Expected failures use a stable frontend-facing shape:

```json
{
  "type": "error",
  "request_id": "renpy-10",
  "code": "NO_ACTIVE_SESSION",
  "message": "...",
  "recoverable": true
}
```

The frontend should branch on code rather than Python exception class names.
