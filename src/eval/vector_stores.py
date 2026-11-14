"""Vector store comparison harness (Phase 6): benchmarks sqlite-vec, LanceDB, Qdrant on ingestion and query latency."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from src.core.db import Database
from src.eval.harness import EvalResult

logger = logging.getLogger(__name__)


@dataclass
class VectorStoreBenchmarkResult:
    store_name: str
    n_vectors: int
    dimension: int
    index_type: str  # "flat", "hnsw", "ivf"
    ingestion_time_sec: float
    query_latency_p50_ms: float
    query_latency_p95_ms: float
    recall_vs_exact: float


class VectorStoreBenchmark:
    """Benchmark different vector stores and index configurations on identical datasets."""

    def __init__(self, db: Database):
        self.db = db

    def benchmark_sqlite_vec(
        self,
        model_name: str = "bge_m3",
        n_queries: int = 50,
    ) -> VectorStoreBenchmarkResult | None:
        """Benchmark sqlite-vec store."""
        if not self.db.vec_available:
            logger.info("sqlite-vec extension not loaded in DB")
            return None

        vec_table = f"vec_{model_name}"
        rows = self.db.execute(f"SELECT chunk_id, embedding FROM {vec_table}").fetchall()
        if not rows:
            return None

        n_vectors = len(rows)
        sample_bytes = rows[0]["embedding"]
        dim = len(sample_bytes) // 4  # float32 = 4 bytes

        # Benchmark query latency
        latencies = []
        for i in range(min(n_queries, n_vectors)):
            query_bytes = rows[i]["embedding"]
            t0 = time.perf_counter()
            self.db.execute(
                f"SELECT chunk_id, distance FROM {vec_table} WHERE embedding MATCH ? AND k = 10",
                (query_bytes,),
            ).fetchall()
            latencies.append((time.perf_counter() - t0) * 1000.0)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]

        return VectorStoreBenchmarkResult(
            store_name="sqlite-vec",
            n_vectors=n_vectors,
            dimension=dim,
            index_type="flat",
            ingestion_time_sec=0.0,
            query_latency_p50_ms=p50,
            query_latency_p95_ms=p95,
            recall_vs_exact=1.0,  # Exact search
        )
