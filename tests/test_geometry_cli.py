
def test_geometry_json_uses_spatial_protocol(capsys, monkeypatch):
    import json
    from worldline import cli
    from worldline.spatial import project_spatial
    from test_spatial import sample
    seen = []
    def connected(_path, op, args):
        seen.append((op, args))
        return {"ok": True, "result": project_spatial(sample())}
    monkeypatch.setattr(cli, "_connect", connected)
    assert cli.main(["geometry", "--json"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["schema"] == "worldline.spatial-frame/1"
    assert seen == [("query", {"view": "geometry", "fresh": False})]


def test_geometry_title_filter_limits_json_windows(capsys, monkeypatch):
    import json
    from worldline import cli
    from worldline.spatial import project_spatial
    from test_spatial import sample

    monkeypatch.setattr(cli, "_connect", lambda *_args: {
        "ok": True, "result": project_spatial(sample())
    })
    assert cli.main(["geometry", "--json", "--title", "Editor"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert [item["title"] for item in value["windows"]] == ["Editor"]


def test_geometry_rejects_legacy_daemon_response(capsys, monkeypatch):
    from worldline import cli

    monkeypatch.setattr(cli, "_connect", lambda *_args: {
        "ok": True, "result": {"revision": 12, "facts": {}}
    })
    assert cli.main(["geometry", "--json"]) == 3
    assert "does not support geometry views" in capsys.readouterr().err
