"""Tests for Kinolog CLI."""

import subprocess
import sys
import pytest
from kinolog.store import Database


@pytest.fixture
def populated_db(tmp_path):
    db_path = tmp_path / "test_cli.db"
    db = Database(db_path)
    id1 = db.upsert_item("film", "La Dolce Vita", 1960)
    db.upsert_user_status(id1, seen=1, liked=1)
    fellini = db.upsert_person("Federico Fellini", tmdb_person_id=4415)
    db.upsert_credit(id1, fellini, "Director", "Directing")
    doc_id = db.upsert_document(id1, "tmdb", "en", "A journalist in Rome experiencing decadence.")
    from kinolog.core.chunkers import chunk_document
    chunk_document(db, doc_id, strategy="whole")
    db.close()
    return str(db_path)


def test_cli_help():
    res = subprocess.run([sys.executable, "-m", "kinolog.interfaces.cli", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "Personal Film & Book Index" in res.stdout


def test_cli_stats(populated_db):
    res = subprocess.run([sys.executable, "-m", "kinolog.interfaces.cli", "stats", "--db", populated_db],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "Database Stats" in res.stdout
    assert "items" in res.stdout


def test_cli_search(populated_db):
    res = subprocess.run([sys.executable, "-m", "kinolog.interfaces.cli", "search",
                          "Rome journalist", "--db", populated_db, "--mode", "bm25"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "La Dolce Vita" in res.stdout


def test_cli_filmography(populated_db):
    res = subprocess.run([sys.executable, "-m", "kinolog.interfaces.cli", "filmography", "Fellini",
                          "--db", populated_db],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "Federico Fellini" in res.stdout
    assert "La Dolce Vita" in res.stdout


def test_cli_crew_overlap(populated_db):
    res = subprocess.run([sys.executable, "-m", "kinolog.interfaces.cli", "crew-overlap",
                          "--db", populated_db, "--min-overlap", "1"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "Federico Fellini" in res.stdout


def test_cli_eval_concierge_runs_and_logs(populated_db):
    res = subprocess.run(
        [sys.executable, "-m", "kinolog.interfaces.cli", "eval", "concierge", "--db", populated_db],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "parser_exact_match" in res.stdout
    db = Database(populated_db)
    suites = [r["suite"] for r in db.execute("SELECT DISTINCT suite FROM eval_runs")]
    db.close()
    assert suites == ["concierge"]
