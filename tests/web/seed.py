"""Seed data for web tests: invented titles, two directors, mixed status."""

from kinolog.core.chunkers import chunk_document


def seed(db):
    ann = db.upsert_person("Ann Auteur", tmdb_person_id=1)
    bob = db.upsert_person("Bob Bergman", tmdb_person_id=2)
    films = [
        # title, year, runtime, director, seen, liked, queued, text
        ("Quiet Harbor", 1990, 95, ann, True, True, False,
         "A fisherman's slow winter in a harbor town."),
        ("Paper Moon Rising", 1995, 110, ann, True, False, False,
         "A con artist and a child cross the plains."),
        ("The Long Corridor", 2000, 150, ann, False, False, True,
         "Detectives chase a missing ledger through a hospital."),
        ("Brief Encounter Again", 2005, 80, ann, False, False, True,
         "Two strangers meet on a train platform each week."),
        ("Midnight Ferry", 2010, 100, ann, False, False, False,
         "A ferry crossing turns into a tense mystery."),
        ("Salt and Silence", 1980, 88, bob, True, True, False,
         "A widow rows out to an island alone."),
        ("Winter Letters", 1985, 92, bob, True, False, False,
         "Letters between siblings reveal an old betrayal."),
        ("Glass Orchard", 1990, 99, bob, False, False, True,
         "A botanist guards a greenhouse during a war."),
        ("Tiny Short", 1999, 15, bob, False, False, False, "A short film about a candle."),
    ]
    ids = {}
    for title, year, rt, person, seen, liked, queued, text in films:
        i = db.upsert_item("film", title, year, runtime_min=rt)
        db.upsert_credit(i, person, "Director", "Directing")
        db.upsert_user_status(i, seen=int(seen), liked=int(liked), on_watchlist=int(queued))
        if queued:
            db.set_watchlist(i, True, at="2024-01-01", manual=False)
        if seen:
            db.log_watch(i, f"{year + 20}-05-01", rating=8 if liked else 7, source="letterboxd",
                         source_key=f"k-{i}")
        body = f"{title} ({year})\nRuntime: {rt} minutes\n\n{text}"
        doc = db.upsert_document(i, "tmdb", "en", body)
        chunk_document(db, doc, strategy="whole")
        ids[title] = i
    return ids
