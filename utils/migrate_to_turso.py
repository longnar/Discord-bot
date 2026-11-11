"""
Script hỗ trợ đẩy dữ liệu từ database.db và wiki.db cục bộ lên Turso Cloud
(dành cho Windows không cần cài Turso CLI / WSL).

Cách dùng:
    1. Tạo 2 database rỗng trên Turso Dashboard (region Singapore)
    2. Điền TURSO_ELO_URL, TURSO_ELO_AUTH_TOKEN, TURSO_WIKI_URL, TURSO_WIKI_AUTH_TOKEN vào .env
    3. Chạy: python utils/migrate_to_turso.py
"""

import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

from database import ELO_DB_PATH, connect as connect_elo, create_tables
from utils.db import DB_PATH as WIKI_DB_PATH, get_connection as connect_wiki, init_db
from utils.turso_compat import is_turso_configured


def migrate_elo() -> None:
    if not is_turso_configured("TURSO_ELO_URL"):
        print("[SKIP] Chua cau hinh TURSO_ELO_URL -> bo qua migrate Elo DB.")
        return
    if not ELO_DB_PATH.exists():
        print(f"[SKIP] Khong tim thay file {ELO_DB_PATH}")
        return

    create_tables()

    local_conn = sqlite3.connect(str(ELO_DB_PATH))
    remote_conn = connect_elo()
    try:
        players = local_conn.execute(
            """
            SELECT name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change
            FROM players
            """
        ).fetchall()
        for row in players:
            remote_conn.execute(
                """
                INSERT OR REPLACE INTO players (
                    name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

        matches = local_conn.execute(
            "SELECT id, winner, loser, change_elo FROM matches"
        ).fetchall()
        for row in matches:
            remote_conn.execute(
                """
                INSERT OR REPLACE INTO matches (id, winner, loser, change_elo)
                VALUES (?, ?, ?, ?)
                """,
                row,
            )

        remote_conn.commit()

        p_count = remote_conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        m_count = remote_conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        print(f"[OK] Da migrate Elo DB len Turso: {p_count} players, {m_count} matches.")
    finally:
        local_conn.close()
        remote_conn.close()


def migrate_wiki() -> None:
    if not is_turso_configured("TURSO_WIKI_URL"):
        print("[SKIP] Chua cau hinh TURSO_WIKI_URL -> bo qua migrate Wiki DB.")
        return
    if not WIKI_DB_PATH.exists():
        print(f"[SKIP] Khong tim thay file {WIKI_DB_PATH}")
        return

    init_db()

    local_conn = sqlite3.connect(str(WIKI_DB_PATH))
    remote_conn = connect_wiki()
    try:
        characters = local_conn.execute(
            "SELECT id, name, display_name, aliases, created_at FROM characters"
        ).fetchall()
        valid_char_ids = {row[0] for row in characters}
        for row in characters:
            remote_conn.execute(
                """
                INSERT OR REPLACE INTO characters (id, name, display_name, aliases, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                row,
            )

        moves = local_conn.execute(
            "SELECT id, character_id, name, normalized_name, aliases, move_type, notes FROM moves"
        ).fetchall()
        valid_move_ids = set()
        for row in moves:
            if row[1] not in valid_char_ids:
                print(f"[WARN] Bo qua move mo coi id={row[0]} ({row[2]}): character_id={row[1]} khong ton tai.")
                continue
            valid_move_ids.add(row[0])
            remote_conn.execute(
                """
                INSERT OR REPLACE INTO moves (id, character_id, name, normalized_name, aliases, move_type, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

        frame_data = local_conn.execute(
            """
            SELECT move_id, startup, active, recovery, damage, guard,
                   adv_on_block, adv_on_hit, invulnerability, image_url, image_data, notes
            FROM frame_data
            """
        ).fetchall()
        for row in frame_data:
            if row[0] not in valid_move_ids:
                print(f"[WARN] Bo qua frame_data mo coi move_id={row[0]}.")
                continue
            remote_conn.execute(
                """
                INSERT OR REPLACE INTO frame_data (
                    move_id, startup, active, recovery, damage, guard,
                    adv_on_block, adv_on_hit, invulnerability, image_url, image_data, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

        glossary = local_conn.execute(
            "SELECT id, term, normalized_term, category, definition, aliases, created_at FROM glossary"
        ).fetchall()
        for row in glossary:
            remote_conn.execute(
                """
                INSERT OR REPLACE INTO glossary (
                    id, term, normalized_term, category, definition, aliases, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

        remote_conn.commit()

        c_count = remote_conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        mv_count = remote_conn.execute("SELECT COUNT(*) FROM moves").fetchone()[0]
        fd_count = remote_conn.execute("SELECT COUNT(*) FROM frame_data").fetchone()[0]
        g_count = remote_conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
        print(
            f"[OK] Da migrate Wiki DB len Turso: {c_count} characters, {mv_count} moves, "
            f"{fd_count} frame_data, {g_count} glossary."
        )
    finally:
        local_conn.close()
        remote_conn.close()


def main() -> None:
    migrate_elo()
    migrate_wiki()


if __name__ == "__main__":
    main()
