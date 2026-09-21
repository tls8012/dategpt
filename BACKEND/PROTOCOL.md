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

play (and the compatibility alias say) runs one normal AgentRunner turn.
Current controls may be repeated on every request.

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


## Cartridge source of truth

Mounted cartridge content is the Distribution source of truth at runtime.
DateGPT no longer creates or resolves `games/GAME_NAME/game_source.md`.
Scenario content is read directly from the mounted local `ScenarioPack`.
Legacy `game_source` fields in existing `init완료.md` files are accepted
for compatibility and omitted on subsequent renders.
