"""SQLite storage for games, cheats, settings and run history."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .paths import SEED_DIR

BUTTONS = frozenset(
    "UP DOWN LEFT RIGHT L1 R1 L2 R2 CROSS CIRCLE SQUARE TRIANGLE".split()
)
MAX_SEQUENCE = 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'PS5',
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cheats (
    id INTEGER PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    sequence TEXT NOT NULL,
    warning TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    UNIQUE (game_id, slug)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    game_id TEXT NOT NULL,
    cheats TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    finished_at REAL
);
"""


class ValidationError(ValueError):
    """Raised when user supplied data cannot be stored."""


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        raise ValidationError("A name with letters or digits is required.")
    return slug


def parse_sequence(value: str | list[str]) -> list[str]:
    tokens = value.split() if isinstance(value, str) else list(value)
    tokens = [str(token).upper() for token in tokens]
    invalid = sorted(set(tokens) - BUTTONS)
    if invalid:
        raise ValidationError(
            f"Unknown buttons: {', '.join(invalid)}. Allowed: {', '.join(sorted(BUTTONS))}."
        )
    if not 1 <= len(tokens) <= MAX_SEQUENCE:
        raise ValidationError(f"A sequence needs 1-{MAX_SEQUENCE} buttons.")
    return tokens


def _cheat_row(row: sqlite3.Row) -> dict:
    cheat = dict(row)
    cheat["sequence"] = cheat["sequence"].split()
    cheat["verified"] = bool(cheat["verified"])
    return cheat


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
        self.seed()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def seed(self) -> None:
        for pack in sorted(SEED_DIR.glob("*.json")):
            data = json.loads(pack.read_text(encoding="utf-8"))
            key = f"seed:{data['game']['id']}:{data.get('revision', 1)}"
            if self.get_setting(key) is None:
                self.import_pack(data, replace=False)
                self._mark_verified(data)
                self.set_setting(key, "1")

    def _mark_verified(self, pack: dict) -> None:
        # A new pack revision must not overwrite user edits, so only this flag moves.
        slugs = [c.get("slug") or slugify(c["name"]) for c in pack["cheats"] if c.get("verified")]
        with self._connect() as conn:
            conn.executemany(
                "UPDATE cheats SET verified = 1 WHERE game_id = ? AND slug = ?",
                [(pack["game"]["id"], slug) for slug in slugs],
            )

    def get_setting(self, key: str, default=None):
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def list_games(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT g.*, COUNT(c.id) AS cheat_count FROM games g "
                "LEFT JOIN cheats c ON c.game_id = g.id GROUP BY g.id ORDER BY g.title"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_game(self, game_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        return dict(row) if row else None

    def add_game(self, title: str, platform="PS5", notes="", source="", game_id=None) -> dict:
        title = title.strip()
        if not title:
            raise ValidationError("A game title is required.")
        game_id = slugify(game_id or title)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO games (id, title, platform, notes, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
                "title = excluded.title, platform = excluded.platform, "
                "notes = excluded.notes, source = excluded.source",
                (game_id, title, platform, notes, source, time.time()),
            )
        return self.get_game(game_id)

    def delete_game(self, game_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM games WHERE id = ?", (game_id,)).rowcount > 0

    def list_cheats(self, game_id: str, query: str = "") -> list[dict]:
        sql = "SELECT * FROM cheats WHERE game_id = ?"
        args: list = [game_id]
        if query:
            sql += " AND (name LIKE ? OR slug LIKE ? OR category LIKE ?)"
            args += [f"%{query}%"] * 3
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY id", args).fetchall()
        return [_cheat_row(row) for row in rows]

    def get_cheats(self, game_id: str, slugs: list[str]) -> list[dict]:
        """Return cheats in the requested order, keeping duplicates."""
        known = {cheat["slug"]: cheat for cheat in self.list_cheats(game_id)}
        missing = sorted(set(slugs) - set(known))
        if missing:
            raise ValidationError(f"Unknown cheats for {game_id}: {', '.join(missing)}.")
        return [known[slug] for slug in slugs]

    def add_cheat(self, game_id, name, sequence, category="General", warning="",
                  slug=None, verified=False, replace=True) -> dict:
        if not self.get_game(game_id):
            raise ValidationError(f"Unknown game: {game_id}.")
        slug = slugify(slug or name)
        tokens = parse_sequence(sequence)
        conflict = (
            "DO UPDATE SET name = excluded.name, category = excluded.category, "
            "sequence = excluded.sequence, warning = excluded.warning, "
            "verified = excluded.verified"
            if replace else "DO NOTHING"
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cheats (game_id, slug, name, category, sequence, warning, verified) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (game_id, slug) {conflict}",
                (game_id, slug, name.strip(), category, " ".join(tokens), warning, int(verified)),
            )
            row = conn.execute(
                "SELECT * FROM cheats WHERE game_id = ? AND slug = ?", (game_id, slug)
            ).fetchone()
        return _cheat_row(row)

    def delete_cheat(self, game_id: str, slug: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM cheats WHERE game_id = ? AND slug = ?", (game_id, slug)
            )
            return cursor.rowcount > 0

    def import_pack(self, pack: dict, replace: bool = True) -> dict:
        if not isinstance(pack, dict) or not isinstance(pack.get("game"), dict):
            raise ValidationError('A pack needs a "game" object and a "cheats" list.')
        game_data = pack["game"]
        cheats = pack.get("cheats")
        if not isinstance(cheats, list):
            raise ValidationError('A pack needs a "cheats" list.')
        for cheat in cheats:
            parse_sequence(cheat["sequence"])
        game = self.add_game(
            game_data.get("title", ""), game_data.get("platform", "PS5"),
            game_data.get("notes", ""), game_data.get("source", ""), game_data.get("id"),
        )
        for cheat in cheats:
            self.add_cheat(
                game["id"], cheat["name"], cheat["sequence"], cheat.get("category", "General"),
                cheat.get("warning", ""), cheat.get("slug"), cheat.get("verified", False), replace,
            )
        return {"game": game, "imported": len(cheats)}

    def export_pack(self, game_id: str) -> dict:
        game = self.get_game(game_id)
        if not game:
            raise ValidationError(f"Unknown game: {game_id}.")
        return {
            "game": {k: game[k] for k in ("id", "title", "platform", "notes", "source")},
            "cheats": [
                {k: cheat[k] for k in ("slug", "name", "category", "sequence", "warning", "verified")}
                for cheat in self.list_cheats(game_id)
            ],
        }

    def start_run(self, game_id: str, slugs: list[str]) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (game_id, cheats, status, started_at) VALUES (?, ?, 'running', ?)",
                (game_id, json.dumps(slugs), time.time()),
            )
            return cursor.lastrowid

    def finish_run(self, run_id: int, status: str, detail: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, detail = ?, finished_at = ? WHERE id = ?",
                (status, detail, time.time(), run_id),
            )

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{**dict(row), "cheats": json.loads(row["cheats"])} for row in rows]
