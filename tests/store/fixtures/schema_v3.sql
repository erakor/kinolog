CREATE INDEX idx_chunks_doc ON chunks(document_id)
-- ---
CREATE INDEX idx_chunks_item ON chunks(item_id)
-- ---
CREATE INDEX idx_chunks_strategy ON chunks(strategy)
-- ---
CREATE INDEX idx_credits_item ON credits(item_id)
-- ---
CREATE INDEX idx_credits_person ON credits(person_id)
-- ---
CREATE INDEX idx_documents_item ON documents(item_id)
-- ---
CREATE INDEX idx_items_title_year ON items(title, year)
-- ---
CREATE INDEX idx_items_tmdb ON items(tmdb_id)
-- ---
CREATE INDEX idx_items_type ON items(item_type)
-- ---
CREATE INDEX idx_user_status_liked ON user_status(liked)
-- ---
CREATE INDEX idx_user_status_seen ON user_status(seen)
-- ---
CREATE INDEX idx_watch_log_date ON watch_log(watched_on)
-- ---
CREATE INDEX idx_watch_log_item ON watch_log(item_id)
-- ---
CREATE TABLE chunks (
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
)
-- ---
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text, section_name,
    content='chunks', content_rowid='id'
)
-- ---
CREATE TABLE 'chunks_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID
-- ---
CREATE TABLE 'chunks_fts_data'(id INTEGER PRIMARY KEY, block BLOB)
-- ---
CREATE TABLE 'chunks_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB)
-- ---
CREATE TABLE 'chunks_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID
-- ---
CREATE TABLE credits (
    item_id INTEGER NOT NULL REFERENCES items(id),
    person_id INTEGER NOT NULL REFERENCES people(id),
    role TEXT NOT NULL,
    department TEXT,
    PRIMARY KEY (item_id, person_id, role)
)
-- ---
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source TEXT,
    lang TEXT,
    text TEXT,
    content_hash TEXT
)
-- ---
CREATE TABLE eval_runs (
    id INTEGER PRIMARY KEY,
    run_at TEXT NOT NULL,
    suite TEXT NOT NULL,
    config_json TEXT,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    stdev REAL
)
-- ---
CREATE TABLE items (
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
, runtime_min INTEGER, is_tv INTEGER DEFAULT 0)
-- ---
CREATE TABLE match_review_queue (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    candidates_json TEXT,
    reason TEXT
)
-- ---
CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    tmdb_person_id INTEGER UNIQUE,
    name TEXT NOT NULL
)
-- ---
CREATE TABLE raw_cache (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    fetched_at TEXT,
    content_hash TEXT,
    path TEXT,
    PRIMARY KEY (source, external_id)
)
-- ---
CREATE TABLE user_status (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    seen INTEGER DEFAULT 0,
    seen_date TEXT,
    on_watchlist INTEGER DEFAULT 0,
    liked INTEGER DEFAULT 0,
    liked_date TEXT,
    source TEXT
, rating INTEGER, watchlist_added_at TEXT, watchlist_removed_at TEXT, manual_updated_at TEXT)
-- ---
CREATE TABLE watch_log (
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
    updated_at TEXT NOT NULL, edited INTEGER DEFAULT 0,
    UNIQUE (source, source_key)
)
-- ---
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section_name)
    VALUES ('delete', old.id, old.text, old.section_name);
END
-- ---
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, section_name)
    VALUES (new.id, new.text, new.section_name);
END
-- ---
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section_name)
    VALUES ('delete', old.id, old.text, old.section_name);
    INSERT INTO chunks_fts(rowid, text, section_name)
    VALUES (new.id, new.text, new.section_name);
END
