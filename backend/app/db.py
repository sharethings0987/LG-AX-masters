"""SQLite 연결, 스키마, 정책 시드."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterator

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("AL_DB_PATH", APP_DIR.parent / "data" / "another_life.db"))
SEED_PATH = APP_DIR / "policies.json"

NOW = "(strftime('%Y-%m-%dT%H:%M:%SZ','now'))"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS sites (
    name   TEXT PRIMARY KEY,
    domain TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policies (
    key          TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    site         TEXT NOT NULL REFERENCES sites(name),
    hint         TEXT NOT NULL,
    description  TEXT NOT NULL,
    requirements TEXT NOT NULL,          -- JSON: 규칙 배열
    effects      TEXT NOT NULL,          -- JSON: {{"money": 12, "burn": -3}}
    active       INTEGER NOT NULL DEFAULT 1,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL DEFAULT {NOW}
);

CREATE TABLE IF NOT EXISTS plays (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id     TEXT NOT NULL,
    variant       TEXT NOT NULL,
    mode          TEXT NOT NULL,
    care          TEXT,
    auto          INTEGER NOT NULL DEFAULT 0,
    character     TEXT NOT NULL,         -- JSON
    result        TEXT NOT NULL,         -- JSON
    eligible      TEXT NOT NULL,         -- JSON: 정책 키 배열
    done          TEXT NOT NULL,
    missed        TEXT NOT NULL,
    heard         TEXT NOT NULL,
    year_map      TEXT NOT NULL,         -- JSON: [{{age, mood, text}}]
    goal_answer   TEXT,
    thanks_answer TEXT,
    created_at    TEXT NOT NULL DEFAULT {NOW},
    updated_at    TEXT NOT NULL DEFAULT {NOW}
);
CREATE INDEX IF NOT EXISTS idx_plays_player ON plays(player_id, id DESC);

CREATE TABLE IF NOT EXISTS letters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id  TEXT NOT NULL,
    play_id    INTEGER REFERENCES plays(id) ON DELETE SET NULL,
    recipient  TEXT NOT NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT {NOW}
);
CREATE INDEX IF NOT EXISTS idx_letters_player ON letters(player_id, id DESC);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI는 동기 의존성과 엔드포인트를 서로 다른 스레드에서 실행할 수 있다.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """요청 하나당 연결 하나. 성공하면 커밋, 예외면 롤백."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0] == 0:
            seed(conn)
        conn.commit()
    finally:
        conn.close()


def load_seed() -> dict:
    with SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def seed(conn: sqlite3.Connection) -> int:
    """policies.json 내용으로 사이트·정책을 덮어쓴다 (키 기준 upsert). 반영한 정책 수를 돌려준다."""
    data = load_seed()
    conn.executemany(
        "INSERT INTO sites(name, domain) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET domain = excluded.domain",
        list(data["sites"].items()),
    )
    rows = [
        (
            p["key"], p["name"], p["site"], p["hint"], p["description"],
            json.dumps(p["requirements"], ensure_ascii=False),
            json.dumps(p["effects"], ensure_ascii=False),
            int(p.get("active", True)), i,
        )
        for i, p in enumerate(data["policies"])
    ]
    conn.executemany(
        f"""INSERT INTO policies(key, name, site, hint, description, requirements, effects, active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              name = excluded.name, site = excluded.site, hint = excluded.hint,
              description = excluded.description, requirements = excluded.requirements,
              effects = excluded.effects, active = excluded.active,
              sort_order = excluded.sort_order, updated_at = {NOW}""",
        rows,
    )
    return len(rows)
