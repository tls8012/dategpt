# DateGPT Backend Protocol

The PySide6 desktop frontend and Python backend communicate using
newline-delimited JSON (JSONL) over stdin/stdout through Qt QProcess.

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

Normal `play` input also accepts the onboarding compatibility commands:

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
2. exact deterministic indexes/pointers
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

### Character manifest index

Distribution character_manifest.md is parsed as a deterministic public index.
The existing line format is used directly:

```text
- 이름 | aliases: 별명1, 별명2 | roles: 직책1, 직책2 | path: entities/characters/...
```

The Save character_manifest.md is applied as a newer overlay by exact entity
path. Name, alias, and role labels are normalized for exact matching only; this
is not fuzzy or semantic search.

When init완료.md Current.present_entities contains names such as:

```text
설연, 남궁휘
```

the engine resolves each unique exact public match and preloads its Distribution
source plus Save entity overlay. Aliases and exact role labels work the same way.
If a public key points to multiple characters, the engine does not guess and
leaves retrieval to the Agent.

The engine also preloads exact non-hidden entity/story/flag/asset paths already
present in Current, the player character, scratchpad working memory, and recent
conversation.

Everything else remains available through content tools. Vector RAG is
deliberately deferred; it can later replace or augment lexical search behind the
same retrieval boundary.

## Gameplay

`play` is the single gameplay text message. Before a gameplay turn reaches
the LLM, deterministic model/control commands are given a chance to handle the
text. Current controls may also be repeated on every request.

Gameplay and onboarding LLM replies use a structured VN response schema. The
validated response contains ordered `segments`; each segment is narration,
dialogue, or system text. Dialogue segments carry the visible speaker name
separately from the text. Every segment also carries an `assets` list containing
zero or more registered asset IDs selected for that presentation unit.

When an emitter is available, a completed structured response is projected onto
the JSONL protocol as:

```text
presentation_start
presentation_segment
presentation_segment
...
presentation_end
reply
```

Each `presentation_segment` is already a frontend display unit, normally one
complete sentence, and may select multiple registered assets. The backend also
adds `resolved_assets` for IDs that resolve to existing local image files.
Each resolved record contains the authored ID/path and a runtime-only
`local_path` for the desktop client. Absolute local paths are never written
back into cartridge manifests or Save data. Unknown/missing IDs are ignored
without failing the text turn.

The final `reply` still includes both flattened `text` and `segments` for compatibility.
Presentation events are emitted only after the single LLM call has completed
and the structured response has been validated; DateGPT does not stream partial
structured output.

Restored `session_opened` events include recent conversation history and the
current rollback turn list so a desktop frontend can reconstruct the visible
state immediately.

`get_controls`, `set_control`, and `set_controls` are deterministic engine
operations and do not call the LLM. `set_controls` accepts a controls object
and is used by the desktop settings panel for language, initiative, and
world_consistency. Scenario-specific controls are also supported as string key/value
pairs. A Distribution may provide their new-game defaults in file-manifest.md
as `control.<key>: <default>`; the active value is persisted without that
prefix in init완료.md and is included in every turn's controls.

A scenario can declare a finite choice set with
`control.<key>.options: value1 | value2 | value3`. The desktop renders such
controls as dropdowns and the backend rejects values outside the declared set.
Controls without `.options` remain free-form text fields.

Finite-choice controls are also eligible for deterministic SCG remapping. If a
character asset manifest has a metadata column with the same name as a declared
control, DateGPT keeps the other character metadata unchanged and resolves the
matching option variant when available. No dedicated hot-swap flag or LLM call
is required. Controls that have no matching asset metadata still work normally
as runtime/LLM controls and do not alter the image.

checkpoint runs the runtime semantic save command without appending that
maintenance instruction to ordinary conversation history.

## Errors

Expected failures use stable frontend-facing codes rather than Python exception
class names.


## Local cartridge installation and mount

Runtime play is local-first. A built Distribution directory can be copied into
the DateGPT cartridge library:

```json
{
  "type": "install_cartridge",
  "source_path": "/path/to/datellm/distribution"
}
```

The parent cartridge directory is also accepted when it contains
`distribution/file-manifest.md`.

Installed layout:

```text
user_data/cartridges/GAME_NAME/BUILD_VERSION/
```

Asset manifests may keep author/source paths such as
`datellm/raw/assets/characters/...`. During installation DateGPT uses
`CONTENT_ROOT` to infer the source repository root, resolves those authored
paths there, and mirrors only referenced image files into the installed
cartridge under the same authored path. This keeps web/build manifests
unchanged while making the local desktop cartridge self-contained.

`assets/` and image files are optional. The installer requires only a valid
`file-manifest.md`; format version 1 is currently supported. Symlinks are
rejected before copying so an installed cartridge cannot escape its source tree.

An installed cartridge can then be mounted without a direct scenario path:

```json
{
  "type": "open_session",
  "game_name": "datellm",
  "build_version": "1",
  "prompt_path": "/path/to/scaffolding"
}
```

When build_version is omitted, the newest installed build is chosen
deterministically. `list_cartridges` reports installed builds.

`list_game_instances` accepts a `game_name` and returns a
`game_instance_list` event with existing GAME_ID values. It is read-only and
does not create or open a save. The desktop launcher uses it to keep New Game
and Continue as separate actions.

Direct `scenario_path` mount remains available for development.


## GitHub source materialization

install_cartridge accepts a local directory or a GitHub HTTPS repository/tree
URL. Example:

```json
{
  "type": "install_cartridge",
  "source": "https://github.com/tls8012/chatgpt_cartridges/tree/main/datellm"
}
```

GitHub sources are materialized with the machine's local `git` executable into
`user_data/sources/`, then passed to the normal local cartridge installer.
DateGPT does not store GitHub credentials. Private repositories work when normal
command-line git access on the machine already works through the user's
credential helper. Credentials embedded in URLs are rejected.

Prompt scaffolding is not fetched at runtime. The source prompt repository
syncs managed files into DateGPT's repository-level `.scaffolding/` directory
through GitHub Actions. DateGPT resolves prompts in this order:

1. explicit `prompt_path`
2. `DATEGPT_PROMPT_DIR`
3. repository `.scaffolding/`

The managed DateGPT copy currently contains only `runtime.md` and
`onboarding.md`.


## DateGPT host adapter

DateGPT consumes the upstream scaffolding and cartridge formats without
rewriting their contracts. The located Distribution directory is mounted
directly as the read-only ScenarioPack; `CONTENT_ROOT` remains cartridge
metadata.

DateGPT does not create or depend on `game_source.md`, because the installed
cartridge and active ScenarioPack already identify the content source. Existing
runtime pointers keep the upstream bare relative form such as
`entities/main_character.md` and `story/전학 첫날.md`. Paths containing
spaces are supported.
