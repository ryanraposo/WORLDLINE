from worldline.providers.gnome import GNOMEProvider


def test_gnome_provider_emits_session_facts(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    facts = {fact.key: fact.value for fact in GNOMEProvider().observe()}
    assert facts["gnome.session.type"] == "wayland"
    assert facts["gnome.session.desktop"] == "GNOME"

def test_gnome_provider_reports_installed_mutter_package(monkeypatch):
    from worldline.providers import gnome

    monkeypatch.setattr(
        gnome.shutil, "which",
        lambda name: "/usr/bin/" + name if name == "dpkg-query" else None,
    )
    monkeypatch.setattr(
        gnome, "_run",
        lambda args, timeout=0.8: (
            "50.1-0ubuntu2.5" if args[-1] == "mutter-common"
            else "50.1-0ubuntu1" if args[-1] == "gnome-shell"
            else None
        ),
    )
    facts = {fact.key: fact for fact in GNOMEProvider().observe()}
    assert facts["gnome.mutter.package_version"].value == "50.1-0ubuntu2.5"
    assert facts["gnome.mutter.package_version"].evidence.detail["package"] == "mutter-common"
    assert facts["gnome.shell.package_version"].value == "50.1-0ubuntu1"


def test_gnome_provider_omits_missing_package_version(monkeypatch):
    from worldline.providers import gnome

    monkeypatch.setattr(
        gnome.shutil, "which",
        lambda name: "/usr/bin/" + name if name == "dpkg-query" else None,
    )
    monkeypatch.setattr(gnome, "_run", lambda args, timeout=0.8: None)
    facts = {fact.key: fact for fact in GNOMEProvider().observe()}
    assert "gnome.mutter.package_version" not in facts
    assert "gnome.shell.package_version" not in facts


def test_fast_gnome_observation_avoids_service_queries(monkeypatch):
    import worldline.providers.gnome as module

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(module, "_run", lambda *_a, **_k:
                        (_ for _ in ()).throw(AssertionError("fast queried a service")))
    facts = {fact.key: fact for fact in GNOMEProvider().observe_fast()}
    assert facts["gnome.session.type"].value == "wayland"
    assert "gnome.atspi.bus.reachable" not in facts
    assert "gnome.mutter.package_version" not in facts
    assert all(fact.evidence.expires_at is not None for fact in facts.values())
