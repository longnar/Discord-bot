import os
import sqlite3
from pathlib import Path

from utils.turso_compat import CompatConnection, is_turso_configured, open_connection

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("WIKI_DB_PATH", str(BASE_DIR / "wiki.db")))
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"
RAW_DATA_DIR = BASE_DIR / "data" / "raw"


def get_connection() -> CompatConnection:
    return open_connection(
        local_path=DB_PATH,
        url_env="TURSO_WIKI_URL",
        token_env="TURSO_WIKI_AUTH_TOKEN",
        row_factory=sqlite3.Row,
    )


def init_db() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    conn = get_connection()
    try:
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
            "image_data": "TEXT DEFAULT ''",
        }
        for column, definition in migrations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE frame_data ADD COLUMN {column} {definition}")

        for old_col in ("on_hit", "on_block"):
            if old_col in columns:
                try:
                    conn.execute(f"ALTER TABLE frame_data DROP COLUMN {old_col}")
                except Exception:
                    pass

        conn.commit()
    finally:
        conn.close()

    mode = "Turso Remote" if is_turso_configured("TURSO_WIKI_URL") else f"Local SQLite ({DB_PATH})"
    print(f"[OK] Wiki database initialized via {mode}")


def fetch_character_id(conn: CompatConnection, character_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM characters WHERE LOWER(name) = LOWER(?)",
        (character_name,),
    ).fetchone()
    return row["id"] if row else None


def fetch_move_by_character(conn: CompatConnection, character_name: str, move_name: str):
    query = """
        SELECT m.id, m.name, m.normalized_name, fd.startup, fd.active, fd.recovery,
               fd.damage, fd.guard, fd.adv_on_block, fd.adv_on_hit,
               fd.invulnerability, fd.image_url, fd.image_data, fd.notes
        FROM moves m
        JOIN characters c ON c.id = m.character_id
        LEFT JOIN frame_data fd ON fd.move_id = m.id
        WHERE LOWER(c.name) = LOWER(?) AND LOWER(m.name) = LOWER(?)
    """
    return conn.execute(query, (character_name, move_name)).fetchone()


