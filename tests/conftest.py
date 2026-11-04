import pytest

from ps5cheater.db import Database

GAME = "gta-vice-city-definitive-edition"


@pytest.fixture(autouse=True)
def mock_console(monkeypatch, tmp_path):
    monkeypatch.setenv("PS5CHEATER_MOCK", "1")
    monkeypatch.setenv("PS5CHEATER_HOME", str(tmp_path))


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.set_setting("console_ip", "192.0.2.50")
    return database
