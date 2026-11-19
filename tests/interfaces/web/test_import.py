import csv
import io
import zipfile


def _csv(fields, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


DIARY = _csv(
    ["Date", "Name", "Year", "Letterboxd URI", "Rating", "Rewatch", "Tags", "Watched Date"],
    [
        {
            "Date": "2024-01-02",
            "Name": "Tiny Film",
            "Year": "1999",
            "Letterboxd URI": "u/tiny",
            "Rating": "4",
            "Rewatch": "",
            "Tags": "",
            "Watched Date": "2024-01-01",
        }
    ],
)
WATCHLIST = _csv(
    ["Date", "Name", "Year", "Letterboxd URI"],
    [{"Date": "2023-05-05", "Name": "Later Film", "Year": "2001", "Letterboxd URI": "u/later"}],
)


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, b in files.items():
            zf.writestr(n, b)
    return buf.getvalue()


def _up(client, name, data, field="file"):
    return client.post("/api/import/letterboxd", files={field: (name, data)})


def test_upload_single_diary_csv(client):
    r = _up(client, "diary.csv", DIARY)
    assert r.status_code == 200
    assert r.json()["diary"] == 1
    log = client.get("/api/log").json()
    assert log["total"] == 1 and log["entries"][0]["rating"] == 8


def test_upload_zip_and_idempotent(client):
    z = _zip({"diary.csv": DIARY, "watchlist.csv": WATCHLIST})
    for _ in range(2):
        r = _up(client, "export.zip", z)
        assert r.status_code == 200
    assert client.get("/api/log").json()["total"] == 1
    assert client.get("/api/watchlist").json()["total"] == 1


def test_unknown_csv_name_422(client):
    r = _up(client, "random.csv", b"a,b\n1,2")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_upload"


def test_bad_zip_and_traversal_rejected(client):
    r = _up(client, "x.zip", b"not a zip")
    assert r.status_code == 422
    evil = _zip({"../escape.csv": b"x"})
    r = _up(client, "x.zip", evil)
    assert r.status_code == 422


def test_deleted_entry_stays_deleted_after_reupload(client):
    _up(client, "diary.csv", DIARY)
    eid = client.get("/api/log").json()["entries"][0]["entry_id"]
    client.delete(f"/api/log/{eid}")
    _up(client, "diary.csv", DIARY)
    assert client.get("/api/log").json()["total"] == 0


def test_missing_file_field_422(client):
    assert _up(client, "a.csv", b"x", field="other").status_code == 422
