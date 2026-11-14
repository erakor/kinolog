"""Crew queries: filmography completion, crew overlap with hearts."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.db import Database

logger = logging.getLogger(__name__)


@dataclass
class FilmographyEntry:
    person_id: int
    person_name: str
    role: str
    total_in_db: int
    total_seen: int
    films: list[dict]


@dataclass
class CrewOverlap:
    person_id: int
    person_name: str
    role: str
    overlap_count: int  # how many hearted films they appear in
    total_seen: int
    films: list[dict]


def find_people(
    db: Database,
    name: str | None = None,
    person_id: int | None = None,
) -> list:
    """Find people by name (partial match) or person_id."""
    if person_id:
        return db.execute("SELECT id, name FROM people WHERE id = ?", (person_id,)).fetchall()
    elif name:
        return db.execute(
            "SELECT id, name FROM people WHERE name LIKE ?",
            (f"%{name}%",),
        ).fetchall()
    else:
        raise ValueError("Provide person_name or person_id")


def filmography(
    db: Database,
    person_name: str | None = None,
    person_id: int | None = None,
    role: str | None = None,
) -> list[FilmographyEntry]:
    """
    Get filmography for a person, with seen/unseen status.

    Search by name (partial match) or person_id.
    """
    people = find_people(db, name=person_name, person_id=person_id)

    results = []
    for person in people:
        # Get all credits
        sql = """
            SELECT c.item_id, c.role, c.department,
                   i.title, i.year, i.item_type,
                   COALESCE(us.seen, 0) as seen
            FROM credits c
            JOIN items i ON c.item_id = i.id
            LEFT JOIN user_status us ON i.id = us.item_id
            WHERE c.person_id = ?
        """
        params: list = [person["id"]]
        if role:
            sql += " AND c.role = ?"
            params.append(role)
        sql += " ORDER BY i.year"

        films = [dict(r) for r in db.execute(sql, tuple(params)).fetchall()]
        total_seen = sum(1 for f in films if f["seen"])

        results.append(
            FilmographyEntry(
                person_id=person["id"],
                person_name=person["name"],
                role=role or "all",
                total_in_db=len(films),
                total_seen=total_seen,
                films=films,
            )
        )

    return results


def crew_overlap_with_hearts(
    db: Database,
    role: str | None = None,
    min_overlap: int = 2,
    limit: int = 30,
) -> list[CrewOverlap]:
    """
    Find crew members who appear in multiple hearted films.

    Useful for discovering important auteurs in taste profile.
    """
    sql = """
        SELECT p.id as person_id, p.name as person_name,
               cr.role,
               COUNT(DISTINCT cr.item_id) as overlap_count
        FROM credits cr
        JOIN people p ON cr.person_id = p.id
        JOIN user_status us ON cr.item_id = us.item_id
        WHERE us.liked = 1
    """
    params: list = []
    if role:
        sql += " AND cr.role = ?"
        params.append(role)

    sql += """
        GROUP BY p.id, cr.role
        HAVING overlap_count >= ?
        ORDER BY overlap_count DESC
        LIMIT ?
    """
    params.extend([min_overlap, limit])

    rows = db.execute(sql, tuple(params)).fetchall()
    results = []

    for row in rows:
        # Get the specific liked films
        films = db.execute(
            """SELECT i.title, i.year FROM credits cr
               JOIN items i ON cr.item_id = i.id
               JOIN user_status us ON i.id = us.item_id
               WHERE cr.person_id = ? AND cr.role = ? AND us.liked = 1
               ORDER BY i.year""",
            (row["person_id"], row["role"]),
        ).fetchall()

        # Get total seen
        total_seen_row = db.execute(
            """SELECT COUNT(*) as cnt FROM credits cr
               JOIN user_status us ON cr.item_id = us.item_id
               WHERE cr.person_id = ? AND cr.role = ? AND us.seen = 1""",
            (row["person_id"], row["role"]),
        ).fetchone()

        results.append(
            CrewOverlap(
                person_id=row["person_id"],
                person_name=row["person_name"],
                role=row["role"],
                overlap_count=row["overlap_count"],
                total_seen=total_seen_row["cnt"] if total_seen_row else 0,
                films=[dict(f) for f in films],
            )
        )

    return results


def directors_by_heart_count(db: Database, limit: int = 20) -> list[dict]:
    """Rank directors by number of hearted films."""
    rows = db.execute(
        """SELECT p.id, p.name,
                  COUNT(DISTINCT cr.item_id) as heart_count,
                  (SELECT COUNT(DISTINCT cr2.item_id) FROM credits cr2
                   JOIN user_status us2 ON cr2.item_id = us2.item_id
                   WHERE cr2.person_id = p.id AND cr2.role = 'Director'
                     AND us2.seen = 1) as seen_count,
                  (SELECT COUNT(DISTINCT cr3.item_id) FROM credits cr3
                   WHERE cr3.person_id = p.id AND cr3.role = 'Director') as total_in_db
           FROM credits cr
           JOIN people p ON cr.person_id = p.id
           JOIN user_status us ON cr.item_id = us.item_id
           WHERE cr.role = 'Director' AND us.liked = 1
           GROUP BY p.id
           ORDER BY heart_count DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
