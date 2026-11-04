import pytest

from conftest import GAME
from ps5cheater.db import BUTTONS, Database, ValidationError, parse_sequence


def test_seed_is_loaded_once(tmp_path):
    path = tmp_path / "seed.db"
    first = Database(path)
    assert first.list_games()[0]["cheat_count"] == 52
    first.delete_cheat(GAME, "full-armor")
    assert len(Database(path).list_cheats(GAME)) == 51


def test_seed_sequences_are_valid_and_unique(db):
    cheats = db.list_cheats(GAME)
    assert all(set(cheat["sequence"]) <= BUTTONS for cheat in cheats)
    assert len({tuple(cheat["sequence"]) for cheat in cheats}) == len(cheats)


def test_verified_flag_only_on_tested_cheat(db):
    verified = [cheat["slug"] for cheat in db.list_cheats(GAME) if cheat["verified"]]
    assert verified == ["full-health-and-vehicle-repair"]


def test_any_game_can_be_added(db):
    game = db.add_game("Other Game")
    db.add_cheat(game["id"], "Jump", "up cross")
    assert db.list_cheats(game["id"])[0]["sequence"] == ["UP", "CROSS"]


@pytest.mark.parametrize("sequence", ["", "UP SHOUT", "OPTIONS", ["UP"] * 65])
def test_bad_sequences_are_rejected(sequence):
    with pytest.raises(ValidationError):
        parse_sequence(sequence)


def test_get_cheats_keeps_order_and_duplicates(db):
    game = db.add_game("Order")["id"]
    db.add_cheat(game, "A", "UP")
    db.add_cheat(game, "B", "DOWN")
    assert [c["slug"] for c in db.get_cheats(game, ["b", "a", "b"])] == ["b", "a", "b"]
    with pytest.raises(ValidationError):
        db.get_cheats(game, ["missing"])


def test_pack_round_trip(db):
    pack = db.export_pack(GAME)
    pack["game"]["id"] = "copy"
    assert db.import_pack(pack)["imported"] == 52
    assert len(db.list_cheats("copy")) == 52


def test_delete_game_removes_cheats(db):
    assert db.delete_game(GAME)
    assert db.list_cheats(GAME) == []


def test_invalid_pack_changes_nothing(db):
    with pytest.raises(ValidationError):
        db.import_pack({"game": {"title": "Bad"}, "cheats": [{"name": "x", "sequence": "NOPE"}]})
    assert db.get_game("bad") is None
