CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, section_name,
    content='chunks', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, section_name)
    VALUES (new.id, new.text, new.section_name);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section_name)
    VALUES ('delete', old.id, old.text, old.section_name);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section_name)
    VALUES ('delete', old.id, old.text, old.section_name);
    INSERT INTO chunks_fts(rowid, text, section_name)
    VALUES (new.id, new.text, new.section_name);
END;

CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
CREATE INDEX IF NOT EXISTS idx_items_tmdb ON items(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_items_title_year ON items(title, year);
CREATE INDEX IF NOT EXISTS idx_user_status_seen ON user_status(seen);
CREATE INDEX IF NOT EXISTS idx_user_status_liked ON user_status(liked);
CREATE INDEX IF NOT EXISTS idx_documents_item ON documents(item_id);
CREATE INDEX IF NOT EXISTS idx_chunks_item ON chunks(item_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_strategy ON chunks(strategy);
CREATE INDEX IF NOT EXISTS idx_credits_item ON credits(item_id);
CREATE INDEX IF NOT EXISTS idx_credits_person ON credits(person_id);
CREATE INDEX IF NOT EXISTS idx_watch_log_item ON watch_log(item_id);
CREATE INDEX IF NOT EXISTS idx_watch_log_date ON watch_log(watched_on);
