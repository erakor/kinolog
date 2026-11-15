"""Pure completion, delta and impact logic (no database)."""

from datetime import date

import pytest

from kinolog.features.completion import (
    FilmographyFilm,
    aggregate_impact,
    completion_deltas,
    compute_completion,
    director_completions,
    director_impact_key,
    format_pct,
    is_feature,
    load_director_films,
    passes_runtime,
    watchlist_by_director_impact,
)

TODAY = date(2026, 6, 1)


def film(title="F", year=2000, *, runtime=100, seen=False, wl=False, status="Released",
         release_date="default", is_video=False, genres=(), is_tv=False, tmdb_id=None):
    if release_date == "default":
        release_date = f"{year}-01-01" if year else None
    return FilmographyFilm(
        tmdb_id=tmdb_id, item_id=None, title=title, year=year, release_date=release_date,
        runtime=runtime, status=status, is_video=is_video, genre_ids=tuple(genres),
        seen=seen, on_watchlist=wl, is_tv=is_tv,
    )


def comp(films, person_id=1, name="Ann", **kw):
    return compute_completion(person_id, name, films, coverage="tmdb", today=TODAY, **kw)


def seen_films(n_seen, n_unseen, prefix="", **kw):
    return [film(f"{prefix}S{i}", 1950 + i, seen=True, **kw) for i in range(n_seen)] + [
        film(f"{prefix}U{i}", 1990 + i, **kw) for i in range(n_unseen)
    ]


def test_nothing_seen():
    c = comp(seen_films(0, 3))
    assert (c.seen, c.total, c.ratio) == (0, 3, 0.0)
    ds = completion_deltas(c)
    assert len(ds) == 3
    assert {(format_pct(d.before_ratio), format_pct(d.after_ratio)) for d in ds} == {(0, 33)}


def test_partly_seen_five_of_seven():
    c = comp(seen_films(5, 2))
    d = completion_deltas(c)[0]
    assert (format_pct(d.before_ratio), format_pct(d.after_ratio)) == (71, 86)
    assert d.delta == pytest.approx(1 / 7)


def test_fully_seen_has_no_deltas_and_no_impact():
    c = comp(seen_films(3, 0))
    assert c.ratio == 1.0
    assert completion_deltas(c) == []
    assert aggregate_impact(completion_deltas(c)) == []


def test_seen_and_watchlisted_counts_once_and_is_never_a_candidate():
    films = [film("A", 1990, seen=True, wl=True), film("B", 2000, wl=True), film("C", 2005)]
    c = comp(films)
    assert (c.seen, c.total) == (1, 3)
    titles = [d.film.title for d in completion_deltas(c, watchlist_only=True)]
    assert titles == ["B"]
    assert "A" not in [i.film.title for i in aggregate_impact(completion_deltas(c))]


def test_missing_runtime_counts_but_is_filtered_from_candidates():
    films = [film("A", 1990, seen=True), film("B", 2000, runtime=None), film("C", 2005, runtime=80)]
    c = comp(films)
    assert c.total == 3
    assert [d.film.title for d in completion_deltas(c, max_runtime=90)] == ["C"]
    both = completion_deltas(c, max_runtime=90, include_unknown_runtime=True)
    assert [d.film.title for d in both] == ["B", "C"]


@pytest.mark.parametrize("limit", [90, 105, 120])
def test_runtime_boundaries(limit):
    assert passes_runtime(film(runtime=limit), limit)
    assert not passes_runtime(film(runtime=limit + 1), limit)
    assert passes_runtime(film(runtime=None), None)


def test_seen_short_is_in_neither_numerator_nor_denominator():
    c = comp([film("Short", 1990, runtime=15, seen=True), film("A", 2000, seen=True),
              film("B", 2001)])
    assert (c.seen, c.total) == (1, 2)


def test_forty_minutes_is_a_short_like_collections():
    assert not is_feature(film(runtime=40), today=TODAY)
    assert is_feature(film(runtime=41), today=TODAY)


@pytest.mark.parametrize("kw", [
    {"release_date": "2027-01-01"},
    {"release_date": None},
    {"status": "Post Production"},
    {"is_video": True},
    {"genres": (10770,)},
    {"is_tv": True},
])
def test_excluded_by_default(kw):
    assert not is_feature(film(**kw), today=TODAY)


def test_tv_movie_included_on_request_and_documentary_always():
    assert is_feature(film(genres=(10770,)), today=TODAY, include_tv_movies=True)
    assert is_feature(film(is_tv=True), today=TODAY, include_tv_movies=True)
    assert is_feature(film(genres=(99,)), today=TODAY)


def test_year_only_release_date():
    assert is_feature(film(release_date="2026"), today=TODAY)
    assert not is_feature(film(release_date="2027"), today=TODAY)
    assert not is_feature(film(release_date="garbage"), today=TODAY)


def test_director_with_only_shorts():
    c = comp([film("S", runtime=10, seen=True)])
    assert (c.total, c.ratio) == (0, 0.0)
    assert completion_deltas(c) == []


def test_completes_only_when_one_film_remains():
    two_left = completion_deltas(comp(seen_films(1, 2)))
    assert [d.completes for d in two_left] == [False, False]
    one_left = completion_deltas(comp(seen_films(2, 1)))
    assert [d.completes for d in one_left] == [True]


def test_distinct_films_with_equal_fields_are_not_merged():
    a = comp([film("Same", 2000, seen=True), film("Same", 2001)], person_id=1)
    b = comp([film("Same", 2000, seen=True), film("Same", 2001)], person_id=2, name="Bob")
    assert len(aggregate_impact(completion_deltas(a) + completion_deltas(b))) == 1  # no ids: key
    a2 = comp([film("Same", 2000, seen=True), film("Same", 2001, tmdb_id=1)], person_id=1)
    b2 = comp([film("Same", 2000, seen=True), film("Same", 2001, tmdb_id=2)], person_id=2)
    assert len(aggregate_impact(completion_deltas(a2) + completion_deltas(b2))) == 2


def test_co_directed_film_sums_both_deltas():
    shared = film("Shared", 2000, tmdb_id=9)
    a = comp([film("A1", 1990, seen=True), shared], person_id=1, name="Ann")  # 1/2
    b = comp([film("B1", 1990, seen=True), film("B2", 1991, seen=True),
              film("B3", 1992, seen=True), shared], person_id=2, name="Bob")  # 3/4
    (fi,) = aggregate_impact(completion_deltas(a) + completion_deltas(b))
    assert len(fi.deltas) == 2
    assert fi.impact == pytest.approx(1 / 2 + 1 / 4)


def test_unseen_director_adds_no_impact_by_default():
    c = comp([film("Debut", 2000)], person_id=3, name="New")  # 0/1 -> 1/1
    (fi,) = aggregate_impact(completion_deltas(c))
    assert fi.impact == 0.0 and fi.deltas[0].completes
    (fi2,) = aggregate_impact(completion_deltas(c), min_seen_for_impact=0)
    assert fi2.impact == 1.0


def test_impact_ordering():
    half = comp([film("H1", 1990, seen=True), film("H2", 2000)], person_id=1)  # 1/2 -> 2/2
    sevens = comp(seen_films(5, 2, "x"), person_id=2)  # 5/7 -> 6/7
    thirty = comp(seen_films(1, 29, "y"), person_id=3)  # 1/30 -> 2/30
    ranked = aggregate_impact(
        completion_deltas(thirty) + completion_deltas(sevens) + completion_deltas(half)
    )
    assert ranked[0].film.title == "H2"
    assert ranked[1].film.title == "xU0" and ranked[1].deltas[0].total == 7
    assert ranked[-1].deltas[0].total == 30
    keys = [director_impact_key(r) for r in ranked]
    assert keys == sorted(keys)
    # deterministic ties: same impact falls back to year, then title
    assert [r.film.title for r in ranked[1:3]] == ["xU0", "xU1"]


# --- Loaders ---

def director(db, name, tmdb_person_id):
    return db.upsert_person(name, tmdb_person_id=tmdb_person_id)


def indexed(db, pid, title, year, *, tmdb_id=None, runtime=100, role="Director", **status):
    item = db.upsert_item("film", title, year, tmdb_id=tmdb_id, runtime_min=runtime)
    db.upsert_credit(item, pid, role, "Directing")
    if status:
        db.upsert_user_status(item, **status)
    return item


def test_without_a_filmography_uses_director_credits_only(db):
    fellini = director(db, "Fellini", 1)
    indexed(db, fellini, "8½", 1963, seen=1)
    indexed(db, fellini, "Amarcord", 1973, seen=1)
    indexed(db, fellini, "Score", 1973, role="Original Music Composer")
    (c,) = director_completions(db, name="Fellini", today=TODAY)
    assert (c.coverage, c.seen, c.total) == ("index_only", 2, 2)
    assert [f.title for f in c.films] == ["8½", "Amarcord"]


def test_with_a_filmography_non_indexed_films_are_unseen_with_no_item(db):
    ann = director(db, "Ann", 2)
    indexed(db, ann, "Seen", 1990, tmdb_id=10, seen=1)
    db.upsert_tmdb_movie(10, "Seen", year=1990, release_date="1990-05-01", runtime=100,
                         status="Released")
    db.upsert_tmdb_movie(11, "Unlogged", year=2001, release_date="2001-05-01", runtime=95,
                         status="Released")
    db.set_person_filmography(ann, [10, 11])
    (c,) = director_completions(db, name="Ann", today=TODAY)
    assert (c.coverage, c.seen, c.total) == ("tmdb", 1, 2)
    unlogged = next(f for f in c.films if f.title == "Unlogged")
    assert unlogged.item_id is None and not unlogged.seen and unlogged.tmdb_id == 11


def test_indexed_item_takes_seen_state_from_user_status_and_defaults_to_unseen(db):
    ann = director(db, "Ann", 2)
    a = indexed(db, ann, "A", 1990, tmdb_id=10, seen=1, on_watchlist=1)
    b = indexed(db, ann, "B", 1995, tmdb_id=11)  # no user_status row
    for t, y in ((10, 1990), (11, 1995)):
        db.upsert_tmdb_movie(t, "x", year=y, release_date=f"{y}-01-01", status="Released")
    db.set_person_filmography(ann, [10, 11])
    films, _ = load_director_films(db, ann)
    by_item = {f.item_id: f for f in films}
    assert by_item[a].seen and by_item[a].on_watchlist
    assert not by_item[b].seen and not by_item[b].on_watchlist


def test_union_keeps_a_seen_indexed_credit_missing_from_the_filmography(db):
    ann = director(db, "Ann", 2)
    indexed(db, ann, "Dropped", 1980, tmdb_id=20, seen=1)  # TMDB omits it from her credits
    db.upsert_tmdb_movie(30, "Other", year=1999, release_date="1999-01-01", status="Released")
    db.set_person_filmography(ann, [30])
    (c,) = director_completions(db, name="Ann", today=TODAY)
    assert c.coverage == "tmdb" and (c.seen, c.total) == (1, 2)


def test_name_matching_two_people_returns_two_completions(db):
    for n, pid in (("Jean Renoir", 5), ("Jean Vigo", 6)):
        indexed(db, director(db, n, pid), f"Film {n}", 1950, seen=1)
    res = director_completions(db, name="Jean", today=TODAY)
    assert {c.name for c in res} == {"Jean Renoir", "Jean Vigo"}


def test_min_seen_and_min_total_filter(db):
    one = director(db, "One", 7)
    indexed(db, one, "Only", 1990, seen=1)
    assert director_completions(db, min_total=2, today=TODAY) == []
    assert director_completions(db, min_seen=2, today=TODAY) == []
    assert len(director_completions(db, min_seen=1, today=TODAY)) == 1


def test_watchlist_impact_defaults_to_watchlist_and_include_unseen_adds_the_rest(db):
    ann = director(db, "Ann", 2)
    indexed(db, ann, "Seen", 1990, tmdb_id=10, seen=1)
    indexed(db, ann, "Queued", 1995, tmdb_id=11, on_watchlist=1)
    indexed(db, ann, "Shelf", 1998, tmdb_id=12)
    for t, y, ti in ((10, 1990, "Seen"), (11, 1995, "Queued"), (12, 1998, "Shelf"),
                     (13, 2003, "Unlogged")):
        db.upsert_tmdb_movie(t, ti, year=y, release_date=f"{y}-01-01", runtime=90,
                             status="Released")
    db.set_person_filmography(ann, [10, 11, 12, 13])
    default = watchlist_by_director_impact(db, today=TODAY)
    assert [i.film.title for i in default] == ["Queued"]
    everything = watchlist_by_director_impact(db, include_unseen=True, today=TODAY)
    assert {i.film.title for i in everything} == {"Queued", "Shelf", "Unlogged"}
    assert next(i for i in everything if i.film.title == "Unlogged").film.item_id is None
    assert watchlist_by_director_impact(db, include_unseen=True, limit=1, today=TODAY)[0]
    short = watchlist_by_director_impact(db, max_runtime=80, include_unseen=True, today=TODAY)
    assert short == []


def test_seen_film_counts_whatever_its_status():
    assert is_feature(film(status="Post Production", seen=True), today=TODAY)
    assert is_feature(film(release_date=None, seen=True), today=TODAY)
    assert not is_feature(film(runtime=30, seen=True), today=TODAY)


def test_format_pct_rounds_float_halves_up():
    assert format_pct(29 / 200) == 15


def test_a_debut_by_an_unseen_director_does_not_outrank_a_real_advance():
    debut = comp([film("Debut", 2000, wl=True)], person_id=1, name="New")
    veteran = comp(seen_films(2, 1, wl=True), person_id=2, name="Old")
    ranked = aggregate_impact(completion_deltas(debut) + completion_deltas(veteran))
    assert [i.film.title for i in ranked][0] == "U0"
    assert ranked[-1].film.title == "Debut" and ranked[-1].impact == 0


def test_unindexed_film_without_status_flags_partial_coverage(db):
    ann = director(db, "Ann", 2)
    indexed(db, ann, "Seen", 1990, tmdb_id=10, seen=1)
    db.upsert_tmdb_movie(10, "Seen", year=1990, release_date="1990-01-01", status="Released")
    db.upsert_tmdb_movie(11, "NoDetails", year=2001, release_date="2001-01-01")  # status None
    db.set_person_filmography(ann, [10, 11])
    (c,) = director_completions(db, name="Ann", today=TODAY)
    assert c.coverage == "index_only" and c.total == 1


def test_person_ids_limits_the_directors_considered(db):
    ids = {}
    for n, tid in (("Ann", 2), ("Bob", 3)):
        ids[n] = director(db, n, tid)
        indexed(db, ids[n], f"Film {n}", 1950, seen=1)
    res = director_completions(db, person_ids=[ids["Ann"]], today=TODAY)
    assert [c.name for c in res] == ["Ann"]
    assert director_completions(db, person_ids=[], today=TODAY) == []
    by_name = director_completions(db, name="o", person_ids=[ids["Bob"]], today=TODAY)
    assert [c.name for c in by_name] == ["Bob"]
