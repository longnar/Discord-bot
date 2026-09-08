import sqlite3
from pathlib import Path

from app.config import DB_PATH, SCHEMA_PATH


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    with get_connection() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(frame_data)").fetchall()
        }
        migrations = {
            "active": "INTEGER",
            "recovery": "INTEGER",
            "guard": "TEXT DEFAULT ''",
            "adv_on_block": "TEXT DEFAULT ''",
            "adv_on_hit": "TEXT DEFAULT ''",
            "invulnerability": "TEXT DEFAULT ''",
            "image_url": "TEXT DEFAULT ''",
        }
        for column, definition in migrations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE frame_data ADD COLUMN {column} {definition}")

    print(f"Database initialized at {DB_PATH}")


def fetch_character_id(conn: sqlite3.Connection, character_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM characters WHERE LOWER(name) = LOWER(?)",
        (character_name,),
    ).fetchone()
    return row["id"] if row else None


def fetch_move_by_character(conn: sqlite3.Connection, character_name: str, move_name: str):
    query = """
         SELECT m.id, m.name, m.normalized_name, fd.startup, fd.active, fd.recovery,
             fd.on_hit, fd.on_block, fd.damage, fd.guard, fd.adv_on_block,
             fd.adv_on_hit, fd.invulnerability, fd.image_url, fd.notes
        FROM moves m
        JOIN characters c ON c.id = m.character_id
        LEFT JOIN frame_data fd ON fd.move_id = m.id
        WHERE LOWER(c.name) = LOWER(?) AND LOWER(m.name) = LOWER(?)
    """
    return conn.execute(query, (character_name, move_name)).fetchone()
