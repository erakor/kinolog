"""Tests for vector store benchmark."""

from kinolog.eval.suites.vector_stores import VectorStoreBenchmark
from kinolog.store import Database


def test_vector_store_benchmark():
    db = Database(":memory:")
    bench = VectorStoreBenchmark(db)
    res = bench.benchmark_sqlite_vec()
    # In sqlite without vec extension loaded, should return None gracefully
    assert res is None or res.store_name == "sqlite-vec"
    db.close()
