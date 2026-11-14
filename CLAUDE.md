# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Kinolog is a personal film & book index built over Letterboxd and Goodreads exports. It is a learning project for vector databases, chunking strategies, retrieval evaluation, and RAG/agent loops, so retrieval changes are expected to be measured with the eval harness rather than judged by eye.

## Commands

The package lives under `src/` and is imported as `src.*`, so run everything from the repo root (pytest is configured with `pythonpath = ["."]`; the MCP server needs `PYTHONPATH=.`).

```bash
.venv/bin/pytest -v                                   # full suite (fast, in-memory SQLite)
.venv/bin/pytest tests/test_search.py::test_bm25_search  # single test
ruff check src tests                                  # lint (dev extra; not installed in .venv by default)

python3 -m src.interfaces.cli stats
python3 -m src.interfaces.cli ingest letterboxd data/raw_exports/letterboxd
python3 -m src.interfaces.cli ingest resolve          # needs TMDB_API_KEY
python3 -m src.interfaces.cli ingest review           # interactive match queue
python3 -m src.interfaces.cli ingest enrich
python3 -m src.interfaces.cli ingest chunk --strategy whole
python3 -m src.interfaces.cli ingest embed --model bge_m3 --strategy whole
python3 -m src.interfaces.cli search "journalist in Rome" --mode rrf
python3 -m src.interfaces.cli eval known-items --mode bm25
python3 -m src.interfaces.cli eval hearts --ranker nearest_exemplar --splits 10
python3 -m src.interfaces.mcp_server                  # stdio MCP server (needs `mcp` extra)
```

Every CLI command accepts `--db` (default `data/index.db`) and `-v`. The CLI is plain argparse in `src/interfaces/cli.py` (click/rich are only used for table output when installed); adding a command means adding a subparser, a `handle_*` function, and a dispatch branch in `run_argparse_cli`.

## Architecture

**Pipeline:** loaders → resolvers → enrichers → documents → chunks → embeddings → search/taste → eval & interfaces. Each stage is a separate CLI step and is idempotent, so stages can be re-run independently.

- `src/core/db.py` — the single `Database` class owns the whole schema (created on construction; no migrations). Key relationships: `items` (films and books share one table, discriminated by `item_type`) → `documents` (one per item/source/lang) → `chunks` (one row per document/strategy/ord). `user_status` holds seen/watchlist/liked state; `people`/`credits` hold TMDB crew. All upserts are content-hash based and skip unchanged text.
- **FTS5** `chunks_fts` is an external-content table kept in sync by triggers on `chunks` — never write to it directly.
- **Vectors**: `sqlite-vec` is optional. Each embedding model gets its own `vec0` table named `vec_<model_name>` (e.g. `vec_bge_m3`, 1024-dim; `multilingual_e5`, 768-dim, uses `query: `/`passage: ` prefixes). When the extension fails to load, `db.vec_available` is False and vector search returns `[]` instead of raising — keep that graceful-degradation behavior.
- **Chunking strategies** (`src/core/chunkers.py` `STRATEGIES`): `whole`, `fixed_256_50`, `fixed_512_100`, `section`, `section_no_prefix`. The strategy name is stored on each chunk, and embeddings/search are always scoped to one strategy, so multiple strategies coexist in the DB for comparison.
- **Search** (`src/core/search.py`): `search_bm25`, `search_vector`, `search_rrf` (reciprocal rank fusion), plus a `search()` dispatcher by mode. Results are deduped to one per item. `SearchFilters` builds SQL conditions for item type/decade and `user_status` joins.
- **Taste** (`src/core/taste.py` `RANKERS`): rank unseen/watchlist candidates by similarity to hearted ("liked") item embeddings — `mean_heart`, `nearest_exemplar`, `top_3_mean`, `prototypes_4..6` (k-means). Letterboxd likes are dated; `first_heart_date` restricts the Positive-Unlabeled evaluation to candidates seen after hearts started being used.
- **Ingest**: `letterboxd.py`/`goodreads.py` load exports; `resolvers/` match items to TMDB (multi-language, year drift ±1/±2, alt titles) or Open Library; low-confidence matches go to `match_review_queue` and are resolved via `review_cli.py`. `enrichers/` add TMDB metadata/credits, Wikipedia sections (via Wikidata sitelinks, EN/FR/IT), and subtitles (scene-level chunks with `start_ms`/`end_ms`). External API responses are disk-cached under `data/cache/<source>/` and tracked in `raw_cache`.
- **Eval** (`src/eval/`): `harness.py` runs known-item retrieval (`datasets/known_items.json`, Hit@k/MRR) and hearts recall (multi-split Recall@20/50, MRR with stdev); results are written to the `eval_runs` table via `log_results`. `adaptation.py` (book↔film cross-modal retrieval), `faithfulness.py` (`datasets/faithfulness_prompts.json`, groundedness/citations), and `vector_stores.py` (store benchmarks) are separate suites; shared metrics are in `metrics.py`.
- **Interfaces**: `mcp_server.py` wraps the core in a `KinologServer.handle_tool` dispatcher (tools: `search`, `rank_watchlist`, `similar_to`, `filmography`, `crew_overlap`, `stats`) so tool logic is testable without the `mcp` package; `chat/agent.py` assembles retrieved chunks under a token budget with numbered citations.

## Conventions

- Tests build fixtures against `Database(":memory:")` with hand-inserted items/documents; none of them call external APIs or load embedding models, which keeps the suite under a second.
- `data/raw_exports/`, `data/cache/`, and `data/*.db` are gitignored personal data — don't commit them.
- Ruff: line length 100, target py311, rules `E,F,I,N,W,UP`.
