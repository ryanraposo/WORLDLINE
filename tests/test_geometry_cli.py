
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
