import json

from worldline import cli


def run(capsys, *args):
    code = cli.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_scalar_query(capsys):
    code, out, err = run(capsys, "host.hostname")
    assert code == 0
    assert isinstance(json.loads(out), str)
    assert err == ""


def test_multiple_paths(capsys):
    code, out, err = run(capsys, "os.kernel", "memory.percent")
    assert code == 0
    value = json.loads(out)
    assert set(value) == {"os.kernel", "memory.percent"}
    assert err == ""


def test_list_sections(capsys):
    code, out, err = run(capsys, "--list")
    assert code == 0
    assert "windows" in json.loads(out)
    assert err == ""


def test_snapshot_shape(capsys):
    code, out, err = run(capsys)
    assert code == 0
    world = json.loads(out)
    assert world["schema"] == 1
    assert world["windows"]["source"] == "at-spi2"
    assert err == ""


def test_missing_key(capsys):
    code, out, err = run(capsys, "host.nope")
    assert code == 1
    assert out == ""
    assert json.loads(err)["error"] == "no_such_path"


def test_unknown_section(capsys):
    code, out, err = run(capsys, "nope.value")
    assert code == 2
    assert json.loads(err)["error"] == "bad_request"


def test_window_geometry_query(capsys, monkeypatch):
    import worldline.cli as cli_module

    monkeypatch.setattr(
        cli_module,
        "observe",
        lambda sections=None, full=False: {
            "windows": {
                "items": [
                    {
                        "title": "ChatGPT",
                        "geometry": {
                            "frame": {"x": 415, "y": 176, "width": 10, "height": 10}
                        },
                    }
                ]
            }
        },
    )
    code, out, err = run(capsys, "windows.items.0.geometry.frame.x")
    assert code == 0
    assert json.loads(out) == 415
    assert err == ""
