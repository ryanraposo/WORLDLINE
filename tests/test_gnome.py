from worldline.providers.gnome import GNOMEProvider


def test_gnome_provider_emits_session_facts(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    facts = {fact.key: fact.value for fact in GNOMEProvider().observe()}
    assert facts["gnome.session.type"] == "wayland"
    assert facts["gnome.session.desktop"] == "GNOME"
