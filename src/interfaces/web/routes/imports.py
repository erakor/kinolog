from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.core.db import Database
from src.ingest.letterboxd import load_letterboxd
from src.interfaces.web.deps import get_state
from src.interfaces.web.state import AppState

router = APIRouter(prefix="/api/import")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# single-CSV uploads are stored under the name the loader expects
CSV_TARGETS = {
    "diary.csv": "diary.csv",
    "watched.csv": "watched.csv",
    "watchlist.csv": "watchlist.csv",
    "ratings.csv": "ratings.csv",
    "films.csv": "likes/films.csv",
    "likes.csv": "likes/films.csv",
}


def _bad(message: str, status: int = 422) -> HTTPException:
    return HTTPException(status, {"code": "invalid_upload", "message": message})


def _read_capped(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise _bad("File is larger than 20 MB", 413)
    return data


@router.post("/letterboxd")
def import_letterboxd(  # sync: runs in the threadpool, so the import never blocks the event loop
    file: UploadFile,
    state: AppState = Depends(get_state),
):
    name = Path(file.filename or "").name.lower()
    data = _read_capped(file)

    with tempfile.TemporaryDirectory(prefix="kinolog-import-") as tmp:
        root = Path(tmp)
        if name.endswith(".zip"):
            target = root / "letterboxd-upload.zip"
            target.write_bytes(data)
            if not zipfile.is_zipfile(target):
                raise _bad("Not a valid zip file")
        elif name in CSV_TARGETS:
            target = root / CSV_TARGETS[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        else:
            raise _bad(
                "Upload a Letterboxd export .zip or one of: " + ", ".join(sorted(CSV_TARGETS))
            )
        with state.db_lock:
            return _load(state.db, root, state)


def _load(db: Database, root: Path, state: AppState) -> dict:
    try:
        stats = load_letterboxd(db, root)
    except FileNotFoundError as e:
        raise _bad(str(e)) from e
    except (ValueError, UnicodeDecodeError, zipfile.BadZipFile) as e:
        raise _bad(f"Could not read the export: {e}") from e
    state.invalidate()
    return stats
