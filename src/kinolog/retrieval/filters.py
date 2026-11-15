"""Search filters: item type, decade, runtime and user-state conditions as SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kinolog.domain import SHORT_MAX_MIN


@dataclass
class SearchFilters:
    item_type: str | None = None
    seen: bool | None = None
    liked: bool | None = None
    on_watchlist: bool | None = None
    year_min: int | None = None
    year_max: int | None = None
    country: str | None = None
    language: str | None = None
    decade: int | None = None
    runtime_min: int | None = None
    runtime_max: int | None = None
    item_ids: list[int] | None = None
    exclude_ids: list[int] | None = None
    features_only: bool = False  # drop shorts and TV movies (see collections.SHORT_MAX_MIN)

    def to_sql_conditions(self) -> tuple[str, list]:
        """Returns (WHERE clause fragments, params) for items table alias 'i'."""
        conditions = []
        params: list[Any] = []

        if self.item_type:
            conditions.append("i.item_type = ?")
            params.append(self.item_type)
        if self.year_min:
            conditions.append("i.year >= ?")
            params.append(self.year_min)
        if self.year_max:
            conditions.append("i.year <= ?")
            params.append(self.year_max)
        if self.decade:
            conditions.append("i.year >= ? AND i.year < ?")
            params.extend([self.decade, self.decade + 10])
        # Items with unknown runtime never satisfy a runtime constraint.
        if self.runtime_min is not None:
            conditions.append("i.runtime_min IS NOT NULL AND i.runtime_min >= ?")
            params.append(self.runtime_min)
        if self.runtime_max is not None:
            conditions.append("i.runtime_min IS NOT NULL AND i.runtime_min <= ?")
            params.append(self.runtime_max)
        if self.item_ids is not None:
            if self.item_ids:
                conditions.append(f"i.id IN ({','.join('?' for _ in self.item_ids)})")
                params.extend(self.item_ids)
            else:
                conditions.append("0 = 1")
        if self.features_only:
            conditions.append(
                "COALESCE(i.is_tv, 0) = 0 "
                f"AND (i.runtime_min IS NULL OR i.runtime_min > {SHORT_MAX_MIN})"
            )
        if self.exclude_ids:
            conditions.append(f"i.id NOT IN ({','.join('?' for _ in self.exclude_ids)})")
            params.extend(self.exclude_ids)

        return " AND ".join(conditions), params

    def to_status_conditions(self) -> tuple[str, list]:
        """Returns (WHERE clause fragments, params) for user_status table alias 'us'."""
        conditions = []
        params: list[Any] = []

        if self.seen is not None:
            conditions.append("us.seen = ?")
            params.append(1 if self.seen else 0)
        if self.liked is not None:
            conditions.append("us.liked = ?")
            params.append(1 if self.liked else 0)
        if self.on_watchlist is not None:
            conditions.append("us.on_watchlist = ?")
            params.append(1 if self.on_watchlist else 0)

        return " AND ".join(conditions), params
