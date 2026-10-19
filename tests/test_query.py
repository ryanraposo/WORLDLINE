import pytest

from worldline.query import QueryError, many, normalize, resolve, top_level

WORLD = {
    "host": {"hostname": "box", "tags": ["a", "b"], "nested": {"x": 1}},
    "storage": [
        {"target": "/", "percent": 10},
        {"target": "/home", "percent": 20},
    ],
    "windows": {"items": [{"title": "one"}, {"title": "two"}]},
}


def test_dot_and_bracket_paths():
    assert resolve(WORLD, "host.hostname") == "box"
    assert resolve(WORLD, "storage[1].percent") == 20
    assert normalize("storage[0].target") == ["storage", "0", "target"]
    assert normalize("storage[0][1]") == ["storage", "0", "1"]


def test_wildcards_return_all_matches():
    assert resolve(WORLD, "storage.*.target") == ["/", "/home"]
    assert resolve(WORLD, "host.tags.*") == ["a", "b"]
    assert resolve(WORLD, "windows.items.*.title") == ["one", "two"]


def test_missing_paths_raise_query_error():
    with pytest.raises(QueryError) as exc:
        resolve(WORLD, "host.nope")
    assert exc.value.path == "host.nope"

    with pytest.raises(QueryError):
        resolve(WORLD, "storage.9.percent")

    with pytest.raises(QueryError):
        resolve(WORLD, "host.hostname.more")


def test_many_preserves_scalar_and_multi_shapes():
    assert many(WORLD, ["host.hostname"]) == "box"
    assert many(WORLD, ["storage.0.percent"]) == 10
    assert many(WORLD, ["host.hostname", "storage.1.percent"]) == {
        "host.hostname": "box",
        "storage.1.percent": 20,
    }


def test_top_level_sections():
    assert top_level(["host.hostname", "storage[0].percent", "windows.items.*"]) == {
        "host",
        "storage",
        "windows",
    }
