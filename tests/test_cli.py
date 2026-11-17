import json

import pytest

from worldline import cli
from worldline.daemon import WorldlineDaemon
import worldline.current as current_module


@pytest.fixture
def connected(monkeypatch):
    calls = []
    window = {"stable_id": "window:42:7", "geometry": {"frame": {"x": 415}}}
    data = {
        "host": {"hostname": "machine"},
        "os": {"kernel": "6.1"},
        "memory": {"percent": 22},
        "windows": {"source": "at-spi2", "available": True,
                    "items": [window], "by_id": {window["stable_id"]: window}},
    }

    def observe(names, *, full=False):
        name = next(iter(names))
        calls.append(name)
        return {name: data.get(name, {"available": False, "reason": "not present"})}

    monkeypatch.setattr(current_module, "observe", observe)
    daemon = WorldlineDaemon()
    monkeypatch.setattr(cli, "_connect", lambda _path, op, args: daemon.dispatch({
        "op": op, "args": args,
    }))
    return daemon, calls, data


def run(capsys, *args):
    code = cli.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_only_queries_an_already_running_daemon(capsys, monkeypatch, tmp_path):
    calls = []
    socket = str(tmp_path / "running.sock")

    def answer(path, op, args=None, **kwargs):
        calls.append((path, op, args, kwargs))
        return {"ok": True, "result": {"values": {"host.hostname": "machine"}}}

    monkeypatch.setattr(cli, "request", answer)
    code, out, err = run(capsys, "--socket", socket, "host.hostname")
    assert (code, json.loads(out), err) == (0, "machine", "")
    assert calls == [(socket, "query", {
        "fresh": False, "full": False, "paths": ["host.hostname"],
    }, {})]


def test_missing_daemon_fails_closed_without_starting_one(capsys, monkeypatch, tmp_path):
    socket = str(tmp_path / "missing.sock")
    calls = []

    def unavailable(path, op, args=None, **kwargs):
        calls.append((path, op))
        raise FileNotFoundError(path)

    monkeypatch.setattr(cli, "request", unavailable)
    code, out, err = run(capsys, "--socket", socket, "host.hostname")
    assert code == 3 and out == ""
    issue = json.loads(err)
    assert issue["error"] == "unavailable"
    assert "not running" in issue["message"]
    assert calls == [(socket, "query")], "the CLI must not retry or auto-start a daemon"


def test_cli_has_no_daemon_start_machinery():
    import inspect

    source = inspect.getsource(cli)
    assert "Popen" not in source
    assert "start_new_session" not in source
    assert not hasattr(cli, "_daemon_runtime")


def test_scalar_and_multiple_path_queries_keep_value_shape(capsys, connected):
    code, out, err = run(capsys, "host.hostname")
    assert (code, json.loads(out), err) == (0, "machine", "")
    code, out, err = run(capsys, "os.kernel", "memory.percent")
    assert code == 0 and err == ""
    assert json.loads(out) == {"os.kernel": "6.1", "memory.percent": 22}


def test_full_snapshot_and_discovery(capsys, connected):
    code, out, err = run(capsys)
    world = json.loads(out)
    assert code == 0 and err == ""
    assert world["schema"] == 1 and world["revision"] > 0
    assert world["windows"]["source"] == "at-spi2"
    assert world["sources"]["windows"]["available"] is True
    assert "windows" in json.loads(run(capsys, "--list")[1])
    paths = json.loads(run(capsys, "--list", "windows")[1])
    assert "windows.by_id.window:42:7.geometry.frame.x" in paths


def test_explain_and_fresh_target_one_source(capsys, connected):
    _daemon, calls, _data = connected
    code, out, err = run(capsys, "--explain", "windows.by_id.window:42:7.geometry.frame.x")
    fact = json.loads(out)
    assert code == 0 and err == ""
    assert fact["value"] == 415
    assert fact["evidence"]["source"] == "at-spi2"
    calls.clear()
    code, out, err = run(capsys, "--fresh", "windows.available")
    assert code == 0 and json.loads(out) is True and err == ""
    assert calls == ["windows"]
    code, out, err = run(capsys, "sources.windows.available")
    assert code == 0 and json.loads(out) is True and err == ""


def test_errors_are_json(capsys, connected):
    code, out, err = run(capsys, "host.nope")
    assert code == 1 and out == "" and json.loads(err)["error"] == "no_such_path"
    code, out, err = run(capsys, "nope.value")
    assert code == 2 and out == "" and json.loads(err)["error"] == "bad_request"
