# Kinolog — Personal Film & Book Index

A personal vector search, ingestion, and evaluation engine built over personal watch/reading history. Designed for hands-on learning of vector databases, chunking strategies, retrieval evaluation, and RAG/agent loops.

## Core Features & Architecture

- **Unified Item Schema**: Generic `items` table supporting both films and books with shared document and chunk hierarchies.
- **SQLite Engine**: Full relational support, WAL mode, foreign keys, external-content FTS5 with insert/update/delete triggers, and optional `sqlite-vec` vector tables (`vec0`).
- **Loaders**:
  - **Letterboxd**: Parses `watched.csv`, `watchlist.csv`, and `likes/films.csv` (dated hearts). Computes `first_heart_date` to support Positive-Unlabeled (PU) taste modeling.
  - **Goodreads**: Cleans `= "ISBN"` wrapping and indexes books for content and adaptation retrieval.
- **Resolvers & Enrichers**:
  - **TMDB**: Multi-lingual search (EN, FR, IT), title fallback, release year drift (±1, ±2), alternative titles, disk-cached raw JSON (`data/cache/tmdb/`), crew/cast extraction, and review queue (`match_review_queue`).
  - **Open Library**: ISBN and title/author matching.
  - **Wikipedia**: Wikidata sitelink resolution to EN, FR, IT articles, clean section extraction (plot, production, reception).
  - **Subtitles**: SRT noise removal (tags, hearing-impaired cues), timestamp preservation, scene-level chunking based on silence gaps.
- **Search & Taste**:
  - **Keyword**: BM25 via SQLite FTS5 with query sanitization.
  - **Dense Vector**: Embedding models (`BAAI/bge-m3`, `intfloat/multilingual-e5-base`).
  - **Hybrid RRF**: Reciprocal Rank Fusion combining BM25 and vector similarity.
  - **Taste Rankers**: Mean of heart vectors, Nearest-exemplar (max cosine), Top-3 mean, and K-means prototypes ($k=4..6$).
  - **Crew Queries**: Filmography completion tracking and crew overlap with hearted films.
- **Evaluation Harness**:
  - **Hearts Recall**: Cross-validated multi-split evaluations on post-first-heart candidates (Recall@20, Recall@50, MRR, standard deviation).
  - **Known-Item Retrieval**: 30 hand-written benchmark queries (factual, thematic, named entity) scoring Hit@5, Hit@10, Hit@20, MRR.
  - **Adaptation Pairs**: Cross-modal retrieval between books and their film adaptations.
  - **Faithfulness**: 20 benchmark prompts checking groundedness % and citation compliance.
- **Interfaces**:
  - Zero-dependency CLI (`kinolog`) with clean terminal output.
  - Interactive match review queue CLI (`kinolog ingest review`).
  - MCP Server (`src/interfaces/mcp_server.py`) with 6 tools: `search`, `rank_watchlist`, `similar_to`, `filmography`, `crew_overlap`, `stats`.
  - Chat Agent (`src/interfaces/chat/agent.py`) with token-budgeted context assembly and citations.

---

## Quickstart & CLI Usage

### Database & Ingestion

```bash
# View current database statistics
python3 -m src.interfaces.cli stats

# Ingest Letterboxd exports (folder or zip)
python3 -m src.interfaces.cli ingest letterboxd data/raw_exports/letterboxd

# Ingest Goodreads export
python3 -m src.interfaces.cli ingest goodreads data/raw_exports/goodreads.csv

# Resolve items with TMDB
export TMDB_API_KEY="your_api_key"
python3 -m src.interfaces.cli ingest resolve

# Review ambiguous matches interactively
python3 -m src.interfaces.cli ingest review

# Enrich matched films with TMDB metadata & credits
python3 -m src.interfaces.cli ingest enrich

# Chunk all documents (whole, fixed_256_50, section)
python3 -m src.interfaces.cli ingest chunk --strategy whole

# Embed chunks (requires sentence-transformers)
python3 -m src.interfaces.cli ingest embed --model bge_m3
```

### Search & Exploration

```bash
# BM25 Search
python3 -m src.interfaces.cli search "journalist in Rome" --mode bm25

# Check person filmography
python3 -m src.interfaces.cli filmography "Fellini" --role Director

# Check crew overlap with hearted films
python3 -m src.interfaces.cli crew-overlap --role Director --min-overlap 2
```

### Running Evaluations

```bash
# Run known-item retrieval benchmark
python3 -m src.interfaces.cli eval known-items --mode bm25

# Run hearts recall taste evaluation (10 random splits)
python3 -m src.interfaces.cli eval hearts --ranker nearest_exemplar --splits 10
```

---

## MCP Server Configuration

To expose the Kinolog index tools to Claude or Antigravity via Model Context Protocol:

```json
{
  "mcpServers": {
    "kinolog": {
      "command": "python3",
      "args": ["-m", "src.interfaces.mcp_server"],
      "cwd": "/Users/amaurymouldron/Sites/Me/kinolog",
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

### Available MCP Tools:
- `search(query, mode, limit, item_type, seen, decade)`: Hybrid/BM25/vector search.
- `rank_watchlist(ranker, limit)`: Ranks watchlist films by taste affinity.
- `similar_to(title, limit, item_type)`: Vector similarity recommendations.
- `filmography(name, role)`: Person's filmography with seen/unseen counts.
- `crew_overlap(role, min_overlap)`: Auteurs and crew patterns in hearted films.
- `stats()`: Index inventory and review queue metrics.

---

## Running the Test Suite

```bash
.venv/bin/pytest -v
```
All 68 unit and integration tests run in under 0.5s.
