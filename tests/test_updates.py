from ats_sim import __version__, updates


def test_update_check_is_off_by_default_and_never_goes_online(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA" if __import__("os").name == "nt" else "XDG_DATA_HOME", str(tmp_path))
    updates._cache.clear()

    def boom():
        raise AssertionError("went online while off")

    r = updates.check(fetch=boom)
    assert r["enabled"] is False and r["latest"] is None


def test_update_check_when_turned_on(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA" if __import__("os").name == "nt" else "XDG_DATA_HOME", str(tmp_path))
    updates._cache.clear()
    assert updates.save_settings(check_updates=True) == {"check_updates": True}
    r = updates.check(fetch=lambda: "v99.0.0")
    assert r["newer"] and r["latest"] == "99.0.0"
    updates._cache.clear()
    assert updates.check(fetch=lambda: "v" + __version__)["newer"] is False
    updates._cache.clear()

    def offline():
        raise OSError("no network")

    assert "error" in updates.check(fetch=offline)
