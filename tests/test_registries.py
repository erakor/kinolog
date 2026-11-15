"""Strategy registries expose exactly the names the CLI, MCP schema and stored data rely on."""

from kinolog.index.chunking import STRATEGIES
from kinolog.index.embedding import EMBEDDERS
from kinolog.taste import RANKERS


def test_chunking_strategy_names():
    assert set(STRATEGIES) == {
        "whole", "fixed_256_50", "fixed_512_100", "section", "section_no_prefix",
    }


def test_taste_ranker_names():
    assert set(RANKERS) == {
        "mean_heart", "nearest_exemplar", "top_3_mean",
        "prototypes_4", "prototypes_5", "prototypes_6",
    }


def test_embedder_names():
    assert set(EMBEDDERS) == {"bge_m3", "multilingual_e5"}


def test_registering_a_duplicate_name_is_rejected():
    import pytest

    from kinolog.index.chunking import register

    with pytest.raises(ValueError):
        register("whole")(lambda text: [])
