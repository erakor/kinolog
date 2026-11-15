CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    item_type TEXT NOT NULL CHECK (item_type IN ('film', 'book')),
    title TEXT NOT NULL,
    original_title TEXT,
    year INTEGER,
    tmdb_id INTEGER UNIQUE,
    wikidata_id TEXT UNIQUE,
    isbn TEXT,
    openlibrary_id TEXT,
    match_confidence REAL,
    match_status TEXT CHECK (match_status IN ('auto', 'manual', 'queued', 'rejected'))
);

CREATE TABLE IF NOT EXISTS user_status (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    seen INTEGER DEFAULT 0,
    seen_date TEXT,
    on_watchlist INTEGER DEFAULT 0,
    liked INTEGER DEFAULT 0,
    liked_date TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS watch_log (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    watched_on TEXT NOT NULL,
    rating INTEGER,
    liked INTEGER,
    rewatch INTEGER DEFAULT 0,
    source TEXT NOT NULL,
    source_key TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source, source_key)
);

CREATE TABLE IF NOT EXISTS raw_cache (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    fetched_at TEXT,
    content_hash TEXT,
    path TEXT,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    tmdb_person_id INTEGER UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credits (
    item_id INTEGER NOT NULL REFERENCES items(id),
    person_id INTEGER NOT NULL REFERENCES people(id),
    role TEXT NOT NULL,
    department TEXT,
    PRIMARY KEY (item_id, person_id, role)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source TEXT,
    lang TEXT,
    text TEXT,
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    ord INTEGER NOT NULL,
    section_name TEXT,
    lang TEXT,
    text TEXT NOT NULL,
    token_count INTEGER,
    start_ms INTEGER,
    end_ms INTEGER,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_review_queue (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    candidates_json TEXT,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY,
    run_at TEXT NOT NULL,
    suite TEXT NOT NULL,
    config_json TEXT,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    stdev REAL
);
