import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "wiki.db"
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"
RAW_DATA_DIR = BASE_DIR / "data" / "raw"


def get_connection() -> sqlite3.Connection:
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

    print(f"[OK] Wiki database initialized at {DB_PATH}")


def fetch_character_id(conn: sqlite3.Connection, character_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM characters WHERE LOWER(name) = LOWER(?)",
        (character_name,),
    ).fetchone()
    return row["id"] if row else None


def fetch_move_by_character(conn: sqlite3.Connection, character_name: str, move_name: str):
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


