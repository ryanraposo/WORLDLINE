from pathlib import Path

from worldline.daemon import WorldlineDaemon
from worldline.providers.host import HostRuntimeProvider


def fixture(tmp_path: Path) -> HostRuntimeProvider:
    proc = tmp_path / "proc"
    sys = tmp_path / "sys"
    proc.mkdir()
    (proc / "meminfo").write_text(
        "MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n"
        "SwapTotal:      4096000 kB\nSwapFree:       2048000 kB\n",
        encoding="ascii",
    )
    (proc / "loadavg").write_text("0.40 0.55 0.65 1/300 42\n", encoding="ascii")
    (proc / "uptime").write_text("1000.00 700.20\n", encoding="ascii")
    battery = sys / "class/power_supply/BAT0"
    battery.mkdir(parents=True)
    (battery / "type").write_text("Battery\n", encoding="ascii")
    (battery / "capacity").write_text("75\n", encoding="ascii")
    (battery / "status").write_text("Discharging\n", encoding="ascii")
    (battery / "serial_number").write_text("SECRET\n", encoding="ascii")
    display = sys / "class/drm/card1-HDMI-A-1"
    display.mkdir(parents=True)
    (display / "status").write_text("connected\n", encoding="ascii")
    return HostRuntimeProvider(proc_root=proc, sys_root=sys, clock=lambda: 1000)


def test_host_surface_reports_bounded_kernel_truth(tmp_path):
    provider = fixture(tmp_path)
    facts = {fact.key: fact for fact in provider.observe_fast()}
    assert facts["host.memory.available_kib"].value == 8192000
    assert facts["host.load.1m"].value == 0.40
    assert facts["host.uptime.seconds"].value == 1000.0
    assert facts["host.power.sources"].value == [{
        "kernel_name": "BAT0", "type": "Battery", "status": "Discharging",
        "percent": 75.0,
    }]
    assert facts["host.displays.connectors"].value == [{
        "kernel_name": "card1-HDMI-A-1", "status": "connected",
    }]
    assert all(fact.evidence.expires_at == 1005 or
               fact.evidence.expires_at == 1010 for fact in facts.values())
    assert "SECRET" not in str(facts)


def test_host_source_absence_is_not_an_empty_result(tmp_path):
    provider = HostRuntimeProvider(proc_root=tmp_path / "missing",
                                   sys_root=tmp_path / "absent", clock=lambda: 1000)
    assert list(provider.observe()) == []


def test_host_source_accepts_no_unbounded_or_private_data(tmp_path):
    provider = fixture(tmp_path)
    (provider.proc_root / "meminfo").write_text("x" * 20000, encoding="ascii")
    battery = provider.sys_root / "class/power_supply/BAT0"
    (battery / "capacity").write_text("9999\n", encoding="ascii")
    facts = {fact.key: fact for fact in provider.observe()}
    assert not any(key.startswith("host.memory.") for key in facts)
    assert "percent" not in facts["host.power.sources"].value[0]


def test_provider_available_via_fast_query_only_when_requested(tmp_path):
    daemon = WorldlineDaemon()
    import time
    host = fixture(tmp_path)
    host.clock = time.time
    daemon.providers["host"] = host
    untouched = daemon.dispatch({"op": "query", "args": {}})
    assert "host.memory.total_kib" not in untouched["result"]["facts"]
    result = daemon.dispatch({"op": "query", "args": {
        "refresh": ["host"], "mode": "fast",
    }})
    assert result["ok"]
    assert result["result"]["facts"]["host.memory.total_kib"]["value"] == 16384000
    assert "host" in [p["name"] for p in daemon.dispatch({"op": "sources", "args": {}})["result"]["providers"]]
