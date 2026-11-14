# Kinolog web UI: implementation plan (DRAFT, not implemented)

Status: reviewed; all decisions recorded in section 9. Nothing in `src/` has changed;
items marked **[BLOCKER]** or **[DEP]** need an answer or a separate piece of work first.

---

## 0. What I read and what I found

Files read: `CLAUDE.md`, `pyproject.toml`, `src/core/db.py`, `src/core/search.py`,
`src/core/taste.py`, `src/core/crew.py`, `src/interfaces/cli.py`, `src/interfaces/mcp_server.py`,
`src/interfaces/chat/agent.py`, `src/ingest/letterboxd.py`, `src/ingest/enrichers/tmdb.py`,
`src/eval/harness.py`, `src/eval/faithfulness.py`, `.gitignore`.

Findings that shape the plan (each one becomes a commit or an open question):

| # | Finding | Consequence |
|---|---------|-------------|
| F1 | **The five screenshots did not come through** with the request. | Design tokens in section 4 are provisional names plus placeholder values. Screen layouts are inferred from the screen names. Please re-attach. |
| F2 | The chat agent lives at `src/interfaces/chat/agent.py`, not `src/chat/agent.py` (CLAUDE.md is also slightly off). | Plan references the real path. |
| F3 | `src/core/collections.py` does not exist yet. `src/core/crew.py` has `filmography()` and `directors_by_heart_count()` which are close but return no completion %, no delta, and are per-person N+1 queries. | Section 2.0 lists the exact contract the UI needs. **[DEP]** |
| F4 | **No structured runtime.** Runtime only exists inside TMDB document text (`"Runtime: 94 minutes"`, `tmdb.py:89`). `items` has no runtime, genres, country, language, or poster columns. `SearchFilters.country/language` exist but `to_sql_conditions` ignores them. | "90-minute" constraints need an `items.runtime_min` column populated by the TMDB enricher plus a one-off backfill from existing documents. **[DEP]** |
| F5 | **No ratings, no diary entries.** `user_status` is one row per item: `seen, seen_date, on_watchlist, liked, liked_date, source`. The Letterboxd loader reads `diary.csv` only to set `seen`; it drops `Rating`, `Rewatch`, `Tags`, and never reads `ratings.csv`. Watchlist `Date` (date added) is also dropped. | Watching Log needs a new `watch_log` table, and the loader needs to keep rating/rewatch/added-date. |
| F6 | **Re-import clobbers manual edits.** `upsert_user_status` overwrites whatever fields it is given and stamps `source='letterboxd'`. A film removed from the queue in the UI comes back on next import if still on the Letterboxd watchlist; a manually deleted log entry would be resurrected; `seen_date` ends as whichever diary row came last, not the latest. | Section 5 defines provenance and tombstone rules. |
| F7 | `sqlite3.connect()` uses `check_same_thread=True`. FastAPI runs sync handlers in a threadpool and `TestClient` runs the app in a portal thread, so a shared `Database` will raise `ProgrammingError`. | `Database.__init__` gets a `check_same_thread: bool = True` kwarg (default unchanged); the web app passes `False` and serializes writes with a lock. |
| F8 | `KinologChatAgent.answer_query` hardcodes `limit=10`, takes no `SearchFilters`, defaults to BM25, and checks grounding by regexing **every item title in the DB** against the answer. | Concierge needs `filters`, `results` (pre-retrieved), and a scoped mention check. Small, testable agent changes. |
| F9 | `_format_fts_query` ORs every token. "under 90 minutes" would match the literal `"Runtime: 90 minutes"` text in TMDB docs. | Constraint phrases must be stripped from the residual query before BM25. |
| F10 | `KinologServer._rank_watchlist` has inline SQL for watchlist/heart ids; `mcp_server.py` has no `--db` flag and duplicated imports. | Move id lookups into `Database` (`get_watchlist_ids`, `get_heart_ids`) and reuse from both interfaces. Don't fix unrelated lint in passing. |
| F11 | No `.venv` and no `pytest` in this container, so I could not confirm the suite is green today. | First implementation step: create venv, `pip install -e .[dev]`, record baseline. |
| F12 | Branch question resolved. | Work happens on `claude/optimistic-dirac-912huk`, based on `main`. |

---

## 1. Stack

**Recommendation: FastAPI + uvicorn, vanilla HTML/CSS/ES-module JS, no build step, no Node.**

- New optional extra in `pyproject.toml`, matching how `mcp` is declared:
  ```toml
  web = ["fastapi>=0.110", "uvicorn>=0.29", "python-multipart>=0.0.9"]
  llm = ["anthropic>=1.0"]          # optional, only for LLM-written rationales
  ```
  `python-multipart` is required for the CSV/zip upload endpoint. `httpx` is already a core
  dependency, which `TestClient` needs.
- Entry point: `python3 -m src.interfaces.web [--db data/index.db] [--host 127.0.0.1] [--port 8765]
  [--no-model] [-v]`, implemented in `src/interfaces/web/__main__.py` with argparse (same style as
  `cli.py`). No click.
- `create_app(db: Database | str = "data/index.db", *, load_model: bool = True, generator=None)`
  factory so tests inject an in-memory DB, no model and a fake generator.
- Static files served by `StaticFiles` from `src/interfaces/web/static/`. Hash router in JS
  (`#/collections`, `#/watchlist`, `#/log`, `#/concierge`), so the server only needs one HTML route.
- Embedding model is lazy-loaded on first vector query (same pattern as `KinologServer._get_model`),
  skipped entirely with `--no-model`. `/api/health` reports what is available.
- Why not alternatives: Flask/stdlib `http.server` would work, but FastAPI gives typed request
  models, `TestClient`, and multipart handling for the cost of one extra. HTMX would also be
  no-build, but the screens are mostly read-only lists with a few mutations, so plain `fetch` is
  enough and keeps one less dependency.

### File tree (new and touched files)

```
pyproject.toml                         # + web, llm extras
src/core/db.py                         # check_same_thread kwarg, _ensure_column, watch_log,
                                       #   user-action methods (section 5)
src/core/search.py                     # SearchFilters: runtime_min/max, item_ids, exclude_ids
src/core/collections.py                # [DEP] owned by the director-completion work
src/core/concierge.py                  # NEW: parse_constraints, pick(), template rationale
src/ingest/letterboxd.py               # keep rating/rewatch/added-date; respect manual overrides
src/ingest/enrichers/tmdb.py           # write items.runtime_min
src/interfaces/chat/agent.py           # filters/results params, scoped grounding, citation check
src/interfaces/web/__init__.py
src/interfaces/web/__main__.py         # argparse, loopback guard, uvicorn.run
src/interfaces/web/app.py              # create_app, deps, error handlers, static mount
src/interfaces/web/schemas.py          # pydantic response/request models
src/interfaces/web/routes/
    health.py  collections.py  watchlist.py  log.py  concierge.py  items.py
src/interfaces/web/llm.py              # optional Anthropic generator_fn (only if `llm` extra)
src/interfaces/web/static/
    index.html
    css/tokens.css  css/base.css  css/components.css
    js/app.js  js/api.js  js/router.js  js/placeholder-art.js
    js/views/collections.js  watchlist.js  log.js  concierge.js
src/eval/concierge.py                  # NEW eval suite
src/eval/datasets/concierge_prompts.json
tests/test_db_user_actions.py          # no fastapi needed
tests/test_concierge_core.py           # no fastapi needed
tests/web/conftest.py                  # importorskip("fastapi"), seeded :memory: DB, client
tests/web/test_health.py  test_collections.py  test_watchlist.py
tests/web/test_log.py  test_import.py  test_concierge.py  test_static.py  test_main.py
tests/test_eval_concierge.py
docs/web-ui-plan.md                    # this file
```

---

## 2. Screens, in build order

Common response conventions: JSON, `snake_case`, item ids are `items.id`. Errors are
`{"error": {"code": str, "message": str}}` with 4xx status. Lists use `limit`/`offset` and return
`total`. Every item card carries the same `ItemCard` shape:

```jsonc
ItemCard = {
  "item_id": 12, "title": "...", "year": 1960, "item_type": "film",
  "runtime_min": 94 | null,
  "directors": [{"person_id": 3, "name": "..."}],
  "status": {"seen": true, "on_watchlist": false, "liked": true,
             "rating": 8 | null,            // half-stars 1..10 (Letterboxd 0.5..5)
             "last_watched_on": "2024-05-01" | null}
}
```

### 2.0 Contract needed from `src/core/collections.py` **[DEP]**

The UI treats these as inputs. Names are a proposal; what matters is the fields.

```python
@dataclass
class DirectorFilm:
    item_id: int; title: str; year: int | None; runtime_min: int | None
    seen: bool; liked: bool; on_watchlist: bool; rating: int | None

@dataclass
class DirectorCompletion:
    person_id: int; name: str
    seen: int; total: int; pct: float          # pct in [0, 100], total > 0
    hearted: int                                # liked films by this director
    unseen_on_watchlist: int
    films: list[DirectorFilm] | None = None     # populated only by the detail call

@dataclass
class CompletionDelta:
    person_id: int; name: str
    seen: int; total: int
    before_pct: float; after_pct: float         # "pushes X% -> Y%"

def director_completion(db, *, role="Director", min_films=2, item_type="film",
                        sort="pct"|"hearted"|"name"|"remaining", limit=None
                        ) -> list[DirectorCompletion]
def director_detail(db, person_id: int, role="Director") -> DirectorCompletion | None
def completion_deltas(db, item_ids: list[int], role="Director"
                      ) -> dict[int, list[CompletionDelta]]   # batched; [] if no credits
```

Things I need the backend work to decide or provide (flag list):

1. **Batched deltas.** Watch List and Concierge show deltas for 20-200 items per page; a per-item
   function means N+1 queries. `completion_deltas(item_ids)` must be one or two queries.
2. **Denominator definition (decided).** `total` = films by this director that are in the index,
   with no TMDB filmography fetch.
3. **Exclusion rules (decided).** Exclude shorts (`runtime_min <= 40`) and TV (`items.is_tv = 1`)
   from `seen`, `total` and deltas; count films with unknown runtime. Requires the `runtime_min`
   and `is_tv` columns from commits 3 and 8.
4. **Delta for already-seen items** should be `[]` (or `before == after`), never negative.
5. `runtime_min` and `rating` on `DirectorFilm` depend on the schema additions in this plan; the
   backend should read them if present and return `None` otherwise.
6. Sorting by "remaining" (`total - seen`) for a "closest to complete" view.

### 2.1 Collections (SQL only, no embeddings)

| Method | Path | Query/body | Response | Core function |
|---|---|---|---|---|
| GET | `/api/collections/directors` | `sort`, `min_films`, `limit`, `offset` | `{total, items: [DirectorSummary]}` | `collections.director_completion` |
| GET | `/api/collections/directors/{person_id}` | | `DirectorDetail` | `collections.director_detail` |

```jsonc
DirectorSummary = {"person_id": 3, "name": "...", "seen": 7, "total": 11, "pct": 63.6,
                   "hearted": 4, "unseen_on_watchlist": 2}
DirectorDetail  = DirectorSummary + {"films": [ItemCard + {"delta": CompletionDelta | null}]}
```

UI: grid of director cards (name in serif display, `seen/total` in monospace, progress bar in the
accent color), detail view lists films with seen/unseen state and a "Queue" button on unseen ones.
Empty state when no credits exist: "Run `ingest enrich` to load crew".

### 2.2 Watch List (SQL only; taste score optional)

| Method | Path | Query/body | Response | Core function |
|---|---|---|---|---|
| GET | `/api/watchlist` | `sort=added\|runtime\|year\|completion\|taste`, `runtime_max`, `decade`, `limit`, `offset` | `{total, taste_available, items: [WatchlistRow]}` | `Database.get_watchlist(...)` (new), `collections.completion_deltas`, `taste.RANKERS[...]` (only for `sort=taste`) |
| POST | `/api/watchlist` | `{item_id}` | `ItemCard` | `Database.set_watchlist(item_id, True)` |
| DELETE | `/api/watchlist/{item_id}` | | `ItemCard` | `Database.set_watchlist(item_id, False)` |
| POST | `/api/watchlist/{item_id}/watched` | `{watched_on?, rating?, liked?, keep_on_watchlist=false}` | `{entry: LogEntry, item: ItemCard}` | `Database.log_watch(...)` |
| GET | `/api/items/lookup` | `q` (title prefix), `limit` | `[ItemCard]` | `Database.find_items_by_title` (new, `LIKE`) |
| GET | `/api/items/{item_id}` | | `ItemCard + {sources: [str]}` | `Database.get_item_card` (new) |

```jsonc
WatchlistRow = ItemCard + {"added_at": "2023-02-11" | null,
                           "completion": [CompletionDelta],
                           "taste": {"score": 0.71, "ranker": "nearest_exemplar"} | null}
```

`sort=taste` returns `409 {"code": "taste_unavailable"}` when `vec_available` is false, no model,
or no hearts with embeddings; the UI hides that sort option based on `/api/health`. Taste scores are
cached in-process keyed by `(ranker, strategy, hash(heart_ids), hash(watchlist_ids))` and
invalidated by any mutation.

### 2.3 Watching Log (SQL + CSV import)

| Method | Path | Query/body | Response | Core function |
|---|---|---|---|---|
| GET | `/api/log` | `year`, `month`, `limit`, `offset` | `{total, entries: [LogEntry], summary: LogSummary}` | `Database.get_watch_log(...)` (new) |
| POST | `/api/log` | `{item_id, watched_on, rating?, liked?, rewatch?}` | `LogEntry` | `Database.log_watch` |
| PATCH | `/api/log/{entry_id}` | `{watched_on?, rating?, liked?, rewatch?}` | `LogEntry` | `Database.update_watch` |
| DELETE | `/api/log/{entry_id}` | | `204` | `Database.delete_watch` (soft) |
| PUT | `/api/items/{item_id}/rating` | `{rating: 1..10 \| null}` | `ItemCard` | `Database.set_rating` |
| PUT | `/api/items/{item_id}/liked` | `{liked: bool}` | `ItemCard` | `Database.set_liked` |
| POST | `/api/import/letterboxd` | multipart `file` (`.zip` or a single `.csv`) | `ImportStats` | `letterboxd.load_letterboxd` |

```jsonc
LogEntry   = {"entry_id": 5, "item": ItemCard, "watched_on": "2024-05-01",
              "rating": 8 | null, "liked": true, "rewatch": false,
              "source": "letterboxd" | "manual"}
LogSummary = {"count": 212, "avg_rating": 7.1 | null,
              "by_month": [{"month": "2024-05", "count": 9}]}
ImportStats = {"watched": 0, "watchlist": 0, "likes": 0, "diary": 0,
               "skipped_manual_override": 0, "first_heart_date": "2019-03-02" | null}
```

**Import reuses the existing loader, no new parser.** The endpoint writes the upload into a
`tempfile.TemporaryDirectory()`:
- `.zip`: saved as `letterboxd-upload.zip`; `find_csvs` already extracts zips.
- single `.csv`: saved under its canonical name, chosen from the filename (`diary.csv`,
  `watched.csv`, `watchlist.csv`, `likes/films.csv`, `ratings.csv`); unknown names return `422`.

Then `load_letterboxd(db, tmpdir)` is called unchanged in signature. The loader itself gains
rating/rewatch/added-date handling and override rules (section 5), which the CLI also benefits from.
Upload size cap (e.g. 20 MB) and zip-slip protection: `find_csvs` uses `zf.extractall`, so the
endpoint should validate member names before calling it (no absolute paths, no `..`).

### 2.4 Concierge (search + taste + agent)

| Method | Path | Query/body | Response | Core function |
|---|---|---|---|---|
| GET | `/api/concierge/suggestions` | | `{prompts: [str]}` | templated from data (`directors_by_heart_count`, watchlist stats) |
| POST | `/api/concierge/parse` | `{query}` | `ParsedQuery` | `concierge.parse_constraints` (debug + "chips" in UI) |
| POST | `/api/concierge` | `{query, limit=5, scope="unseen"\|"watchlist"\|"all"}` | `ConciergeResponse` | `concierge.pick` -> `search.search`, `taste.RANKERS`, `collections.completion_deltas`, `agent.assemble_context` / `KinologChatAgent.answer_query` |

```jsonc
ParsedQuery = {"residual_query": "slow italian drama",
               "filters": {"item_type": "film", "seen": false, "decade": 1960,
                           "runtime_max": 100, "on_watchlist": null},
               "chips": [{"kind": "runtime_max", "label": "<= 100 min", "source_span": [0, 12]}],
               "unparsed": []}

ConciergeResponse = {
  "parsed": ParsedQuery,
  "mode_used": "rrf" | "bm25",
  "degraded": ["no_vector: sqlite-vec unavailable", "no_llm: template rationale"],
  "picks": [{
    "item": ItemCard,
    "score": 0.034,
    "score_parts": {"retrieval": 0.031, "taste": 0.64 | null, "completion_boost": 0.003},
    "completion": [CompletionDelta],
    "rationale": {
      "text": "Fits a night under 100 minutes ... [1] ... [2]",
      "generator": "template" | "llm",
      "citations": [{"n": 1, "chunk_id": 88, "item_id": 12, "title": "...", "year": 1960,
                     "section_name": "Plot" | null, "source": "wikipedia" | "tmdb" | ...,
                     "snippet": "first 240 chars"}],
      "groundedness": 1.0,
      "facts": [{"label": "Runtime", "value": "94 min", "from": "items.runtime_min"}]
    }
  }]
}
```

Design details in section 3.

---

## 3. Concierge design

### 3.1 Constraints -> filters

`concierge.parse_constraints(text) -> ParsedQuery` is deterministic (regex + small lexicons), with
no LLM, so it is testable and works offline.

| Phrase family | Becomes | Where applied |
|---|---|---|
| "90 minutes", "under 1h30", "short", "< 2 hours" | `runtime_max` (and `runtime_min` for "at least") | **SQL** via new `SearchFilters.runtime_min/max` on `items.runtime_min` |
| "60s", "1960s", "from the sixties" | `decade` | SQL (exists) |
| "before 1970", "after 2000" | `year_max` / `year_min` | SQL (exists) |
| "book", "novel" / "film", "movie" | `item_type` | SQL (exists) |
| "haven't seen", default for Concierge | `seen=False` | SQL (exists) |
| "from my watchlist" | `on_watchlist=True` | SQL (exists) |
| "Italian", "French", country names | `language`/`country` | **Deferred**: fields exist but no columns (F4). Kept in `residual_query` so BM25 still matches "Language: Italian" in TMDB docs. Flagged in `unparsed`. |
| "light", "something sad", "like Antonioni" | residual query | retrieval |

Rules:
- Matched constraint spans are removed from `residual_query` (F9). If the residual is empty
  (e.g. "something under 90 minutes"), retrieval falls back to taste-only ranking over the filtered
  candidate set.
- Items with `runtime_min IS NULL`: excluded when a runtime constraint is present (strict), and
  counted in the response as `excluded_unknown_runtime` so the UI can say so. (Q5.)
- **Runtime filter fallback** if `items.runtime_min` is not yet populated: a runtime post-filter
  that parses `Runtime: (\d+) minutes` from the item's TMDB document. Only as a bridge until the
  backfill commit lands; tested, then removed.

### 3.2 Pipeline (`concierge.pick`)

1. `parse_constraints` -> `SearchFilters` (+ `scope` sets `seen`/`on_watchlist`).
2. Retrieval: `search.search(db, residual, model, mode, limit=50, filters=f)`.
   `mode = "rrf"` if `db.vec_available` and the model loaded, else `"bm25"`; reason recorded in
   `degraded`.
3. Optional rerank: `score = retrieval_rank_score + w_taste * taste + w_comp * completion_gain`,
   where taste comes from the configured `RANKERS` entry over the retrieved candidates only (cheap),
   and `completion_gain = max(after_pct - before_pct)`. Weights default to `w_taste=0.0`,
   `w_comp=0.0` until the eval in 3.5 justifies non-zero values. This keeps the first version a
   pure retrieval baseline.
4. Top `limit` picks.
5. **Rationale per pick, grounded through the existing agent path**:
   - Item-scoped retrieval: `search_bm25`/`search_rrf` with `SearchFilters(item_ids=[pick_id])`
     and the residual query, `dedupe_items=False`, giving the pick's most relevant chunks.
   - `agent.assemble_context(results, token_budget=600)` -> numbered citations `[^n]`.
   - Generation through `KinologChatAgent.answer_query(question, results=..., generator_fn=...)`
     (new `results`/`filters` params so it does not re-retrieve).
   - **Template generator (default)**: deterministic text built only from (a) the cited chunk
     snippets and (b) structured facts from the DB (runtime, year, director, completion delta,
     "you hearted 3 films by X"). Facts are listed in `rationale.facts` with their column of origin;
     they are not passed off as citations.
   - **LLM generator (optional)**: same context text, prompt requires every claim to carry a `[^n]`
     that exists in the context. Post-check: every `[^n]` must be in range, every mentioned title
     must be in the context (`groundedness == 1.0`, using the scoped mention check from F8).
     If either check fails, discard and fall back to the template, recording
     `degraded: ["llm_ungrounded"]`.
6. UI renders `[^n]` as superscript links that expand the snippet.

### 3.3 Degradation matrix

| Condition | Retrieval | Taste rerank | Rationale | UI signal |
|---|---|---|---|---|
| All available | RRF | if weight > 0 | LLM (validated) | none |
| No LLM key / no `llm` extra | RRF | as above | template | small "template" tag |
| `sqlite-vec` missing or `--no-model` | BM25 | off | template or LLM | banner from `/api/health` |
| No chunks for pick | n/a | n/a | facts-only template, `citations: []` | "no indexed text" |
| No matches | n/a | n/a | n/a | empty state listing which filters cut results |

Vector code must keep the existing behavior: `search_vector` returns `[]` instead of raising.

### 3.4 Optional LLM generator

- `src/interfaces/web/llm.py` builds a `generator_fn(question, context_text) -> str` with the
  official `anthropic` SDK (`anthropic.Anthropic().messages.create(...)`), only if the `llm` extra is
  installed and credentials resolve (`ANTHROPIC_API_KEY` or an `ant auth login` profile).
- Model from `KINOLOG_LLM_MODEL`, default `claude-opus-5-5`; low effort and a small `max_tokens`
  since rationales are 2-3 sentences. Check `stop_reason` (including `refusal`) and fall back to the
  template on anything but `end_turn`.
- Privacy: this sends retrieved chunk text and the query to the API. Off unless explicitly enabled
  (`--llm` flag or env var), and `/api/health` shows it. (Q6.)

### 3.5 Measuring Concierge quality (eval harness, not by eye)

New suite `src/eval/concierge.py`, logged through `harness.log_results` with
`suite="concierge"` and a config of `{mode, ranker, w_taste, w_comp, generator, strategy, model}`.
CLI: `python3 -m src.interfaces.cli eval concierge --mode rrf --ranker nearest_exemplar`.

Dataset `src/eval/datasets/concierge_prompts.json`, hand-written against your index:
```json
{"id": "c01", "query": "something under 90 minutes from the 60s I haven't seen",
 "expected_filters": {"runtime_max": 90, "decade": 1960, "seen": false},
 "relevant": [{"title": "...", "year": 1962}], "acceptable": [{"title": "...", "year": 1964}]}
```

Metrics:
1. **Parser accuracy**: exact match of `expected_filters` (per field and whole-query).
2. **Constraint satisfaction@k**: share of returned picks that satisfy hard constraints. Must be
   100%; any lower is a bug, and the test suite asserts it on fixtures.
3. **Hit@k / MRR / nDCG@5** against `relevant` (graded with `acceptable`), reusing `metrics.py`.
4. **Hearts PU check**: reuse the `eval_hearts_recall` split logic: hide a fraction of hearts,
   mark them unseen, run constraint-free prompts derived from their own chunks' themes, and measure
   whether held-out hearts surface at k=5/10 across splits (mean and stdev). This is how a taste
   weight > 0 earns its place.
5. **Rationale faithfulness**: `groundedness`, citation-validity rate (all `[^n]` resolve), and
   share of LLM answers that fell back to template. Reuses `faithfulness.py` logic.

Ablations to run before changing defaults: BM25 vs RRF; `w_taste` in {0, 0.25, 0.5}; `w_comp` in
{0, 0.1}; strategy `whole` vs `section`. Defaults change only when a run in `eval_runs` shows a gain
beyond the split stdev.

---

## 4. Design system

**Blocked on F1 (screenshots missing).** The structure below is ready; values are placeholders
derived from your description and will be re-sampled from the screenshots once re-attached.

`static/css/tokens.css`:
```css
:root {
  /* color */
  --color-bg: #f6f2ea;            /* warm off-white */
  --color-surface: #fbf8f2;       /* cards */
  --color-ink: #1b1a17;           /* text, primary buttons */
  --color-ink-muted: #6d675d;
  --color-rule: #e3ddd2;          /* hairlines, card borders */
  --color-accent: #d6461f;        /* the single red-orange */
  --color-accent-soft: #f6d9cf;   /* progress track, chips */
  --color-on-ink: #fbf8f2;        /* text on black buttons */
  /* type: system stacks only, no web-font CDN (local + private) */
  --font-display: "Iowan Old Style", "Charter", "Georgia", serif;
  --font-body: system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, "SFMono-Regular", "Menlo", "Consolas", monospace;
  --text-xs: .75rem; --text-sm: .875rem; --text-md: 1rem; --text-lg: 1.25rem;
  --text-xl: 1.75rem; --text-display: 2.5rem;
  /* shape */
  --radius-card: 10px; --radius-pill: 999px; --radius-btn: 8px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-6: 24px; --space-8: 32px;
  --shadow-card: 0 1px 0 var(--color-rule);
  --progress-h: 6px;
}
```
Components (`components.css`): `.card`, `.btn` (black primary: `--color-ink` bg, `--color-on-ink`
text), `.btn--ghost`, `.chip`, `.progress` (track `--color-accent-soft`, fill `--color-accent`),
`.num` (`font-family: var(--font-mono); font-variant-numeric: tabular-nums`) for all counts,
percentages, runtimes, dates, `.poster` placeholder. Layout works down to 360px wide.

**Not copying the mock:**
- Screenshots are reference only and are never committed (add `docs/design-ref/` to `.gitignore`
  if you want them local).
- Only tokens (colors, scale, radius, spacing) are extracted; layout is rebuilt from the screen
  requirements, not traced.
- All microcopy, headings, empty states and example prompts are written fresh; sample titles in
  fixtures are invented or public-domain-safe and never taken from the mock.
- **Placeholder art**: `placeholder-art.js` renders an inline SVG per item: background from a
  deterministic hash of `item_id` into a fixed 6-color palette derived from the tokens, the title
  initials in the display serif, and the year in mono. No TMDB posters, no network fetches, no
  bundled images.

---

## 5. Mutations and re-import consistency

All writes go through new `Database` methods (no SQL in handlers):

```python
def set_watchlist(self, item_id: int, on: bool, *, at: str | None = None) -> None
def log_watch(self, item_id: int, watched_on: str, *, rating: int | None = None,
              liked: bool | None = None, rewatch: bool = False,
              source: str = "manual", source_key: str | None = None) -> int
def update_watch(self, entry_id: int, **fields) -> None
def delete_watch(self, entry_id: int) -> None            # soft delete
def set_rating(self, item_id: int, rating: int | None) -> None   # validates 1..10
def set_liked(self, item_id: int, liked: bool, *, at: str | None = None) -> None
def recompute_user_status(self, item_id: int) -> None     # derives seen/seen_date from watch_log
def get_watchlist(...), get_watch_log(...), get_item_card(...), find_items_by_title(...)
def get_watchlist_ids(self) -> list[int]; def get_heart_ids(self) -> list[int]
```

Schema additions (no migrations exist, so `_init_schema` gains an idempotent `_ensure_column`
helper using `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`):

```sql
-- items
runtime_min INTEGER, is_tv INTEGER DEFAULT 0
-- user_status
rating INTEGER CHECK (rating BETWEEN 1 AND 10),
watchlist_added_at TEXT, watchlist_removed_at TEXT,
manual_updated_at TEXT
-- new
CREATE TABLE IF NOT EXISTS watch_log (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  watched_on TEXT NOT NULL, rating INTEGER, liked INTEGER, rewatch INTEGER DEFAULT 0,
  source TEXT NOT NULL,                  -- 'letterboxd' | 'manual'
  source_key TEXT,                       -- Letterboxd URI + date, NULL for manual
  deleted_at TEXT,                       -- tombstone
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (source, source_key)
);
```

Consistency rules (the point is that re-importing never wipes a manual change):

1. **Log entries are idempotent by `(source, source_key)`.** Letterboxd diary rows get
   `source_key = "<Letterboxd URI>|<Watched Date>"`; re-import upserts the same row, so no
   duplicates. Manual entries have `source='manual'` and are never touched by import.
2. **Deletes are tombstones.** `delete_watch` sets `deleted_at`. Import skips rows whose
   `(source, source_key)` is tombstoned, so a deleted entry stays deleted.
3. **`user_status.seen/seen_date` become derived**: `recompute_user_status` sets `seen` if any
   non-deleted log entry exists or the Letterboxd `watched.csv` says so, and `seen_date = MAX`
   (fixes the last-row-wins bug in F6).
4. **Watchlist**: import sets `on_watchlist=1` only if there is no `watchlist_removed_at` later than
   the row's `Date` (date added). If you remove a film in the UI and later re-add it on Letterboxd,
   the newer Letterboxd date wins. Manual removal sets `watchlist_removed_at`; manual add clears it.
5. **Rating / liked**: import writes them only if `manual_updated_at` is NULL or older than the
   export's row date; UI writes set `manual_updated_at`. `source` stops being overwritten blindly.
6. Every UI write is one transaction (`with db:`), and the in-process taste cache is invalidated.
7. Content-hash upserts (`documents`, `chunks`) are unaffected: user actions never touch
   documents/chunks/embeddings, so no re-chunking or re-embedding is triggered by UI edits.
8. "Log as watched" from the Watch List removes it from the watchlist by default (Q3).

---

## 6. Testing

Principles: `Database(":memory:", check_same_thread=False)`, hand-inserted items/people/credits/
documents/chunks (FTS works in memory, so BM25 paths are real), no vec tables, no model, fake
`generator_fn`. Web tests start with `pytest.importorskip("fastapi")` so the suite stays green
without the `web` extra. Target: whole suite still about 1 second.

Fixture (`tests/web/conftest.py`): 2 directors, ~8 films with runtimes 85-150, mixed
seen/liked/watchlist, TMDB-style docs ("Runtime: N minutes ..."), a stub `collections` if the real
module is not merged yet (behind a `monkeypatch`, removed when it lands).

Test list:

- `tests/test_db.py` (additions): `_ensure_column` is idempotent on a re-opened file DB;
  `check_same_thread=False` allows cross-thread use.
- `tests/test_db_user_actions.py`: set/unset watchlist; log_watch creates entry and sets seen;
  delete_watch tombstones and recomputes seen; seen_date is the max; rating out of range raises;
  set_liked sets liked_date; all writes leave `documents/chunks` row counts unchanged.
- `tests/test_letterboxd.py` (additions): diary rating/rewatch parsed into `watch_log`;
  re-import is idempotent (no duplicate entries); re-import does not resurrect a tombstoned entry;
  re-import does not re-add a manually dequeued film unless the Letterboxd added-date is newer;
  manual rating survives re-import; watchlist added date stored.
- `tests/test_search.py` (additions): `runtime_max`/`runtime_min` filters; `item_ids` filter;
  NULL runtime excluded under a runtime constraint.
- `tests/test_chat_and_subtitles.py` (additions): `answer_query(results=...)` skips retrieval;
  filters forwarded; scoped mention check; out-of-range `[^n]` detected.
- `tests/test_concierge_core.py`: parser table test (~25 phrases incl. "1h30", "under two
  hours", "60s", "sixties", "not seen"); constraint spans removed from residual; empty residual
  falls back to taste/recency ranking; picks always satisfy hard constraints; template rationale
  cites only existing chunks and has groundedness 1.0; ungrounded fake LLM output falls back to
  template; BM25 used when `vec_available` is False.
- `tests/web/test_health.py`: reports `vec_available`, `model_loaded=false`, `llm_configured=false`.
- `tests/web/test_collections.py`: list sorted by pct; detail includes films and deltas;
  unknown person 404; empty DB returns empty list.
- `tests/web/test_watchlist.py`: list, filters, sorts; `sort=taste` returns 409 without vec;
  add/remove; "watched" creates log entry and dequeues; deltas present.
- `tests/web/test_log.py`: list with month filter and summary; create/patch/delete; rating PUT;
  liked PUT; 422 on bad date or rating.
- `tests/web/test_import.py`: upload a tiny `diary.csv` built in memory; upload a zip; unknown csv
  name 422; zip with `../` member rejected; second upload idempotent.
- `tests/web/test_concierge.py`: parse endpoint; full pick in BM25 mode with `degraded` set;
  citations shape; runtime constraint honored; empty result explains which filter cut.
- `tests/web/test_static.py`: `/` serves index.html; `tokens.css` served; no external URLs in
  static files (grep for `http`).
- `tests/web/test_main.py`: argparse defaults (`--db data/index.db`, host `127.0.0.1`); non-loopback
  host refused without `--allow-remote`.
- `tests/test_eval_concierge.py`: suite runs on fixture dataset and produces the expected metric
  names; constraint satisfaction = 100%.

### Manual verification checklist (per screen)

Run `python3 -m src.interfaces.web --db data/index.db`, open `http://127.0.0.1:8765`.

- **Collections**: directors appear with `seen/total` matching `cli filmography "<name>"`; bar width
  matches pct; detail lists films; "Queue" on an unseen film adds it to Watch List; empty state on a
  DB without credits.
- **Watch List**: count matches `cli stats`/SQL; each sort works; runtime filter hides long films;
  delta text "X% -> Y%" appears for films with a known director; "Log as watched" moves the film to
  the Log and out of the list; taste sort hidden when started with `--no-model`.
- **Watching Log**: entries ordered by date; edit rating and date; delete then reload, entry gone;
  import a Letterboxd zip twice and confirm counts do not double; delete an imported entry,
  re-import, it stays deleted; rating changed in UI survives re-import.
- **Concierge**: "something under 90 minutes I haven't seen" shows chips and only <= 90-minute
  unseen films; every `[n]` opens a real snippet; with `--no-model`, banner says BM25 and results
  still appear; without an API key, rationale tagged "template"; nonsense query gives an empty
  state, not an error.
- **Global**: page works at 360px width; no network requests besides `127.0.0.1` in devtools.

---

## 7. Privacy and ops

- Binds to `127.0.0.1` by default. `--host` other than a loopback address is refused unless
  `--allow-remote` is passed, and then a warning is printed (no auth exists).
- No CORS middleware (same-origin only). Mutating endpoints require `Content-Type: application/json`
  (or multipart for import) to blunt cross-site form posts from other local pages.
- No external fetches from the browser: no CDNs, web fonts, or posters. Server only calls out for
  the optional LLM, which is opt-in.
- Uploads go to a `TemporaryDirectory` and are deleted after import; nothing written under the repo
  except the DB itself.
- `.gitignore` already covers `data/raw_exports/`, `data/cache/`, `data/*.db*`. Add
  `docs/design-ref/` (local screenshots) and keep test fixtures synthetic.
- Logging: request log omits query strings for `/api/concierge` at default verbosity (`-v` shows
  them), since queries can be personal.

---

## 8. Risks

1. **Director completion semantics** are decided (index only, no shorts/TV), but percentages
   depend on enrichment coverage: unenriched films have no runtime and cannot be classified.
2. **Runtime coverage**: films never enriched have no runtime and vanish under runtime constraints.
   Mitigation: report the excluded count, and the backfill command.
3. **Schema without migrations**: `ALTER TABLE` on a live personal DB. Mitigation: additive columns
   only, `_ensure_column` tested against a file DB, and a "back up `data/index.db` first" note.
4. **Thread safety**: one SQLite connection shared across threads. Mitigation: `check_same_thread=False`
   + a write lock; reads are fine in WAL mode. Single-user local app, so contention is low.
5. **Model load time** (bge-m3 is large): first vector query can take many seconds. Mitigation: lazy
   load, `--no-model`, health shows status, UI shows "warming up".
6. **Letterboxd loader changes** affect the CLI path too; covered by the re-import tests.
7. **Grounding check by title regex** is fragile for short titles ("M", "Her"). Scoping it to the
   candidate set reduces false positives but does not remove them.
8. **Design fidelity** cannot be checked until screenshots arrive.

---

## 9. Decisions (answered 2026-11-14)

- **Q1. Branch.** `claude/optimistic-dirac-912huk`, based on `main`.
- **Q2. Screenshots.** Will be supplied next session. Section 4 values and layouts stay provisional
  until then; re-sample tokens before commit 10 (`tokens.css`).
- **Q3. Delete.** Agreed: soft-delete a log entry, or remove a film from the watchlist. `items`
  rows are never deleted from the UI.
- **Q4. Completion denominator.** Films in the index only (no TMDB person-filmography fetch).
  Shorts and TV are excluded from both `seen` and `total`:
  - short = `items.runtime_min <= 40` (the common feature-length cutoff);
  - TV = TMDB genre "TV Movie", stored as a new `items.is_tv INTEGER` flag by the TMDB enricher
    (the backfill in commit 8 sets it from existing TMDB documents' "Genres:" line);
  - films with unknown runtime are counted (they cannot be classified), and the detail view marks
    them so missing enrichment is visible.
- **Q5. Unknown runtime.** Agreed: excluded under a runtime constraint, with the excluded count
  reported.
- **Q6. LLM.** Yes: optional LLM rationale ships in v1 (commit 21 is in scope), and sending
  retrieved chunk text to the Anthropic API is acceptable. Still opt-in via flag/env, template
  remains the default and the fallback.
- **Q7. Scope.** Agreed: films only, light theme only for v1. The dark-mode block in `tokens.css`
  is left out.
- **Q8. Rating scale.** Yes: half-stars stored as integers 1..10.

---

## 10. Commit sequence (each leaves the suite green)

0. `chore: record baseline` (venv, `pip install -e .[dev]`, run pytest; no code change, only if
   something needs fixing to get green).
1. `docs: add web UI plan` (this file).
2. `db: add check_same_thread option and _ensure_column helper` + tests.
3. `db: add watch_log table, rating/watchlist dates, runtime_min columns` + tests.
4. `db: add user-action methods and recompute_user_status` + tests.
5. `db: add get_watchlist_ids/get_heart_ids; use them in mcp_server` + tests.
6. `ingest(letterboxd): keep diary rating/rewatch and watchlist added date` + tests.
7. `ingest(letterboxd): respect manual overrides and tombstones on re-import` + tests.
8. `ingest(tmdb): store runtime_min and is_tv; add backfill from existing TMDB documents` + tests.
9. `search: add runtime_min/max and item_ids to SearchFilters` + tests.
10. `build: add web extra; web app skeleton with health, static shell, tokens.css` + tests.
11. `web: Collections endpoints and view` (after `collections.py` lands, or against a stub).
12. `web: Watch List read endpoints and view` + tests.
13. `web: Watch List mutations (queue, dequeue, log as watched)` + tests.
14. `web: Watching Log endpoints and view` + tests.
15. `web: Letterboxd import endpoint` + tests.
16. `chat: answer_query accepts results/filters; scoped grounding; citation check` + tests.
17. `core: concierge constraint parser` + tests.
18. `core: concierge pick pipeline with template rationale` + tests.
19. `web: Concierge endpoints and views` + tests.
20. `eval: concierge suite, dataset scaffold, eval concierge CLI` + tests.
21. `web: optional LLM rationale generator (llm extra)` + tests with fake client.
22. `docs: update CLAUDE.md and README for the web UI` (incl. correcting the agent path).

Each commit passes `pytest` and `ruff check src tests` (E,F,I,N,W,UP, line length 100, py311) on
the files it touches.
