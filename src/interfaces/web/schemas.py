"""Request models. Responses are plain dicts built by the core layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemRef(BaseModel):
    item_id: int


class WatchedBody(BaseModel):
    watched_on: str | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
    liked: bool | None = None
    keep_on_watchlist: bool = False


class LogCreate(BaseModel):
    item_id: int
    watched_on: str
    rating: int | None = Field(default=None, ge=1, le=10)
    liked: bool | None = None
    rewatch: bool = False


class LogPatch(BaseModel):
    watched_on: str | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
    liked: bool | None = None
    rewatch: bool | None = None


class RatingBody(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=10)


class LikedBody(BaseModel):
    liked: bool


class ConciergeBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    scope: str = Field(default="unseen", pattern="^(unseen|watchlist|all)$")


class ParseBody(BaseModel):
    query: str = Field(max_length=500)
