# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Kinolog is a personal film & book index built over Letterboxd and Goodreads exports. It is a learning project for vector databases, chunking strategies, retrieval evaluation, and RAG/agent loops, so retrieval changes are expected to be measured with the eval harness rather than judged by eye.

## Commands

The package lives in `src/kinolog/` and is imported as `kinolog.*`. Install it first with `pip install -e '.[dev,web,mcp]'` (tests import the installed package; there is no `pythonpath` hack). Run commands from the repo root: the default paths (`data/index.db`, `data/cache/...`) are relative to the working directory. `kinolog <command>` and `python -m kinolog <command>` are equivalent to `python3 -m kinolog.interfaces.cli <command>`.

```bash
.venv/bin/pytest -v                                   # full suite (fast, in-memory SQLite)
.venv/bin/pytest tests/test_search.py::test_bm25_search  # single test
ruff check src tests                                  # lint (dev extra; not installed in .venv by default)

python3 -m kinolog.interfaces.cli stats
python3 -m kinolog.interfaces.cli ingest letterboxd data/raw_exports/letterboxd
python3 -m kinolog.interfaces.cli ingest resolve          # needs TMDB_API_KEY
python3 -m kinolog.interfaces.cli ingest review           # interactive match queue
python3 -m kinolog.interfaces.cli ingest enrich
python3 -m kinolog.interfaces.cli ingest chunk --strategy whole
python3 -m kinolog.interfaces.cli ingest embed --model bge_m3 --strategy whole
python3 -m kinolog.interfaces.cli search "journalist in Rome" --mode rrf
python3 -m kinolog.interfaces.cli eval known-items --mode bm25
python3 -m kinolog.interfaces.cli eval hearts --ranker nearest_exemplar --splits 10
python3 -m kinolog.interfaces.mcp_server                  # stdio MCP server (needs `mcp` extra)
npm --prefix frontend ci && npm --prefix frontend run build  # build the web UI (once, and after frontend changes)
python3 -m kinolog.interfaces.web --db data/index.db      # local web UI (needs `web` extra)
npm --prefix frontend run dev      # UI dev server on 127.0.0.1:5173, proxies /api to :8765
npm --prefix frontend run typecheck && npm --prefix frontend test  # frontend checks (Vitest)
npm --prefix frontend run lint     # oxlint (config: frontend/.oxlintrc.json; warnings only for now)
python3 -m kinolog.interfaces.cli eval concierge --hearts # concierge eval
python3 -m kinolog.interfaces.cli ingest backfill-runtime # runtime_min / is_tv from stored TMDB docs
```

Every CLI command accepts `--db` (default `data/index.db`) and `-v`. The CLI is plain argparse in `src/kinolog/interfaces/cli.py` (click/rich are only used for table output when installed); adding a command means adding a subparser, a `handle_*` function, and a dispatch branch in `run_argparse_cli`.

## Architecture

**Pipeline:** loaders → resolvers → enrichers → documents → chunks → embeddings → search/taste → eval & interfaces. Each stage is a separate CLI step and is idempotent, so stages can be re-run independently.

- `src/kinolog/core/db.py` — the single `Database` class owns the whole schema (created on construction; no migrations). Key relationships: `items` (films and books share one table, discriminated by `item_type`) → `documents` (one per item/source/lang) → `chunks` (one row per document/strategy/ord). `user_status` holds seen/watchlist/liked state; `people`/`credits` hold TMDB crew. All upserts are content-hash based and skip unchanged text.
- **FTS5** `chunks_fts` is an external-content table kept in sync by triggers on `chunks` — never write to it directly.
- **Vectors**: `sqlite-vec` is optional. Each embedding model gets its own `vec0` table named `vec_<model_name>` (e.g. `vec_bge_m3`, 1024-dim; `multilingual_e5`, 768-dim, uses `query: `/`passage: ` prefixes). When the extension fails to load, `db.vec_available` is False and vector search returns `[]` instead of raising — keep that graceful-degradation behavior.
- **Chunking strategies** (`src/kinolog/core/chunkers.py` `STRATEGIES`): `whole`, `fixed_256_50`, `fixed_512_100`, `section`, `section_no_prefix`. The strategy name is stored on each chunk, and embeddings/search are always scoped to one strategy, so multiple strategies coexist in the DB for comparison.
- **Search** (`src/kinolog/core/search.py`): `search_bm25`, `search_vector`, `search_rrf` (reciprocal rank fusion), plus a `search()` dispatcher by mode. Results are deduped to one per item. `SearchFilters` builds SQL conditions for item type/decade and `user_status` joins.
- **Taste** (`src/kinolog/core/taste.py` `RANKERS`): rank unseen/watchlist candidates by similarity to hearted ("liked") item embeddings — `mean_heart`, `nearest_exemplar`, `top_3_mean`, `prototypes_4..6` (k-means). Letterboxd likes are dated; `first_heart_date` restricts the Positive-Unlabeled evaluation to candidates seen after hearts started being used.
- **Ingest**: `letterboxd.py`/`goodreads.py` load exports; `resolvers/` match items to TMDB (multi-language, year drift ±1/±2, alt titles) or Open Library; low-confidence matches go to `match_review_queue` and are resolved via `review_cli.py`. `enrichers/` add TMDB metadata/credits, Wikipedia sections (via Wikidata sitelinks, EN/FR/IT), and subtitles (scene-level chunks with `start_ms`/`end_ms`). External API responses are disk-cached under `data/cache/<source>/` and tracked in `raw_cache`.
- **Eval** (`src/kinolog/eval/`): `harness.py` runs known-item retrieval (`datasets/known_items.json`, Hit@k/MRR) and hearts recall (multi-split Recall@20/50, MRR with stdev); results are written to the `eval_runs` table via `log_results`. `adaptation.py` (book↔film cross-modal retrieval), `faithfulness.py` (`datasets/faithfulness_prompts.json`, groundedness/citations), and `vector_stores.py` (store benchmarks) are separate suites; shared metrics are in `metrics.py`.
- **Interfaces**: `mcp_server.py` wraps the core in a `KinologServer.handle_tool` dispatcher (tools: `search`, `rank_watchlist`, `similar_to`, `filmography`, `crew_overlap`, `stats`) so tool logic is testable without the `mcp` package; `src/kinolog/interfaces/chat/agent.py` assembles retrieved chunks under a token budget with numbered citations; `answer_query` accepts pre-fetched `results`, `filters` and a `mention_scope`, and reports invalid `[^n]` citations.
- **Web UI** (`src/kinolog/interfaces/web/`): FastAPI app factory `create_app(db, load_model=..., generator=...)`, routes under `routes/`, Vite + React + TypeScript frontend under `frontend/` (strict TS, hand-written payload types in `src/types.ts`, hash routes, no router/query libraries, no CDN or external requests; Tailwind CSS v4 via `@tailwindcss/vite` (build-time only); UI primitives are shadcn/ui components copied into `src/components/ui/` (Radix via `radix-ui`, cva, tailwind-merge `cn` in `src/lib/utils.ts`, lucide-react icons, sonner toasts), imported through the `@/` alias (`@/*` -> `src/*`); the shadcn theme variables are mapped onto the Kinolog palette in `frontend/src/styles/tokens.css` (light only; shadcn `accent` is a hover wash, Kinolog's terracotta is `brand`); layout class strings live in `src/components/styles.ts`; `Modal` (Dialog wrapper), `Segmented` (ToggleGroup, `''` mapped to a sentinel), `RatingSelect` (Select, `"none"` sentinel) and `useToast` (sonner) keep their old APIs; Radix Dialog has no Trigger here, so `Modal` restores focus to the opener itself). The build goes to the gitignored `web/dist/`, which FastAPI serves (`/` returns a 503 with the build hint when it is missing); Node is needed to build it. One SQLite connection is shared across threads (`Database(..., check_same_thread=False)`), so all DB access goes through `AppState.db_lock`. Core logic lives outside the web package: `src/kinolog/core/collections.py` (director completion; shorts <= 40 min and `is_tv` excluded, index-only denominator), `src/kinolog/core/concierge.py` (deterministic constraint parser + `pick`), `src/kinolog/core/docfacts.py`. Web tests live in `tests/web/` and skip without the `web` extra.
- **User actions and re-import**: UI writes go through `Database` methods (`set_watchlist`, `log_watch`, `update_watch`, `delete_watch`, `set_rating`, `set_liked`). `watch_log` rows are idempotent by `(source, source_key)`, deletes are tombstones, edited rows are protected, and `user_status.manual_updated_at` / `watchlist_removed_at` stop Letterboxd re-imports from overwriting manual changes. Ratings are half-stars stored as integers 1..10.
- **Concierge**: constraint phrases ("90 minutes", "60s", "haven't seen") become SQL filters and are stripped from the retrieval text; rationales are built from cited chunks and structured facts, and LLM output (optional, `llm` extra) is accepted only if grounded and all citations resolve. Rerank weights `w_taste`/`w_comp` default to 0 until `eval concierge` shows a gain beyond the split stdev.

## Conventions

- Tests build fixtures against `Database(":memory:")` with hand-inserted items/documents; none of them call external APIs or load embedding models, which keeps the suite under a second.
- `data/raw_exports/`, `data/cache/`, and `data/*.db` are gitignored personal data — don't commit them.
- Ruff: line length 100, target py311, rules `E,F,I,N,W,UP`.
