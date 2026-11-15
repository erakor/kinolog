"""Pure completion, delta and impact logic (no database)."""

from datetime import date

import pytest

from kinolog.features.completion import (
    FilmographyFilm,
    aggregate_impact,
    completion_deltas,
    compute_completion,
    director_impact_key,
    format_pct,
    is_feature,
    passes_runtime,
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
