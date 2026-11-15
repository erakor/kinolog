-- Full TMDB director filmographies, kept apart from `items` so films the user never logged do
-- not enter the retrieval corpus, the taste candidate pool or the stats.

CREATE TABLE tmdb_movies (
    tmdb_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    original_title TEXT,
    release_date TEXT,          -- 'YYYY-MM-DD' or NULL
    year INTEGER,
    runtime INTEGER,            -- minutes; NULL or 0 from TMDB is stored as NULL
    status TEXT,                -- TMDB status: Released, Post Production, ...
    is_video INTEGER NOT NULL DEFAULT 0,  -- TMDB 'video' flag (direct-to-video)
    genre_ids TEXT,             -- JSON list; 99 = Documentary, 10770 = TV Movie
    fetched_at TEXT
);

CREATE TABLE person_filmography (
    person_id INTEGER NOT NULL REFERENCES people(id),
    tmdb_id INTEGER NOT NULL,   -- joins tmdb_movies and items.tmdb_id
    job TEXT NOT NULL,          -- 'Director' only for now
    PRIMARY KEY (person_id, tmdb_id, job)
);
CREATE INDEX idx_pf_person ON person_filmography(person_id);
