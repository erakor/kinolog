# Kinolog web UI plan (condensed)

Local, single-user web UI over the existing index: Concierge, Watch List, Watching Log,
Collections. FastAPI + a Vite/React/TypeScript frontend, bound to loopback.

> Note: the frontend originally shipped as vanilla ES modules under `static/` with no build step.
> It now lives in `src/interfaces/web/frontend/` and builds to `src/interfaces/web/dist/`; the JSON
> API and visual design are unchanged. Mentions of vanilla JS below describe the original design.

## Decisions

- Branch: work happens on the session branch, based on `main`.
- Soft-delete log entries and watchlist membership. `items` rows are never deleted from the UI.
- Director completion: films in the index only (no TMDB filmography fetch). Shorts
  (`runtime_min <= 40`) and TV movies (`items.is_tv = 1`) are excluded from `seen` and `total`.
  Films with unknown runtime are counted.
- Unknown runtime is excluded under a runtime constraint; the excluded count is reported.
- Optional LLM rationale (opt-in via flag/env, `llm` extra). Template rationale is the default
  and the fallback. Sending chunk text to the Anthropic API is acceptable when enabled.
- Films only, light theme only. Ratings are half-stars stored as integers 1..10.

## Findings that shape the work

- `items` has no runtime, `is_tv`; `user_status` has no rating or watchlist dates; the Letterboxd
  loader drops rating, rewatch and watchlist added date.
- Re-import must not clobber manual edits: log entries are idempotent by `(source, source_key)`,
  deletes are tombstones, manual rating/liked/watchlist changes carry timestamps that imports
  respect.
- `sqlite3` connections are thread-bound; the web app needs `check_same_thread=False` plus a lock.
- `KinologChatAgent.answer_query` needs `results`/`filters` params and a scoped title check.
- Constraint phrases ("90 minutes") must be stripped before BM25 because TMDB documents contain
  the literal text `Runtime: N minutes`.

## Schema additions (idempotent `_ensure_column`)

- `items`: `runtime_min INTEGER`, `is_tv INTEGER DEFAULT 0`
- `user_status`: `rating`, `watchlist_added_at`, `watchlist_removed_at`, `manual_updated_at`
- `watch_log(id, item_id, watched_on, rating, liked, rewatch, source, source_key, deleted_at,
  created_at, updated_at, UNIQUE(source, source_key))`

## API

| Method | Path |
|---|---|
| GET | `/api/health` |
| GET | `/api/collections/directors`, `/api/collections/directors/{person_id}` |
| GET/POST/DELETE | `/api/watchlist`, `/api/watchlist/{item_id}` |
| POST | `/api/watchlist/{item_id}/watched` |
| GET/POST/PATCH/DELETE | `/api/log`, `/api/log/{entry_id}` |
| PUT | `/api/items/{item_id}/rating`, `/api/items/{item_id}/liked` |
| GET | `/api/items/lookup`, `/api/items/{item_id}` |
| POST | `/api/import/letterboxd` |
| GET/POST | `/api/concierge/suggestions`, `/api/concierge/parse`, `/api/concierge` |

## Concierge

Deterministic constraint parser (runtime, decade, year range, type, seen/watchlist scope) strips
matched spans from the query, builds `SearchFilters`, retrieves with RRF (BM25 when vectors or the
model are unavailable), optionally reranks with taste and completion gain (weights default to 0
until the eval justifies otherwise), and attaches a grounded rationale with numbered citations.

Quality is measured with `eval concierge` (parser accuracy, constraint satisfaction@k, Hit@k/MRR,
rationale faithfulness) and logged to `eval_runs`.

## Design

Warm off-white background, serif display type, monospace numerals, a single red-orange accent,
black filled primary buttons, hairline card borders. System font stacks only, no CDNs, no external
images; item art is generated inline SVG. Layouts are rebuilt from requirements, not traced from
reference screenshots, and all copy is original.

## Privacy

Loopback only (`--allow-remote` required otherwise), no CORS, uploads in a temp dir, no external
fetches from the browser, concierge queries not logged by default.

## Commit sequence

See the task list in the session; each commit keeps `pytest` green and lints the files it touches.
