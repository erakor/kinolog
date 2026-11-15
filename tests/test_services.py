"""Services: the logic shared by the CLI, the MCP server and the web routes."""

import pytest

from kinolog import services
from kinolog.index.chunking import chunk_document
from kinolog.store import Database, InvalidInputError, NotFoundError
from kinolog.taste import TasteScore, TasteUnavailableError


@pytest.fixture
def db():
    d = Database(":memory:")
    ann = d.upsert_person("Ann Auteur", tmdb_person_id=1)
    ids = {}
    films = [
        ("Quiet Harbor", 1990, 95, True, True, False, "A fisherman's slow winter in a harbor."),
        ("Paper Moon", 1995, 110, True, False, False, "A con artist and a child cross the plains."),
        ("The Long Corridor", 2000, 150, False, False, True, "Detectives chase a ledger."),
        ("Brief Encounter", 2005, 80, False, False, True, "Two strangers meet on a platform."),
    ]
    for title, year, rt, seen, liked, queued, text in films:
        i = d.upsert_item("film", title, year, runtime_min=rt)
        d.upsert_credit(i, ann, "Director", "Directing")
        d.upsert_user_status(i, seen=int(seen), liked=int(liked), on_watchlist=int(queued))
        if queued:
            d.set_watchlist(i, True, at="2024-01-01", manual=False)
        if seen:
            d.log_watch(i, f"{year + 20}-05-01", rating=8, source="letterboxd", source_key=f"k{i}")
        doc = d.upsert_document(i, "tmdb", "en", f"{title} ({year})\nRuntime: {rt} minutes\n\n{text}")
        chunk_document(d, doc, strategy="whole")
        ids[title] = i
    d.ids = ids
    return d


# --- search and similarity ---


def test_stats_adds_queue_and_match_counts(db):
    s = services.stats(db)
    assert s["items"] == 4
    assert {"review_queue", "items_matched"} <= set(s)


def test_search_items_returns_plain_dicts(db):
    out = services.search_items(db, "harbor fisherman", mode="bm25", limit=3)
    assert out[0]["title"] == "Quiet Harbor"
    assert set(out[0]) == {"title", "year", "score", "source", "snippet"}


def test_search_items_falls_back_to_bm25_without_a_model(db):
    out = services.search_items(db, "harbor", mode="rrf", get_model=lambda: None)
    assert out and out[0]["source"] == "bm25"


def test_search_items_only_loads_the_model_for_vector_modes(db):
    def boom():
        raise AssertionError("model must not be loaded for bm25")

    assert services.search_items(db, "harbor", mode="bm25", get_model=boom)


def test_similar_to_errors(db):
    with pytest.raises(NotFoundError, match="Item not found: Nope"):
        services.similar_to(db, "Nope", get_model=lambda: None)
    with pytest.raises(services.UnavailableError, match="Embedding model not available"):
        services.similar_to(db, "Harbor", get_model=lambda: None)


# --- taste and crew ---


def test_rank_watchlist_unknown_ranker(db):
    with pytest.raises(InvalidInputError, match="Unknown ranker: nope"):
        services.rank_watchlist(db, "nope")


def test_rank_watchlist_uses_the_registered_ranker(db, monkeypatch):
    from kinolog import taste

    def fake(database, candidates, hearts, **kw):
        return [TasteScore(i, 1.0 / (n + 1), method="fake") for n, i in enumerate(candidates)]

    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", fake)
    out = services.rank_watchlist(db, "nearest_exemplar", limit=1)
    assert len(out) == 1 and out[0]["method"] == "fake"


def test_filmography_and_crew_overlap(db):
    fm = services.filmography(db, "Ann")
    assert fm[0]["person"] == "Ann Auteur" and fm[0]["total"] == 4 and fm[0]["seen"] == 2
    assert {f["title"] for f in fm[0]["films"]} >= {"Quiet Harbor"}
    assert services.crew_overlap(db, min_overlap=1)[0]["films"] == ["Quiet Harbor"]


# --- items, log, watchlist ---


def test_require_card_raises_not_found(db):
    with pytest.raises(NotFoundError, match="No such item: 999"):
        services.require_card(db, 999)


def test_item_detail_has_sources(db):
    out = services.item_detail(db, db.ids["Quiet Harbor"])
    assert out["title"] == "Quiet Harbor" and out["sources"] == ["tmdb"]


def test_rate_and_like(db):
    i = db.ids["Paper Moon"]
    assert services.rate_item(db, i, 9)["status"]["rating"] == 9
    assert services.like_item(db, i, True)["status"]["liked"] is True
    with pytest.raises(NotFoundError):
        services.rate_item(db, 999, 5)


def test_add_and_remove_watchlist(db):
    i = db.ids["Paper Moon"]
    assert services.add_to_watchlist(db, i)["status"]["on_watchlist"] is True
    assert services.remove_from_watchlist(db, i)["status"]["on_watchlist"] is False


def test_log_as_watched_removes_from_watchlist_unless_kept(db):
    a, b = db.ids["The Long Corridor"], db.ids["Brief Encounter"]
    out = services.log_as_watched(db, a, watched_on="2024-02-02", rating=7)
    assert out["entry"]["watched_on"] == "2024-02-02"
    assert out["item"]["status"]["on_watchlist"] is False
    kept = services.log_as_watched(db, b, watched_on="2024-02-03", keep_on_watchlist=True)
    assert kept["item"]["status"]["on_watchlist"] is True


def test_create_log_entry_dequeues(db):
    i = db.ids["The Long Corridor"]
    entry = services.create_log_entry(db, i, "2024-03-01", rating=6)
    assert entry["item"]["item_id"] == i
    assert db.get_item_card(i)["status"]["on_watchlist"] is False


def test_watchlist_view_sorts_and_pages(db):
    view = services.watchlist_view(db, sort="runtime", limit=1)
    assert view["total"] == 2 and len(view["items"]) == 1
    assert view["items"][0]["title"] == "Brief Encounter"
    assert all("_gain" not in r for r in view["items"])
    assert {"total", "summary", "items"} == set(view)


def test_watchlist_view_rejects_unknown_sort(db):
    with pytest.raises(InvalidInputError, match="Unknown sort: sideways"):
        services.watchlist_view(db, sort="sideways")


def test_watchlist_view_taste_sort_uses_taste_fn(db):
    a, b = db.ids["The Long Corridor"], db.ids["Brief Encounter"]
    view = services.watchlist_view(
        db, sort="taste", ranker="mean_heart", taste_fn=lambda ids, r: {a: 0.2, b: 0.9}
    )
    assert [r["item_id"] for r in view["items"]] == [b, a]
    assert view["items"][0]["taste"] == {"score": 0.9, "ranker": "mean_heart"}


def test_watchlist_view_propagates_taste_unavailable(db):
    def unavailable(ids, ranker):
        raise TasteUnavailableError("no hearts")

    with pytest.raises(TasteUnavailableError):
        services.watchlist_view(db, sort="taste", taste_fn=unavailable)


# --- collections and the concierge ---


def test_directors_view_and_director_view(db):
    view = services.directors_view(db, min_films=2)
    assert view["total"] == 1 and view["items"][0]["name"] == "Ann Auteur"
    assert "films" not in view["items"][0]
    person_id = view["items"][0]["person_id"]
    detail = services.director_view(db, person_id)
    assert len(detail["films"]) == 4
    assert all(f["after_pct"] is None for f in detail["films"] if f["seen"])
    with pytest.raises(NotFoundError, match="No such director"):
        services.director_view(db, 999)


def test_concierge_suggestions_mention_the_closest_director(db):
    prompts = services.concierge_suggestions(db)["prompts"]
    assert prompts[2] == "What should I watch next from Ann Auteur?"
    assert len(prompts) <= 5


def test_concierge_overview_shape(db):
    out = services.concierge_overview(db)
    assert out["directors"] == {"tracked": 1}
    assert out["closest"]["name"] == "Ann Auteur"
    assert out["radar"][0]["quickest"]["title"] == "Brief Encounter"


def test_concierge_pick_returns_picks_for_a_filtered_query(db):
    out = services.concierge_pick(db, "strangers on a platform under 100 minutes", limit=2)
    assert [p["item"]["title"] for p in out["picks"]] == ["Brief Encounter"]
    assert out["query"] == "strangers on a platform under 100 minutes"


# --- Filmography completion and watchlist impact ---


def test_filmography_completion_lists_directors_and_flags_index_only(db):
    (row,) = services.filmography_completion(db)
    assert (row["person"], row["seen"], row["total"], row["percent"]) == ("Ann Auteur", 2, 4, 50)
    assert row["coverage"] == "index_only" and "films" not in row


def test_filmography_completion_with_a_name_previews_each_unseen_film(db):
    (row,) = services.filmography_completion(db, name="Ann")
    films = {f["title"]: f for f in row["films"]}
    assert films["Quiet Harbor"]["if_watched"] is None
    w = films["Brief Encounter"]["if_watched"]
    assert (w["before"], w["after"], w["before_pct"], w["after_pct"]) == ("2/4", "3/4", 50, 75)
    assert films["Brief Encounter"]["on_watchlist"] and films["Brief Encounter"]["in_index"]


def test_filmography_completion_name_defaults_do_not_hide_small_filmographies(db):
    solo = db.upsert_person("Solo Director", tmdb_person_id=9)
    i = db.upsert_item("film", "Only One", 2001, runtime_min=100)
    db.upsert_credit(i, solo, "Director", "Directing")
    assert [r["person"] for r in services.filmography_completion(db)] == ["Ann Auteur"]
    (r,) = services.filmography_completion(db, name="Solo")
    assert (r["seen"], r["total"]) == (0, 1)


def test_filmography_completion_validates_arguments(db):
    with pytest.raises(InvalidInputError):
        services.filmography_completion(db, limit=0)
    with pytest.raises(InvalidInputError):
        services.filmography_completion(db, min_total=0)


def test_watchlist_director_impact_ranks_and_filters_by_runtime(db):
    rows = services.watchlist_director_impact(db)
    assert {r["title"] for r in rows} == {"The Long Corridor", "Brief Encounter"}
    d = rows[0]["directors"][0]
    assert (d["before"], d["after"], d["before_pct"], d["after_pct"]) == ("2/4", "3/4", 50, 75)
    (short,) = services.watchlist_director_impact(db, max_runtime=90)
    assert short["title"] == "Brief Encounter" and short["impact"] == 0.25
    with pytest.raises(InvalidInputError):
        services.watchlist_director_impact(db, max_runtime=0)
