from worldline.providers.gnome import GNOMEProvider


def test_gnome_provider_emits_session_facts(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    facts = {fact.key: fact.value for fact in GNOMEProvider().observe()}
    assert facts["gnome.session.type"] == "wayland"
    assert facts["gnome.session.desktop"] == "GNOME"

def test_fast_gnome_observation_avoids_subprocess_and_queries(monkeypatch):
    import worldline.providers.gnome as module
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(module, "_run", lambda *_a, **_k:
                        (_ for _ in ()).throw(AssertionError("fast must not call services")))
    facts = {fact.key: fact for fact in GNOMEProvider().observe_fast()}
    assert facts["gnome.session.type"].value == "wayland"
    assert "gnome.atspi.bus.reachable" not in facts
    assert all(fact.evidence.expires_at is not None for fact in facts.values())
