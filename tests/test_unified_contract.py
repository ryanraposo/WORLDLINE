from __future__ import annotations

from worldline.daemon import WorldlineDaemon
from worldline.model import Evidence, Fact
import worldline.observe as observe


def rpc(daemon, op, **args):
    return daemon.dispatch({"protocol": 1, "op": op, "args": args})


def test_protocol_mismatch_fails_before_any_mutation():
    daemon = WorldlineDaemon()
    response = daemon.dispatch({"protocol": 99, "op": "event",
                                "args": {"key": "task.done", "value": True}})
    assert response["error"]["code"] == "protocol_mismatch"
    assert daemon.store.revision == 0
    domain = rpc(daemon, "hello")["result"]["domain_id"]
    assert domain
    skew = rpc(daemon, "fence", domain_id="previous-daemon")
    assert skew["error"]["code"] == "revision_domain_mismatch"
    assert daemon.store.revision == 0


def test_one_revision_domain_rejects_stale_and_focus_conflicts():
    daemon = WorldlineDaemon()
    fence = rpc(daemon, "fence")
    baseline = fence["result"]["revision"]
    rpc(daemon, "event", event={"source": "atspi",
                                 "facts": {"ui.focus.name": "Editor"}})
    waiting = rpc(daemon, "wait", after_revision=baseline,
                  predicates=[{"path": "ui.focus.name", "op": "eq",
                               "value": "Editor", "fresh_after": baseline}])
    assert waiting["result"]["code"] == "ready"
    newer = rpc(daemon, "fence")["result"]["revision"]
    stale = rpc(daemon, "wait", after_revision=newer,
                predicates=[{"path": "ui.focus.name", "op": "eq",
                             "value": "Editor", "fresh_after": newer}])
    assert stale["result"]["code"] == "pending"
    rpc(daemon, "event", event={"source": "atspi",
                                 "facts": {"ui.focus.name": "Other"}})
    conflict = rpc(daemon, "wait", after_revision=newer,
                   conflict_paths=["ui.focus"],
                   predicates=[{"path": "never", "op": "exists"}])
    assert conflict["result"]["code"] == "conflict"
    armed = rpc(daemon, "arm", id="focus-editor",
                predicates=[{"path": "ui.focus.name", "op": "eq", "value": "Editor"}])
    assert armed["result"]["armed"]
    rpc(daemon, "event", event={"source": "atspi",
                                 "facts": {"ui.focus.name": "Editor"}})
    assert rpc(daemon, "wait", id="focus-editor")["result"]["code"] == "ready"


def test_failed_actuator_cannot_become_verified_receipt():
    daemon = WorldlineDaemon()
    fence = rpc(daemon, "fence")["result"]
    baseline, domain = fence["revision"], fence["domain_id"]
    rpc(daemon, "event", event={"source": "cua",
                                 "facts": {"ui.result": "done"}})
    forged = rpc(daemon, "receipt", owner="cua", action_id="a",
                 before_revision=baseline, domain_id=domain, action_ok=True,
                 predicate={"path": "ui.result", "op": "eq", "value": "done"})
    assert forged["result"]["outcome"] == "unverified"
    rpc(daemon, "event", event={"source": "atspi",
                                 "facts": {"ui.result": "done"}})
    failed = rpc(daemon, "receipt", owner="cua", action_id="a",
                 before_revision=baseline, domain_id=domain, action_ok=False,
                 predicate={"path": "ui.result", "op": "eq", "value": "done"})
    assert failed["result"]["outcome"] == "failed"
    verified = rpc(daemon, "receipt", owner="cua", action_id="a",
                   before_revision=baseline, domain_id=domain, action_ok=True,
                   predicate={"path": "ui.result", "op": "eq", "value": "done"})
    assert verified["result"]["outcome"] == "verified"
    assert verified["result"]["observation"]["evidence"]["source"] == "rpc:atspi"
    assert rpc(daemon, "receipt", owner="cua", domain_id="previous-daemon",
               before_revision=baseline, action_ok=True,
               predicate={"path": "ui.result", "op": "exists"})["error"]["code"] == "revision_domain_mismatch"


def test_branch_wait_returns_its_observation_witness():
    daemon = WorldlineDaemon()
    fence = rpc(daemon, "fence")["result"]
    rpc(daemon, "event", event={"source": "atspi", "facts": {"ui.dialog": "Saved"}})
    wait = rpc(daemon, "wait", after_revision=fence["revision"], branches=[
        {"id": "success", "predicates": [{"path": "ui.dialog", "op": "eq", "value": "Saved"}]},
        {"id": "failure", "predicates": [{"path": "ui.dialog", "op": "eq", "value": "Error"}]},
    ])["result"]
    assert wait["matched_branch"] == "success"
    assert wait["matched_predicates"] == [{"path": "ui.dialog", "op": "eq", "value": "Saved"}]
    assert wait["witnesses"][0]["evidence"]["source"] == "rpc:atspi"


def test_exact_compositor_frame_preserves_component_extents(monkeypatch):
    monkeypatch.setattr(observe, "_atspi_windows", lambda: {
        "available": True, "count": 1, "items": [{
            "pid": 42, "stable_id": "window:42:accessible", "title": "Editor",
            "app": "Editor", "frame": {"x": 11, "y": 22, "width": 400, "height": 300},
            "focused": True}]})
    monkeypatch.setattr(observe, "_display", lambda: {
        "screen": {"x": 0, "y": 0, "width": 1000, "height": 800},
        "monitors": []})
    monkeypatch.setattr(observe, "_compositor_windows", lambda: {
        "available": True, "source": "cua-gnome-shell", "helper_api": 8,
        "items": [{"pid": 42, "id": 7, "title": "Editor",
                   "x": 8, "y": 19, "w": 406, "h": 306,
                   "focused": True, "visible": True, "minimized": False}]})
    window = observe._windows()["items"][0]
    assert window["geometry"]["frame"] == {"x": 8, "y": 19, "width": 406, "height": 306}
    assert window["component_extents"] == {"x": 11, "y": 22, "width": 400, "height": 300}
    assert window["geometry"]["frame_source"] == "cua-gnome-shell-frame"
    assert window["compositor_id"] == 7 and window["compositor_verified"]


def test_compositor_stacking_bounds_exposure_and_reports_verified_focus(monkeypatch):
    monkeypatch.setattr(observe, "_atspi_windows", lambda: {
        "available": True, "count": 1, "items": [{
            "pid": 42, "stable_id": "window:42:accessible", "title": "Editor",
            "app": "Editor", "frame": {"x": 10, "y": 10, "width": 100, "height": 100},
            "focused": False}]})
    monkeypatch.setattr(observe, "_display", lambda: {
        "screen": {"x": 0, "y": 0, "width": 500, "height": 500},
        "monitors": []})
    monkeypatch.setattr(observe, "_compositor_windows", lambda: {
        "available": True, "source": "cua-gnome-shell", "helper_api": 8,
        "items": [
            {"pid": 42, "id": 7, "title": "Editor", "x": 10, "y": 10,
             "w": 100, "h": 100, "focused": False, "visible": True,
             "minimized": False, "stacking": 0},
            {"pid": 55, "id": 9, "title": "Dialog", "x": 60, "y": 10,
             "w": 100, "h": 100, "focused": True, "visible": True,
             "minimized": False, "stacking": 1},
        ]})
    world = observe._windows()
    editor = world["by_id"]["window:42:accessible"]
    assert editor["geometry"]["exposure"]["occlusion_known"] is True
    assert editor["geometry"]["exposure"]["exposed_fraction"] == 0.5
    assert editor["geometry"]["exposure"]["pixel_accurate"] is False
    assert world["stacking_order"] == ["window:42:accessible", "window:55:9"]
    assert world["focus"]["compositor_id"] == 9
    assert world["focus"]["verified"] is True
