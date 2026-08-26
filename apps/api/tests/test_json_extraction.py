"""Tests for JSON ingestion.

Raw JSON indexes badly — the content drowns in punctuation and a chunk boundary
can land mid-object — so files are flattened to one `path: value` line per leaf.
These pin that shape, and the forgiving behaviour for files that do not parse.
"""
import io
import json

from app.main import extract_json_text


def write(tmp_path, data, name="doc.json", raw=None):
    path = tmp_path / name
    path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")
    return path


def test_flattens_nested_objects(tmp_path):
    path = write(tmp_path, {"service": {"name": "meridian", "port": 8000}})
    lines = extract_json_text(path).split("\n")

    assert "service.name: meridian" in lines
    assert "service.port: 8000" in lines


def test_arrays_keep_their_index(tmp_path):
    path = write(tmp_path, {"users": [{"name": "Ana"}, {"name": "Bo"}]})
    lines = extract_json_text(path).split("\n")

    assert "users[0].name: Ana" in lines
    assert "users[1].name: Bo" in lines


def test_top_level_array(tmp_path):
    path = write(tmp_path, [{"id": 1}, {"id": 2}])
    lines = extract_json_text(path).split("\n")

    assert "[0].id: 1" in lines
    assert "[1].id: 2" in lines


def test_scalars_and_null(tmp_path):
    path = write(tmp_path, {"enabled": True, "ratio": 0.5, "note": None})
    lines = extract_json_text(path).split("\n")

    assert "enabled: True" in lines
    assert "ratio: 0.5" in lines
    assert "note: null" in lines


def test_empty_containers_are_not_dropped(tmp_path):
    path = write(tmp_path, {"tags": [], "meta": {}})
    text = extract_json_text(path)

    assert "tags: (empty list)" in text
    assert "meta: (empty object)" in text


def test_unicode_survives(tmp_path):
    path = write(tmp_path, {"জেলা": "রাজবাড়ী"})
    assert "জেলা: রাজবাড়ী" in extract_json_text(path)


def test_invalid_json_is_indexed_as_plain_text(tmp_path):
    """A .json that does not parse is still text; losing it would be worse."""
    path = write(tmp_path, None, raw="{not valid json, but readable words}")
    assert "readable words" in extract_json_text(path)


def test_every_leaf_appears_once(tmp_path):
    data = {"a": {"b": {"c": "deep"}}, "list": [1, 2, 3]}
    lines = [l for l in extract_json_text(write(tmp_path, data)).split("\n") if l]

    assert lines.count("a.b.c: deep") == 1
    assert len(lines) == 4  # one deep leaf + three list entries


def test_upload_accepts_json(client):
    payload = json.dumps({"district": "রাজবাড়ী", "river": "পদ্মা"}).encode()
    res = client.post(
        "/documents/upload",
        files={"file": ("data.json", io.BytesIO(payload), "application/json")},
    )

    assert res.status_code == 200
    assert res.json()["document"]["type"] == "application/json"


def test_upload_accepts_json_with_generic_content_type(client):
    res = client.post(
        "/documents/upload",
        files={"file": ("data.json", io.BytesIO(b'{"k": "v"}'), "application/octet-stream")},
    )

    assert res.status_code == 200
    assert res.json()["document"]["type"] == "application/json"
