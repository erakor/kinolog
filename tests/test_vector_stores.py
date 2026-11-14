"""Tests for vector store benchmark."""

from src.core.db import Database
from src.eval.vector_stores import VectorStoreBenchmark


def test_vector_store_benchmark():
    db = Database(":memory:")
    bench = VectorStoreBenchmark(db)
    res = bench.benchmark_sqlite_vec()
    # In sqlite without vec extension loaded, should return None gracefully
    assert res is None or res.store_name == "sqlite-vec"
    db.close()
