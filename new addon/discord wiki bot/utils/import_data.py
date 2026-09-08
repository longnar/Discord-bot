import json
import sqlite3
from pathlib import Path

from app.config import DB_PATH, RAW_DATA_DIR
from utils.db import get_connection


def load_json_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_data_files_exist():
    if not RAW_DATA_DIR.exists():
        raise FileNotFoundError(f"Raw data directory not found: {RAW_DATA_DIR}")

    files = list(RAW_DATA_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON files found in {RAW_DATA_DIR}")

    return files


def import_characters(conn: sqlite3.Connection, characters: list[dict]):
    for character in characters:
        conn.execute(
            """
            INSERT OR REPLACE INTO characters (name, display_name, aliases)
            VALUES (?, ?, ?)
            """,
            (
                character.get("name"),
                character.get("display_name", character.get("name")),
                ",".join(character.get("aliases", [])),
            ),
        )


def import_glossary(conn: sqlite3.Connection, glossary_items: list[dict]):
    for item in glossary_items:
        conn.execute(
            """
            INSERT OR REPLACE INTO glossary (term, normalized_term, category, definition, aliases)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.get("term"),
                item.get("term", "").lower(),
                item.get("category", "general"),
                item.get("definition", ""),
                ",".join(item.get("aliases", [])),
            ),
        )


def import_moves_and_frame_data(conn: sqlite3.Connection, moves_data: list[dict]):
    for entry in moves_data:
        character_name = entry.get("character")
        if not character_name:
            continue

        character_row = conn.execute(
            "SELECT id FROM characters WHERE LOWER(name) = LOWER(?)",
            (character_name,),
        ).fetchone()

        if not character_row:
            conn.execute(
                "INSERT INTO characters (name, display_name) VALUES (?, ?)",
                (character_name, character_name),
            )
            character_row = conn.execute("SELECT id FROM characters WHERE name = ?", (character_name,)).fetchone()

        character_id = character_row["id"]

        for move in entry.get("moves", []):
            move_name = move.get("name")
            if not move_name:
                continue

            conn.execute(
                """
                INSERT OR REPLACE INTO moves (character_id, name, normalized_name, aliases, move_type, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    character_id,
                    move_name,
                    move_name.lower(),
                    ",".join(move.get("aliases", [])),
                    move.get("type", "normal"),
                    move.get("notes", ""),
                ),
            )

            move_row = conn.execute(
                "SELECT id FROM moves WHERE character_id = ? AND name = ?",
                (character_id, move_name),
            ).fetchone()

            if not move_row:
                continue

            conn.execute(
                """
                INSERT OR REPLACE INTO frame_data (
                    move_id, startup, active, recovery, on_hit, on_block, damage,
                    guard, adv_on_block, adv_on_hit, invulnerability, image_url, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    move_row["id"],
                    move.get("startup"),
                    move.get("active"),
                    move.get("recovery"),
                    move.get("on_hit"),
                    move.get("on_block"),
                    move.get("damage"),
                    move.get("guard", ""),
                    move.get("adv_on_block", ""),
                    move.get("adv_on_hit", ""),
                    move.get("invulnerability", ""),
                    move.get("image_url", ""),
                    move.get("frame_notes", "") or move.get("notes", ""),
                ),
            )


def main():
    files = ensure_data_files_exist()
    conn = get_connection()

    try:
        for file in files:
            data = load_json_file(file)
            if "characters" in data:
                import_characters(conn, data["characters"])
            if "moves" in data:
                import_moves_and_frame_data(conn, data["moves"])
            if "glossary" in data:
                import_glossary(conn, data["glossary"])

        conn.commit()
        print(f"Imported data from {len(files)} JSON file(s) into {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
