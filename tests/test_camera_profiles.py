import json

import pytest

from multicam.core.services import CameraProfileStore


def test_profile_round_trip(tmp_path):
    store = CameraProfileStore(tmp_path)
    profile = {
        "name": "SWIR indoor",
        "camera": {"backend": "aravis"},
        "controls": {"exposure": 493.0},
    }

    path = store.save(profile["name"], profile)

    assert path == tmp_path / "SWIR indoor.json"
    assert store.load(profile["name"]) == profile
    assert not path.with_suffix(".json.tmp").exists()

    profiles, errors = store.list_profiles()
    assert profiles == [profile]
    assert errors == []


def test_invalid_name_is_rejected(tmp_path):
    store = CameraProfileStore(tmp_path)

    with pytest.raises(ValueError):
        store.save("...", {"name": "invalid"})


def test_bad_profile_does_not_hide_good_profiles(tmp_path):
    store = CameraProfileStore(tmp_path)
    store.save("good", {"name": "good", "controls": {}})
    (tmp_path / "broken.json").write_text("not json")

    profiles, errors = store.list_profiles()

    assert profiles == [
        {"name": "good", "camera": {}, "controls": {}}
    ]
    assert len(errors) == 1
    assert errors[0][0].name == "broken.json"


def test_delete_reports_presence(tmp_path):
    store = CameraProfileStore(tmp_path)
    store.save("temporary", {"name": "temporary"})

    assert store.delete("temporary") is True
    assert store.delete("temporary") is False


def test_saved_json_is_readable(tmp_path):
    store = CameraProfileStore(tmp_path)
    path = store.save("profile", {"name": "profile"})

    assert json.loads(path.read_text()) == {"name": "profile"}
