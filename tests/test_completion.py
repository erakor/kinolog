"""Tests for director completion and watchlist impact ranking."""

from datetime import date

import pytest

from src.core.completion import (
    CompletionDelta,
    DirectorFilm,
    FilmImpact,
    aggregate_impact,
    completion_deltas,
    compute_completion,
    director_impact_key,
    format_pct,
    is_feature,
    passes_runtime,
)

FIXED_TODAY = date(2025, 1, 1)


def make_film(
    title: str = "Test Film",
    year: int | None = 2020,
    release_date: str | None = "2020-05-01",
    runtime: int | None = 100,
    status: str | None = "Released",
    is_video: bool = False,
    genre_ids: tuple[int, ...] = (),
    seen: bool = False,
    on_watchlist: bool = False,
    tmdb_id: int | None = 1,
    item_id: int | None = 1,
) -> DirectorFilm:
    return DirectorFilm(
        tmdb_id=tmdb_id,
        item_id=item_id,
        title=title,
        year=year,
        release_date=release_date,
        runtime=runtime,
        status=status,
        is_video=is_video,
        genre_ids=genre_ids,
        seen=seen,
        on_watchlist=on_watchlist,
    )


# 1. 0 seen: 0/3, ratio 0.0, every candidate 0% -> 33%.
def test_zero_seen():
    films = [
        make_film("Film 1", tmdb_id=1, seen=False),
        make_film("Film 2", tmdb_id=2, seen=False),
        make_film("Film 3", tmdb_id=3, seen=False),
    ]
    c = compute_completion(1, "Director Zero", films, coverage="tmdb", today=FIXED_TODAY)
    assert c.seen == 0
    assert c.total == 3
    assert c.ratio == 0.0

    deltas = completion_deltas(c)
    assert len(deltas) == 3
    for d in deltas:
        assert d.before_seen == 0
        assert d.after_seen == 1
        assert format_pct(d.before_ratio) == 0
        assert format_pct(d.after_ratio) == 33
        assert d.delta == pytest.approx(1 / 3)
        assert not d.completes


# 2. Partly seen 5/7: unseen film gives before_pct == 71, after_pct == 86, delta == 1/7.
def test_partly_seen_five_of_seven():
    films = [make_film(f"Film {i}", tmdb_id=i, seen=(i <= 5)) for i in range(1, 8)]
    c = compute_completion(2, "Director 5/7", films, coverage="tmdb", today=FIXED_TODAY)
    assert c.seen == 5
    assert c.total == 7

    deltas = completion_deltas(c)
    assert len(deltas) == 2
    for d in deltas:
        assert format_pct(d.before_ratio) == 71
        assert format_pct(d.after_ratio) == 86
        assert d.delta == pytest.approx(1 / 7)


# 3. Fully seen 3/3: 100%, completion_deltas returns [], no impact contribution.
def test_fully_seen():
    films = [make_film(f"Film {i}", tmdb_id=i, seen=True) for i in range(1, 4)]
    c = compute_completion(3, "Director Complete", films, coverage="tmdb", today=FIXED_TODAY)
    assert c.seen == 3
    assert c.total == 3
    assert c.ratio == 1.0
    assert format_pct(c.ratio) == 100

    deltas = completion_deltas(c)
    assert deltas == []
    impacts = aggregate_impact(deltas)
    assert impacts == []


# 4. Watchlisted and seen: counted once in numerator, never a candidate, absent from impact.
def test_watchlisted_and_seen():
    f1 = make_film("Seen Watchlisted", tmdb_id=1, seen=True, on_watchlist=True)
    f2 = make_film("Unseen Watchlisted", tmdb_id=2, seen=False, on_watchlist=True)
    c = compute_completion(4, "Director WL", [f1, f2], coverage="tmdb", today=FIXED_TODAY)
    assert c.seen == 1
    assert c.total == 2

    deltas = completion_deltas(c, watchlist_only=True)
    assert len(deltas) == 1
    assert deltas[0].film == f2

    impacts = aggregate_impact(deltas)
    assert len(impacts) == 1
    assert impacts[0].film == f2


# 5. Missing runtime: counted in total; excluded at max_runtime=90;
#    included with include_unknown_runtime=True.
def test_missing_runtime():
    f = make_film("No Runtime", runtime=None)
    assert is_feature(f, today=FIXED_TODAY)

    c = compute_completion(5, "Director No Runtime", [f], coverage="tmdb", today=FIXED_TODAY)
    assert c.total == 1

    # Excluded when max_runtime=90 and include_unknown_runtime=False
    deltas_excluded = completion_deltas(c, max_runtime=90, include_unknown_runtime=False)
    assert len(deltas_excluded) == 0

    # Included when include_unknown_runtime=True
    deltas_included = completion_deltas(c, max_runtime=90, include_unknown_runtime=True)
    assert len(deltas_included) == 1


# 6. Runtime boundaries: 90 passes <=90, 91 fails; same for 105 and 120.
def test_runtime_boundaries():
    for bound in (90, 105, 120):
        film_exact = make_film("Exact", runtime=bound)
        film_over = make_film("Over", runtime=bound + 1)
        assert passes_runtime(film_exact, bound)
        assert not passes_runtime(film_over, bound)


# 7. Seen short (runtime 15) is in neither numerator nor denominator.
def test_seen_short_excluded():
    short_film = make_film("Short", runtime=15, seen=True)
    assert not is_feature(short_film, today=FIXED_TODAY)

    feature_film = make_film("Feature", runtime=90, seen=False)
    c = compute_completion(
        7, "Director With Short", [short_film, feature_film], coverage="tmdb", today=FIXED_TODAY
    )
    assert c.total == 1
    assert c.seen == 0
    assert c.films == (feature_film,)


# 8. Future release, non-Released status, video film and TV movie excluded by default;
#    TV movie included with include_tv_movies=True.
def test_feature_exclusions_and_tv_movies():
    future = make_film("Future", release_date="2026-06-01")
    not_released = make_film("In Prod", status="Post Production")
    video = make_film("Direct to Video", is_video=True)
    tv_movie = make_film("TV Movie", genre_ids=(10770,))

    assert not is_feature(future, today=FIXED_TODAY)
    assert not is_feature(not_released, today=FIXED_TODAY)
    assert not is_feature(video, today=FIXED_TODAY)
    assert not is_feature(tv_movie, today=FIXED_TODAY)
    assert is_feature(tv_movie, today=FIXED_TODAY, include_tv_movies=True)


# 9. Director with only shorts: total 0, ratio 0.0, no ZeroDivisionError.
def test_only_shorts_no_division_error():
    shorts = [
        make_film("Short 1", runtime=10, seen=True),
        make_film("Short 2", runtime=25, seen=False),
    ]
    c = compute_completion(9, "Shorts Director", shorts, coverage="tmdb", today=FIXED_TODAY)
    assert c.total == 0
    assert c.seen == 0
    assert c.ratio == 0.0
    deltas = completion_deltas(c)
    assert deltas == []


# 10. completes True only for the last unseen film.
def test_completes_flag():
    f1 = make_film("Film 1", tmdb_id=1, seen=True)
    f2 = make_film("Film 2", tmdb_id=2, seen=False)
    f3 = make_film("Film 3", tmdb_id=3, seen=False)

    c = compute_completion(10, "Director Near", [f1, f2, f3], coverage="tmdb", today=FIXED_TODAY)
    assert c.seen == 1
    assert c.total == 3
    deltas = completion_deltas(c)
    assert len(deltas) == 2
    # Neither completes when 2 remain unseen
    assert not deltas[0].completes
    assert not deltas[1].completes

    # When only 1 remains unseen:
    c2 = compute_completion(
        10,
        "Director 2/3",
        [f1, make_film("Film 2", tmdb_id=2, seen=True), f3],
        coverage="tmdb",
        today=FIXED_TODAY,
    )
    deltas2 = completion_deltas(c2)
    assert len(deltas2) == 1
    assert deltas2[0].completes


# 11. Co-directed film: two deltas, impact is their sum.
def test_co_directed_film():
    film = make_film("Co-Directed", tmdb_id=42, seen=False)
    d1 = CompletionDelta(
        person_id=101,
        director="Director A",
        film=film,
        before_seen=1,
        after_seen=2,
        total=4,
        before_ratio=0.25,
        after_ratio=0.5,
        delta=0.25,
        completes=False,
    )
    d2 = CompletionDelta(
        person_id=102,
        director="Director B",
        film=film,
        before_seen=2,
        after_seen=3,
        total=5,
        before_ratio=0.4,
        after_ratio=0.6,
        delta=0.2,
        completes=False,
    )

    impacts = aggregate_impact([d1, d2])
    assert len(impacts) == 1
    assert len(impacts[0].deltas) == 2
    assert impacts[0].impact == pytest.approx(0.45)


# 12. director_impact_key ordering: 1/2 -> 2/2 above 5/7 -> 6/7 above 0/30 -> 1/30;
#     a director with 0 seen adds no impact at default min_seen_for_impact=1; deterministic ties.
def test_director_impact_key_ordering():
    film_completing = make_film("Completing Film", tmdb_id=1, year=2020)
    delta_completing = CompletionDelta(
        person_id=1,
        director="Dir 1",
        film=film_completing,
        before_seen=1,
        after_seen=2,
        total=2,
        before_ratio=0.5,
        after_ratio=1.0,
        delta=0.5,
        completes=True,
    )

    film_partly = make_film("High Impact Film", tmdb_id=2, year=2020)
    delta_partly = CompletionDelta(
        person_id=2,
        director="Dir 2",
        film=film_partly,
        before_seen=5,
        after_seen=6,
        total=7,
        before_ratio=5 / 7,
        after_ratio=6 / 7,
        delta=1 / 7,
        completes=False,
    )

    film_zero = make_film("Zero Seen Dir Film", tmdb_id=3, year=2020)
    delta_zero = CompletionDelta(
        person_id=3,
        director="Dir 3",
        film=film_zero,
        before_seen=0,
        after_seen=1,
        total=30,
        before_ratio=0.0,
        after_ratio=1 / 30,
        delta=1 / 30,
        completes=False,
    )

    impacts = aggregate_impact([delta_zero, delta_partly, delta_completing])
    assert [fi.film.title for fi in impacts] == [
        "Completing Film",
        "High Impact Film",
        "Zero Seen Dir Film",
    ]
    # Director with 0 seen contributes 0.0 to impact with min_seen_for_impact=1
    assert impacts[2].impact == 0.0

    # Deterministic ties broken by year, then title
    film_tie_a = make_film("Alpha", tmdb_id=10, year=2010)
    film_tie_b = make_film("Beta", tmdb_id=11, year=2010)
    fi_a = FilmImpact(film=film_tie_a, deltas=(), impact=0.2)
    fi_b = FilmImpact(film=film_tie_b, deltas=(), impact=0.2)
    assert director_impact_key(fi_a) < director_impact_key(fi_b)
