import os
from pathlib import Path

from utils.turso_compat import is_turso_configured, open_connection

BASE_DIR = Path(__file__).resolve().parent
ELO_DB_PATH = Path(os.getenv("ELO_DB_PATH", str(BASE_DIR / "database.db")))


def connect():
    return open_connection(
        local_path=ELO_DB_PATH,
        url_env="TURSO_ELO_URL",
        token_env="TURSO_ELO_AUTH_TOKEN",
    )


def create_tables():
    db = connect()
    try:
        cur = db.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS players(
            name TEXT PRIMARY KEY,
            elo INTEGER DEFAULT 1500,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            highest_elo REAL DEFAULT 1500,
            win_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            last_name_change TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS matches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner TEXT,
            loser TEXT,
            change_elo INTEGER
        )
        """)

        # Kiểm tra cột hiện có để migrate an toàn trên cả SQLite và Turso
        cur.execute("PRAGMA table_info(players)")
        existing_columns = {row[1] for row in cur.fetchall()}

        if "last_name_change" not in existing_columns:
            cur.execute("ALTER TABLE players ADD COLUMN last_name_change TEXT")

        if "best_streak" not in existing_columns:
            cur.execute("ALTER TABLE players ADD COLUMN best_streak INTEGER DEFAULT 0")

        db.commit()
        mode = "Turso Remote" if is_turso_configured("TURSO_ELO_URL") else f"Local SQLite ({ELO_DB_PATH})"
        print(f"[OK] Elo database initialized via {mode}")
    finally:
        db.close()