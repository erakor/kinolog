# Repository reorganisation plan

Status: done (executed 2026-11-15, one commit per phase on `claude/quirky-goldberg-23uslx`; see "Deferred / notes"). Written 2026-11-15 against commit `c8a2c1b` (main) plus `b692e10`
(packaging fix on branch `claude/quirky-goldberg-23uslx`).

This plan is meant to be executed by a session that has none of the conversation that produced
it. Read the whole file before starting. Read `CLAUDE.md` too; it describes the system as it is
before this plan.

## Goal

Restructure the code so that:

1. The import package is named `kinolog` and lives in `src/kinolog/` (standard src layout).
   Today the package itself is named `src`.
2. Code depends in one direction only, enforced by a test (see "Layers" below).
3. Each external system (TMDB, Open Library, Wikipedia, subtitles, Letterboxd, Goodreads) lives
   in one folder, instead of being split by pipeline verb (`resolvers/`, `enrichers/`).
4. Each family of compared strategies (chunkers, embedders, taste rankers) is a folder with a
   small protocol and a registry, one file per variant.
5. The CLI, the MCP server and the web routes call one shared `services` module and stay thin.
6. The schema evolves through numbered migrations instead of `_ensure_column`.
7. Only `kinolog.store` writes to the database (INSERT/UPDATE/DELETE). Read queries may stay in
   the modules whose subject they are (BM25 SQL in retrieval, aggregation SQL in collections).
8. `db.py` (1,021 lines) is split by aggregate, behind the same `Database` facade.
9. The Node frontend moves to the top-level `frontend/`.
10. `tests/` mirrors the package.

**This is a pure refactor.** No behaviour, CLI flags, HTTP payloads, MCP tool schemas, SQL
results or eval numbers change. Defaults (`data/index.db`, `data/cache/...`, relative to the
working directory) stay the same. If a step seems to need a behaviour change, stop and ask the
user.

## Ground rules

- One commit per phase (or per numbered sub-step where a phase says so). Every commit leaves the
  full verification suite green. Do not batch phases into one commit.
- Prefer `git mv` for moves so history follows. Make the move and the import rewrite in the same
  commit, but do not mix moves with logic edits in a single file when avoidable: move first, then
  edit, in separate commits if the diff would otherwise be unreadable.
- Do not delete or skip tests to get green. Tests may be moved and their imports rewritten; their
  assertions must not change, except where a phase explicitly says so.
- The test count from Phase 0 is a floor. It may only go up (new layering, migration and services
  tests).
- Commit and push to the branch the session was told to use. Do not open a pull request unless the
  user asks.
- Personal data (`data/raw_exports/`, `data/cache/`, `data/*.db`) is gitignored. Never commit it.
- Update `CLAUDE.md` in the phase that makes a statement in it false, not only at the end, so a
  session that stops halfway leaves accurate docs.

## Verification suite

Run after every phase. All must pass.

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
npm --prefix <frontend dir> run typecheck
npm --prefix <frontend dir> test
npm --prefix <frontend dir> run build
```

Plus these smoke checks (adjust module paths to the phase you are in):

```bash
.venv/bin/kinolog --help
.venv/bin/kinolog stats --db /tmp/kinolog-smoke.db
.venv/bin/python -m <web module> --help
.venv/bin/python -c "import <mcp server module>"
```

And a leftover check: `grep -rn "from src\.\|import src\.\|\"src\.\|src/eval\|src/interfaces" src tests
pyproject.toml CLAUDE.md README.md docs` should return only lines this plan expects (none after
Phase 1, except this file).

## Phase 0: baseline

1. Create the environment if missing:
   `python3 -m venv .venv && .venv/bin/pip install -e '.[dev,web,mcp]'`.
   The `llm` extra and `sentence-transformers` weights are not needed; tests never load models.
   If `sentence-transformers` is slow to install, it is still required by the dependency list, so
   let it install.
2. `npm --prefix src/interfaces/web/frontend ci`.
3. Run the verification suite. Record in the commit message of Phase 1: the pytest pass count,
   skip count, and any pre-existing ruff findings. Pre-existing lint findings are not this plan's
   job; do not let the count grow.
4. Save a schema baseline for Phase 4:
   ```bash
   .venv/bin/python -c "from src.core.db import Database; d=Database('/tmp/baseline.db'); \
   print('\n'.join(r[0] for r in d.conn.execute(\"SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name\")))" \
   > /tmp/schema_baseline.sql
   ```
   Keep `/tmp/baseline.db` too: Phase 4 opens it with the new code to test upgrading an existing
   database. (If `/tmp` is not allowed, use the session scratchpad.)

No commit for Phase 0.

## Phase 1: rename the package to `kinolog`

Mechanical. No file changes other than paths and import strings.

1. `git mv src kinolog_tmp && mkdir src && git mv kinolog_tmp src/kinolog`.
2. Rewrite imports everywhere (`src/`, `tests/`):
   `from src.` → `from kinolog.`, `import src.` → `import kinolog.`. Also string module paths:
   `tests/test_cli.py` runs `python -m src.interfaces.cli` via subprocess (6 places).
3. `pyproject.toml`:
   - `[project.scripts] kinolog = "kinolog.interfaces.cli:cli"`.
   - Replace any `[tool.setuptools.packages.find]` block (commit `b692e10` added one that pins
     the package to `src`) with `where = ["src"]`. Keep `[build-system]` (add it if missing:
     `requires = ["setuptools>=68"]`, `build-backend = "setuptools.build_meta"`).
   - Package data: `"kinolog.eval" = ["datasets/*.json"]`.
   - `[tool.pytest.ini_options]`: remove `pythonpath = ["."]`. Tests now import the installed
     (editable) package. Reinstall: `.venv/bin/pip install -e '.[dev,web,mcp]'`.
4. Fix cwd-relative dataset paths, which break once the package moves:
   `src/kinolog/eval/harness.py` (`"src/eval/datasets/known_items.json"`),
   `eval/concierge.py` and `eval/faithfulness.py` (`PROMPTS_PATH`). Use
   `importlib.resources.files("kinolog.eval") / "datasets" / "<name>.json"`. Keep the `path`
   parameters so callers can still pass a file.
5. Add `src/kinolog/__main__.py` that calls the CLI entry, so `python -m kinolog ...` works.
6. Frontend paths that mention `src/interfaces/web/...` move with the package; nothing to edit yet
   because Vite's `outDir: '../dist'` is relative.
7. `CLAUDE.md` and `README.md`: replace `src.interfaces...` module paths with
   `kinolog.interfaces...`, drop the "needs `PYTHONPATH=.`" note, and change the commands
   section to say `pip install -e .` is required.

Done when: verification suite passes; the wheel (`pip wheel --no-deps -w /tmp/w .`) contains
`kinolog/...` and the three dataset JSON files; `kinolog stats --db /tmp/x.db` works from `/`.

## Phase 2: move the frontend to the top level

1. `git mv src/kinolog/interfaces/web/frontend frontend`.
2. `frontend/vite.config.ts`: `outDir` becomes `'../src/kinolog/interfaces/web/dist'`. Fix the
   comment above it.
3. `src/kinolog/interfaces/web/app.py`: `FRONTEND_DIR` points into the package and is only used by
   `tests/web/test_static.py` (which scans the frontend source for external URLs). Remove
   `FRONTEND_DIR` from `app.py`; in the test, compute the path from the repo root
   (`Path(__file__).resolve().parents[2] / "frontend"`). `DIST_DIR` keeps pointing at
   `interfaces/web/dist`.
4. `.gitignore`: the generic `dist/` rule already covers the build. Check `frontend/.gitignore`
   still makes sense from its new location.
5. Package data for non-editable installs: add `"kinolog.interfaces.web" = ["dist/**/*"]`.
6. Replace every `npm --prefix src/interfaces/web/frontend` with `npm --prefix frontend` in
   `CLAUDE.md`, `README.md` and `docs/`.

Done when: `npm --prefix frontend ci && npm --prefix frontend run build` writes
`src/kinolog/interfaces/web/dist/index.html`, the web tests pass, and `git status` shows no
untracked build output.

## Phase 3: `config.py` and `domain.py`

These two modules sit below every layer, so later phases can import them.

1. `src/kinolog/config.py`. Centralise, with today's defaults:
   - `DATA_DIR = Path("data")`, `DEFAULT_DB_PATH = DATA_DIR / "index.db"`,
     `CACHE_DIR = DATA_DIR / "cache"` (relative to cwd, as today).
   - Per-source cache dirs: `tmdb`, `openlibrary`, `wiki`, `wikidata`, `subs`.
   - `ENV_FILE = Path(".env")` and the TMDB key lookup now in `resolvers/tmdb.py::_get_api_key`.
   - Default model and strategy names (`"bge_m3"`, `"whole"`), default ranker
     (`"nearest_exemplar"`).
   Replace the literals: `CACHE_DIR = Path("data/cache/...")` in four ingest modules, the hardcoded
   `f"data/cache/tmdb/movie_{tmdb_id}.json"` in `ingest/enrichers/tmdb.py`, and the
   `"data/index.db"` defaults in `mcp_server.py`, `web/app.py`, `web/__main__.py`,
   `ingest/review_cli.py`, `interfaces/cli.py` and `core/db.py`.
2. `src/kinolog/domain.py`. Plain dataclasses and constants shared across layers:
   - `Chunk` (from `core/chunkers.py`; `ingest/enrichers/subtitles.py` imports it, and sources
     must not depend on the index layer).
   - `SHORT_MAX_MIN` (from `core/collections.py`; `core/search.py` imports it, which makes
     retrieval depend on a feature).
   - `SearchResult` stays in retrieval (only higher layers use it).
   Leave a re-export in the old location only within this commit if needed to keep it small;
   remove re-exports before the phase ends.

Done when: `grep -rn '"data/' src` only finds `config.py` and help strings.

## Phase 4: `store/` package and migrations

Two commits.

### 4a: split `core/db.py` into `store/` (no behaviour change)

Keep one `Database` class so the ~400 `db.method(...)` call sites in code and tests do not
change. Build it from mixins, one per aggregate:

```
src/kinolog/store/
  __init__.py       # exports Database, NotFoundError, InvalidInputError, content_hash, chunked
  database.py       # class Database(ItemsMixin, DocumentsMixin, ..., ConnectionBase)
  connection.py     # ConnectionBase: __init__, sqlite-vec loading, vec_available, execute,
                    #   executemany, __enter__/__exit__, close; calls migrations.apply()
  errors.py         # NotFoundError, InvalidInputError
  util.py           # _now, chunked, content_hash, _check_date, _check_rating, _title_or_director
  schema.py         # temporary in 4a: _TABLES_SQL, _FTS_SQL, _FTS_TRIGGERS_SQL, _INDEXES_SQL,
                    #   _ADDED_COLUMNS, _init_schema, _ensure_column (replaced in 4b)
  vectors.py        # try_create_vec_table (+ upsert_embedding, added in Phase 9)
  items.py          # upsert_item, get_item, get_items, find_items_by_title, get_item_sources
  documents.py      # upsert_document, upsert_chunk, delete_chunks_for_document
  people.py         # upsert_person, upsert_credit
  ingest_meta.py    # cache_get, cache_put, queue_for_review, get_review_queue, resolve_review
  user_state.py     # upsert_user_status, _ensure_status, set_watchlist, log_watch,
                    #   get_watch_entry, update_watch, delete_watch, set_rating, set_liked,
                    #   recompute_user_status, get_watchlist_ids, get_heart_ids
  views.py          # get_item_cards, _fill_item_cards, get_item_card, get_watchlist,
                    #   watchlist_summary, get_watch_log, _entry_dict, get_watch_entry_view, stats
  eval_runs.py      # log_eval
```

Method bodies move verbatim. Rewrite `from kinolog.core.db import ...` to `from kinolog.store
import ...` everywhere, and delete `core/db.py` and `core/__init__.py`'s re-export. Move
`tests/test_db.py` and `tests/test_db_user_actions.py` to `tests/store/`.

### 4b: numbered migrations

Replace `schema.py` with a migration runner:

```
src/kinolog/store/migrations/
  __init__.py       # apply(conn): run pending migrations in order, track with PRAGMA user_version
  m001_tables.sql   # _TABLES_SQL exactly as today (CREATE TABLE IF NOT EXISTS ...)
  m002_added_columns.py  # the 7 _ADDED_COLUMNS, applied with ensure-column semantics
  m003_fts_and_indexes.sql  # _FTS_SQL + _FTS_TRIGGERS_SQL + _INDEXES_SQL
```

Rules for the runner:
- `PRAGMA user_version` holds the number of the last applied migration. Each migration runs in a
  transaction and bumps it. `executescript` commits implicitly, so for `.sql` files run the script
  and then set `user_version` and commit; idempotent SQL (`IF NOT EXISTS`) makes a crash between the
  two harmless.
- Migrations 001 to 003 must be idempotent, because every existing database (the user's real
  `data/index.db`) has `user_version = 0` but already has all tables and columns. That is why 002 is
  Python (check `PRAGMA table_info` before `ALTER TABLE`). From 004 on, migrations can assume the
  previous state and need not be idempotent.
- `try_create_vec_table` stays dynamic (one table per embedding model), not a migration.
- Remove `SCHEMA_VERSION` from the old module; `user_version` replaces it.
- Ship the `.sql` files as package data (`"kinolog.store" = ["migrations/*.sql"]`).

New tests in `tests/store/test_migrations.py`:
- A fresh database's schema (the `sqlite_master` dump from Phase 0) equals
  `/tmp/schema_baseline.sql`. Commit the baseline as a test fixture,
  `tests/store/fixtures/schema_v3.sql`, and compare against that.
- A database created by the old code (build it in the test by executing the old DDL from the
  fixture without setting `user_version`) opens cleanly, ends at `user_version = 3`, and keeps
  its rows.
- Opening twice is a no-op.
Also open `/tmp/baseline.db` (from Phase 0) with the new code by hand and diff its schema.

Update `CLAUDE.md`: "creates the schema on construction; no migrations" becomes a short
description of `store/migrations/` and the rule "add a new numbered file; never edit an applied
migration".

## Phase 5: split `core/` by layer and add the layering test

Moves (one commit, or one per target package if the diff is large):

| From | To |
|---|---|
| `core/chunkers.py` | `index/chunking/` (split further in Phase 7) |
| `core/embed.py` | `index/embedding/` (split further in Phase 7) |
| `core/search.py` | `retrieval/filters.py` (`SearchFilters`), `retrieval/bm25.py` (`_format_fts_query`, `search_bm25`), `retrieval/vector.py` (`search_vector`), `retrieval/fusion.py` (`search_rrf`, `_dedupe_by_item`), `retrieval/search.py` (`SearchResult`, `search` dispatcher). `retrieval/__init__.py` exports `search`, `SearchFilters`, `SearchResult`, `search_bm25`, `search_vector`, `search_rrf`. |
| `core/grounding.py` | `rag/context.py` (`CITATION_RE`, `RetrievedChunkContext`, `AssembledContext`, `assemble_context`), `rag/grounding.py` (`groundedness`, `MentionScope`, `check_grounding`) |
| `interfaces/chat/agent.py` | `rag/agent.py` |
| `interfaces/web/llm.py` | `rag/llm.py` |
| `core/taste.py` | `taste/` (split further in Phase 7) |
| `interfaces/web/taste.py` | `taste/cache.py`: a `TasteCache` class holding the dict and the `cached_taste_scores` logic. `AppState` owns an instance; `invalidate()` clears it. |
| `core/concierge.py` | `features/concierge/constraints.py` (regexes, `Chip`, `ParsedQuery`, `_Spans`, `_duration_minutes`, `_fmt_minutes`, `parse_constraints`, `to_search_filters`), `features/concierge/rationale.py` (`_snippet`, `_template_text`, `_facts`, `RATIONALE_TOKEN_BUDGET`), `features/concierge/pick.py` (everything else, incl. `pick`, `_explain_empty`). `__init__.py` exports `parse_constraints`, `to_search_filters`, `pick`, `ParsedQuery`, `Chip`. |
| `core/collections.py` | `features/collections.py` |
| `core/crew.py` | `features/crew.py` |
| `core/docfacts.py` | `features/docfacts.py` |

Also:
- `eval/metrics.py` re-exports `groundedness` from grounding. Remove the re-export; callers import
  from `kinolog.rag.grounding`.
- `eval/faithfulness.py` now imports `kinolog.rag.agent`, not an interface.
- `core/` must be empty and deleted at the end.

### Layers

Lower number = lower layer. A module may import from its own top-level subpackage and from any
strictly lower layer, never from the same layer's sibling packages or from higher layers.

| Layer | Packages |
|---|---|
| 0 | `kinolog.config`, `kinolog.domain` |
| 1 | `kinolog.store` |
| 2 | `kinolog.sources`, `kinolog.index` |
| 3 | `kinolog.retrieval` |
| 4 | `kinolog.rag`, `kinolog.taste` |
| 5 | `kinolog.features` |
| 6 | `kinolog.pipeline`, `kinolog.services` |
| 7 | `kinolog.eval` |
| 8 | `kinolog.interfaces` (and `kinolog.__main__`) |

Add `tests/test_layering.py`: walk `src/kinolog/**/*.py` with `ast`, collect every `import` and
`from ... import` (including imports inside functions; the CLI and MCP server import lazily) that
targets `kinolog.*`, map both modules to layers, and fail with a list of violations. Packages
that do not exist yet (for example `sources` before Phase 6) are simply absent from the map.
Expect to find, and fix in this phase, `features.concierge` importing `features.collections`
(allowed: same subpackage `features`), and `index` needing `domain.Chunk` (Phase 3 handled it).

`taste` (layer 4) must not import `retrieval` or `rag`; `features.concierge` receives taste scores
through its existing `taste_fn` parameter, so no change is needed there.

## Phase 6: `sources/` by external system

| From | To |
|---|---|
| `ingest/letterboxd.py` | `sources/letterboxd/load.py` |
| `ingest/goodreads.py` | `sources/goodreads/load.py` |
| `ingest/resolvers/tmdb.py` | `sources/tmdb/client.py` (API key lookup via `config`, HTTP + disk cache, the methods that fetch) and `sources/tmdb/resolve.py` (`TMDBResolver` matching logic, using the client) |
| `ingest/enrichers/tmdb.py` | `sources/tmdb/enrich.py` (uses `client.py`, not `TMDBResolver`, to fetch) |
| `ingest/resolvers/openlibrary.py` | `sources/openlibrary/client.py` + `sources/openlibrary/resolve.py` |
| `ingest/enrichers/wikipedia.py` | `sources/wikipedia/client.py` (`_fetch_wikidata_sitelinks`, `_fetch_wikipedia_sections`) + `sources/wikipedia/enrich.py` (the rest) |
| `ingest/enrichers/subtitles.py` | `sources/subtitles/parse.py` (SRT parsing and scene chunking) + `sources/subtitles/enrich.py` (`load_and_chunk_subtitle_file`) |
| `ingest/review_cli.py` | `interfaces/cli/review.py` (done in Phase 8; leave it in `ingest/` until then if simpler, but `ingest/` must be gone after Phase 8) |

`sources/http_cache.py`: read every source's "check cache file, else fetch, then write JSON"
code first. Extract a shared helper only for the pattern that is actually duplicated; do not
invent an abstraction the sources do not share. Keep cache file names and locations identical,
so the user's existing `data/cache/` stays valid. That compatibility is a hard requirement.

Split the TMDB client out of `TMDBResolver` carefully: `enrich_all` currently receives a resolver
instance from the CLI. Keep the public function signatures the CLI calls working, or update the
CLI call sites in the same commit.

`pipeline.py` (layer 6): move the bodies of the CLI's `handle_ingest_*` functions here as plain
functions (`load_letterboxd(db, path)`, `resolve(db, item_type)`, `enrich(db, item_type)`,
`backfill_runtime(db)`, `chunk(db, strategy, item_type)`, `embed(db, model, strategy, device)`),
returning their stats dicts. The CLI handlers become argument parsing plus printing. The web
import route also calls `pipeline.load_letterboxd`. No new commands.

Move tests: `test_letterboxd.py`, `test_goodreads.py`, `test_tmdb_runtime.py` and the subtitle
half of `test_chat_and_subtitles.py` into `tests/sources/`.

## Phase 7: strategy registries

For each of `index/chunking/`, `index/embedding/`, `taste/`:

- `base.py`: a `Protocol` for the strategy, and a plain `dict` registry with a `register(name)`
  decorator.
- One module per variant. `__init__.py` imports every variant module explicitly (so registration
  never depends on import order elsewhere) and exports the registry.
- Keep the existing public names working: `STRATEGIES` (chunking) and `RANKERS` (taste) remain the
  registry dicts with the same keys; `BGE_M3`, `MultilingualE5`, `embed_chunks`,
  `chunk_document`, `chunk_all_documents`, `taste_scores`, `taste_available`,
  `TasteUnavailableError` keep their names and are exported from the package `__init__`.

Chunking: `whole.py` (`chunk_whole_document`), `fixed.py` (`chunk_fixed_window`, registering
`fixed_256_50` and `fixed_512_100`), `section.py` (`chunk_by_section`, registering `section` and
`section_no_prefix`), `runner.py` (`chunk_document`, `chunk_all_documents`, `_estimate_tokens`).
Check `STRATEGIES` in the current file for the exact parameters each name binds.

Embedding: `base.py` (`EmbeddingModel` protocol), `bge_m3.py`, `e5.py`, `runner.py`
(`embed_chunks`). Add an `EMBEDDERS` registry keyed by model name (`bge_m3`,
`multilingual_e5`) and use it in the CLI instead of its if/else on `--model`.

Taste: `data.py` (`_get_item_embeddings`, `_get_heart_ids`, `_get_candidate_ids`),
`mean.py` (`rank_mean_heart`, `rank_top_k_mean` with `top_3_mean`), `exemplar.py`
(`rank_nearest_exemplar`), `prototypes.py` (`rank_prototypes`, registering `prototypes_4..6`),
`scores.py` (`TasteScore`, `taste_scores`, `taste_available`, `TasteUnavailableError`),
`cache.py` (from Phase 5). Check `RANKERS` for the exact names and partials.

Done when: the registries list the same keys as before (add a test asserting the exact key sets),
and eval output for a fixed in-memory fixture is unchanged (the existing taste and chunker tests
cover this).

## Phase 8: `services.py` and thin interfaces

### 8a: services

`src/kinolog/services.py` (layer 6; split into a `services/` package if it passes ~400 lines).
Functions take `db` (and, where needed, `model`, `taste_fn` or a `TasteCache`) and return plain
dicts, lists or dataclasses. They contain the logic currently duplicated or embedded in the
interfaces:

- From `mcp_server.py`: `search_items`, `rank_watchlist`, `similar_to`, `filmography`,
  `crew_overlap`, `stats`. Return what the MCP handlers return today (`handle_tool` output must
  be byte-for-byte identical; `tests/test_mcp.py` checks it).
- From `web/routes/watchlist.py`: `watchlist_view(db, sort, ..., taste_fn)` including the
  `decorate` and sort logic, `add_to_watchlist`, `remove_from_watchlist`, `log_as_watched`.
- From `web/routes/collections.py` and `concierge.py`: `directors_view`, `director_view`,
  `concierge_suggestions`, `concierge_overview`, `concierge_pick`.
- From `web/routes/items.py` and `log.py`: thin wrappers only where a route does more than call
  one `db` method; otherwise the route keeps calling `db` directly.

Rules: services never raise `HTTPException` and never take the lock. Domain errors
(`NotFoundError`, `InvalidInputError`, `TasteUnavailableError`) propagate; the web layer maps them
to status codes as it does today. Taste cache invalidation stays the web layer's job.

New tests: `tests/test_services.py` covering each service against an in-memory fixture. Most can
be lifted from the existing MCP and web tests' setup.

### 8b: interfaces

```
src/kinolog/interfaces/
  cli/
    __init__.py     # exports cli() for the entry point
    __main__.py     # python -m kinolog.interfaces.cli
    main.py         # build_parser(), run_argparse_cli() dispatch
    output.py       # print_table
    ingest.py       # ingest subcommands -> pipeline
    query.py        # search, filmography, crew-overlap, stats -> services
    eval.py         # eval subcommands -> kinolog.eval
    review.py       # from ingest/review_cli.py
  mcp/
    __init__.py
    __main__.py     # python -m kinolog.interfaces.mcp
    tools.py        # the TOOLS schema list
    server.py       # KinologServer (handle_tool -> services), create_mcp_app
  web/              # unchanged layout; routes call services; taste.py is gone (Phase 5)
```

Keep `python -m kinolog.interfaces.cli`, the `kinolog` script and every subcommand and flag
working exactly as before (`tests/test_cli.py` runs them). Update `CLAUDE.md`'s note on adding a
CLI command (it currently says one file with a dispatch branch).

## Phase 9: database writes only in `store`

Every INSERT/UPDATE/DELETE outside `store/` moves into a named `Database` method. At the time of
writing these are:

- `sources/openlibrary/resolve.py`: 4 `UPDATE items` (set `openlibrary_id` + confidence + status;
  set status `queued`).
- `sources/tmdb/resolve.py`: 3 `UPDATE items` (set `tmdb_id` + status + confidence; set
  `queued`).
- `sources/tmdb/enrich.py`: 6 `UPDATE items` (`runtime_min`, `is_tv`, `original_title`,
  `wikidata_id` only-if-null).
- `index/embedding/runner.py`: `INSERT OR REPLACE INTO vec_<model>`.

Suggested methods: `set_match(item_id, *, tmdb_id=None, openlibrary_id=None, confidence,
status="auto")`, `mark_queued(item_id)`, `set_item_facts(item_id, *, runtime_min=None,
is_tv=None, original_title=None)`, `set_wikidata_id_if_missing(item_id, wikidata_id)`,
`upsert_embedding(model_name, chunk_id, vector)`. Re-grep before starting; the list may have
grown.

Add to `tests/test_layering.py` (or a sibling test): no string literal outside `src/kinolog/store/`
matches `\b(INSERT|UPDATE|DELETE|REPLACE)\s` as SQL. Reads (`SELECT`) stay where they are.

## Phase 10: eval suites and tests layout

1. `eval/`:
   ```
   eval/
     metrics.py
     runner.py          # EvalResult, log_results
     suites/
       known_items.py   # load_known_item_queries, eval_known_items
       hearts.py        # eval_hearts_recall
       concierge.py
       adaptation.py
       faithfulness.py
       vector_stores.py
     datasets/
   ```
   `harness.py` disappears. Its two suites and the shared `EvalResult`/`log_results` split as
   above.
2. `tests/` mirrors the package: `tests/store/`, `tests/sources/`, `tests/index/`,
   `tests/retrieval/`, `tests/rag/`, `tests/taste/`, `tests/features/`, `tests/eval/`,
   `tests/interfaces/` (CLI and MCP), `tests/interfaces/web/` (from `tests/web/`, keeping its
   `conftest.py` and the `importorskip` guards). Split `test_chat_and_subtitles.py` between
   `tests/rag/` and `tests/sources/`.
3. Top-level `tests/conftest.py`: an in-memory `db` fixture and small factories
   (`make_film(db, title, year, **status)`, `make_document(db, item_id, text, source="tmdb")`).
   Use them where they shorten fixtures, but do not rewrite every test to use them.
4. Test files with the same basename in different folders need `__init__.py` in each test
   folder, or pytest's rootdir import mode (`--import-mode=importlib` in `pyproject.toml`).
   Pick one and apply it consistently.

## Phase 11: docs and final checks

1. Rewrite the Architecture section of `CLAUDE.md` around the new tree and the layer table.
   Keep the conventions that still hold (in-memory tests, gitignored personal data, ruff
   settings, graceful sqlite-vec degradation, `db_lock`, rerank weights default to 0).
2. Update `README.md` paths and commands, and `docs/web-ui-plan.md` paths if it references code.
3. Set this file's status line to done and note anything deferred.
4. Final verification suite, plus:
   - `pip wheel --no-deps` contains `kinolog/store/migrations/*.sql`,
     `kinolog/eval/datasets/*.json`.
   - If `data/index.db` exists locally (it does not in a fresh cloud container), run
     `kinolog stats`, `kinolog search "journalist in Rome" --mode bm25` and
     `kinolog eval known-items --mode bm25` against it, and compare with the same commands run
     on `main`. The numbers must be identical.
   - `grep -rn "core\.\|ingest\.\|interfaces\.chat" src tests` finds nothing stale.

## Target tree (end state)

```
kinolog/
├── pyproject.toml
├── frontend/
├── data/                       # gitignored
├── docs/
├── src/kinolog/
│   ├── __main__.py
│   ├── config.py
│   ├── domain.py
│   ├── store/                  # Database facade from mixins, migrations/
│   ├── sources/                # letterboxd/ goodreads/ tmdb/ openlibrary/ wikipedia/ subtitles/
│   ├── index/                  # chunking/ embedding/
│   ├── retrieval/              # filters, bm25, vector, fusion, search
│   ├── rag/                    # context, grounding, agent, llm
│   ├── taste/                  # registry of rankers, scores, cache
│   ├── features/               # concierge/ collections crew docfacts
│   ├── pipeline.py
│   ├── services.py
│   ├── eval/                   # metrics, runner, suites/, datasets/
│   └── interfaces/             # cli/ mcp/ web/
└── tests/                      # mirrors src/kinolog, plus test_layering.py
```

## Risks and how to handle them

- **Existing user database.** The user's real `data/index.db` must open without loss after
  Phase 4. The idempotent migrations 001 to 003 and the upgrade test exist for that. Never write a
  migration that drops or rewrites data as part of this plan.
- **Existing disk cache.** `data/cache/<source>/...` file names must not change (Phase 6).
- **Lazy imports.** The CLI and MCP server import inside functions. `ruff` will not catch a stale
  path there; the layering test's AST walk and `tests/test_cli.py` / `tests/test_mcp.py` will.
  Also grep for string module paths (`"kinolog.` / `"src.`) after each move.
- **Parallel work.** Any branch started before this refactor will conflict heavily. Check with the
  user that nothing is in flight before Phase 1.
- **Scope creep.** Bugs or improvements noticed along the way go in a list at the end of this
  file (or a reply to the user), not into the refactor commits.

## Deferred / notes

Baseline before Phase 1: 235 passed, 1 skipped; 139 ruff findings; 21 frontend tests. End state: 287
passed, 1 skipped; 90 ruff findings (the count only went down: unused-import and import-order fixes
were applied to files that were touched); the same frontend checks pass.

Deviations from the plan, and why:

- `SearchResult` lives in `retrieval/results.py` (re-exported from `retrieval/search.py` and the
  package), because `search.py` imports the BM25, vector and fusion modules, which all need it.
- Phase 8a and 8b are one commit (services and the interface split were done together).
- `RANKERS` key order is now `mean_heart, top_3_mean, nearest_exemplar, prototypes_4..6` (the
  registration order of the modules); the key set is unchanged and pinned by `tests/test_registries.py`.
  Only the "Available: [...]" text of the CLI's unknown-ranker message shows the order.
- `taste_scores` looks up `taste_available` in `taste/scores.py`, so two tests that patched
  `taste.taste_available` also patch `kinolog.taste.scores.taste_available`.
- `eval.metrics` no longer re-exports `groundedness` (as the plan says); `test_metrics.py` and one
  chat test import it from `kinolog.rag.grounding` instead.
- The MCP entry point is now `python -m kinolog.interfaces.mcp` (was `kinolog.interfaces.mcp_server`).
  The README config snippet is updated; an existing MCP client configuration must change its `args`.
- `ingest/review_cli.py` moved straight to `interfaces/cli/review.py` in Phase 8 (it stayed in
  `ingest/` through Phases 6 and 7).
- `tests/web/` moved to `tests/interfaces/web/`; `test_llm.py` was split into a unit test under
  `tests/rag/` and an end-to-end test under `tests/interfaces/web/`.

Verified against `main` (c8a2c1b) on a seeded database: `stats`, `search`, `filmography`, `crew-overlap`,
`eval known-items` and `eval concierge` print identical output from both code bases, and the MCP
`handle_tool` results (search, filmography, crew_overlap, stats, error cases) are byte-identical. A
database created by the old code opens with the new code, ends at `user_version = 3`, and has an
identical schema. There was no real `data/index.db` in the cloud container, so the plan's final
comparison against the user's own index was not run; do it locally.

After the refactor, `main` gained the OMDb ratings enricher (#6) and it was merged in: the OMDb code
lives in `sources/omdb/` (client, enrich), `external_ratings` and `items.imdb_id` come from migration
004 (idempotent, because databases that ran the pre-migration OMDb code already have both), the
ratings queries are in `store/ratings.py`, the `omdb` command is wired through `pipeline.omdb`, and
`get_api_key(var)` is in `config.py`.

Noticed, not changed (out of scope for a pure refactor):

- `create_mcp_app` fails with the installed `mcp` 2.3.0 (`Server` has no `list_tools` decorator). It
  fails the same way on `main`. `KinologServer.handle_tool` and its tests are unaffected.
- sqlite-vec `vec0` tables reject `INSERT OR REPLACE` on an existing `chunk_id` (UNIQUE error), so
  `upsert_embedding` only works for chunks without a vector; `embed_chunks` already skips those.
- `chunk_document` has an unused `c_hash` variable (pre-existing lint finding).
