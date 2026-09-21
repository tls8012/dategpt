# DateGPT Backend Protocol

The Ren'Py frontend and Python backend communicate using newline-delimited JSON
(JSONL) over stdin/stdout.

DateGPT v1 intentionally supports exactly one active game session per backend
process. Opening another session replaces the current active session. There is
no protocol-level session_id; persistent play identity is the existing GAME_ID.

## Session lifecycle

open_session mounts one scenario, one prompt bundle, and one GAME_ID. New games
return needs_setup=true; restored games return needs_setup=false.

## Onboarding

The prompt bundle may provide onboarding.md. Runtime.md remains active during
onboarding, while onboarding.md adds the temporary character-creation policy.

The onboarding agent has restricted tools: public scenario read/search plus
scratchpad read/write. It does not receive Save write tools.

For original-character creation, the mutable draft convention is:

```text
scratchpad/onboarding/main_character.md
```

Only onboarding_finalize copies that draft into the compatible Save at:

```text
entities/main_character.md
```

Protocol operations:

- onboarding_start
- onboarding_select_mode
- onboarding_turn
- onboarding_finalize
- get_onboarding_state

Supported modes are original, existing, and observer. Existing mode requires an
exact public Distribution entity path.

Until a dedicated UI is added, normal say/play input also accepts:

```text
!온보딩
!새캐릭터
!기존캐릭터 <Distribution entity path>
!관찰자
!캐릭터확정
```

Other text received while needs_setup=true is routed to onboarding_turn.

## Gameplay context

The engine uses a hybrid context strategy:

1. stable core context
2. exact current-state context
3. agent retrieval tools

An optional scenario context_manifest.json can declare authored files that are
always included after runtime.md and before mutable controls:

```json
{
  "core_files": [
    "entities/characters/main_heroine.md",
    "entities/world/school.md"
  ]
}
```

Those source baselines stay in the cache-friendly system prefix. Save overlays
for the same paths remain dynamic.

When exact paths are known, the engine also preloads the player character,
current scene entity/story/flag/asset files, their Save overlays, scratchpad
working memory, and recent conversation. Everything else is retrieved through
content tools. Vector RAG is deliberately deferred; it can later replace or
augment lexical search behind the same retrieval boundary.

## Gameplay

play (and the compatibility alias say) runs one normal AgentRunner turn.
Current controls may be repeated on every request.

checkpoint runs the runtime semantic save command without appending that
maintenance instruction to ordinary conversation history.

## Errors

Expected failures use stable frontend-facing codes rather than Python exception
class names.
