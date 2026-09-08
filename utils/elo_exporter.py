import csv
import io
import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, Tuple
from elo import calculate


def export_elo_json(conn: sqlite3.Connection) -> str:
    """
    Xuất toàn bộ dữ liệu Elo (players và matches) ra chuỗi JSON.
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change FROM players")
    players = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT id, winner, loser, change_elo FROM matches")
    matches = [dict(row) for row in cur.fetchall()]

    data = {
        "version": 1,
        "exported_at": datetime.now().isoformat(),
        "players": players,
        "matches": matches,
    }

    return json.dumps(data, ensure_ascii=False, indent=2)


def export_elo_csv(conn: sqlite3.Connection) -> Tuple[str, str]:
    """
    Xuất dữ liệu Elo ra 2 chuỗi CSV (players_csv, matches_csv).
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Players CSV
    cur.execute("SELECT name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change FROM players")
    players = [dict(row) for row in cur.fetchall()]

    players_output = io.StringIO()
    if players:
        fieldnames = ["name", "elo", "wins", "losses", "highest_elo", "win_streak", "best_streak", "last_name_change"]
        writer = csv.DictWriter(players_output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(players)
    else:
        players_output.write("name,elo,wins,losses,highest_elo,win_streak,best_streak,last_name_change\n")

    # Matches CSV
    cur.execute("SELECT id, winner, loser, change_elo FROM matches")
    matches = [dict(row) for row in cur.fetchall()]

    matches_output = io.StringIO()
    if matches:
        fieldnames = ["id", "winner", "loser", "change_elo"]
        writer = csv.DictWriter(matches_output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    else:
        matches_output.write("id,winner,loser,change_elo\n")

    return players_output.getvalue(), matches_output.getvalue()


def import_elo_from_json(conn: sqlite3.Connection, json_data: str, mode: str = "upsert") -> Dict[str, int]:
    """
    Import hoặc khôi phục dữ liệu Elo từ chuỗi JSON snapshot.
    mode: 'upsert' (cập nhật/thêm mới) hoặc 'overwrite' (xóa sạch và nạp lại)
    """
    data = json.loads(json_data)
    players = data.get("players", [])
    matches = data.get("matches", [])

    cur = conn.cursor()

    if mode == "overwrite":
        cur.execute("DELETE FROM matches")
        cur.execute("DELETE FROM players")

    imported_players = 0
    for p in players:
        cur.execute(
            """
            INSERT INTO players (name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                elo = excluded.elo,
                wins = excluded.wins,
                losses = excluded.losses,
                highest_elo = excluded.highest_elo,
                win_streak = excluded.win_streak,
                best_streak = excluded.best_streak,
                last_name_change = excluded.last_name_change
            """,
            (
                p.get("name"),
                p.get("elo", 1500),
                p.get("wins", 0),
                p.get("losses", 0),
                p.get("highest_elo", 1500),
                p.get("win_streak", 0),
                p.get("best_streak", 0),
                p.get("last_name_change"),
            ),
        )
        imported_players += 1

    imported_matches = 0
    for m in matches:
        # Nếu match có id, check tồn tại
        match_id = m.get("id")
        if match_id and mode != "overwrite":
            cur.execute("SELECT id FROM matches WHERE id = ?", (match_id,))
            if cur.fetchone():
                continue

        cur.execute(
            """
            INSERT INTO matches (winner, loser, change_elo)
            VALUES (?, ?, ?)
            """,
            (m.get("winner"), m.get("loser"), m.get("change_elo", 0)),
        )
        imported_matches += 1

    conn.commit()
    return {"players": imported_players, "matches": imported_matches}


def import_elo_from_csv(conn: sqlite3.Connection, csv_text: str, mode: str = "upsert") -> Dict[str, str]:
    """
    Import dữ liệu từ CSV. Tự động nhận diện loại file CSV:
    1. Trận đấu kèm score (winner, loser, score) -> Tính toán lại Elo như importelo cũ.
    2. Player snapshot (name, elo, wins, losses, ...) -> Upsert vào bảng players.
    3. Matches snapshot (id, winner, loser, change_elo) -> Upsert vào bảng matches.
    """
    cur = conn.cursor()
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    if not reader:
        return {"status": "error", "message": "File CSV rỗng hoặc không đúng định dạng."}

    headers = [h.strip().lower() for h in reader[0].keys() if h]

    # Loại 1: CSV trận đấu tính Elo (winner, loser, score)
    if "winner" in headers and "loser" in headers and "score" in headers:
        count = 0
        for row in reader:
            winner = row["winner"].strip()
            loser = row["loser"].strip()
            score = row["score"].strip()

            for player in [winner, loser]:
                cur.execute("INSERT OR IGNORE INTO players(name) VALUES(?)", (player,))

            cur.execute("SELECT elo FROM players WHERE name=?", (winner,))
            winner_elo = cur.fetchone()[0]

            cur.execute("SELECT elo FROM players WHERE name=?", (loser,))
            loser_elo = cur.fetchone()[0]

            change = calculate(winner_elo, loser_elo, score)

            new_winner_elo = winner_elo + change
            new_loser_elo = loser_elo - change

            cur.execute(
                """
                UPDATE players
                SET elo=?, wins=wins+1, win_streak=win_streak+1,
                    best_streak=MAX(best_streak, win_streak+1), highest_elo=MAX(highest_elo,?)
                WHERE name=?
                """,
                (new_winner_elo, new_winner_elo, winner),
            )

            cur.execute(
                """
                UPDATE players
                SET elo=?, losses=losses+1, win_streak=0
                WHERE name=?
                """,
                (new_loser_elo, loser),
            )

            cur.execute(
                "INSERT INTO matches (winner, loser, change_elo) VALUES(?,?,?)",
                (winner, loser, change),
            )
            count += 1

        conn.commit()
        return {"status": "success", "message": f"Đã nạp {count} trận đấu và cập nhật Elo."}

    # Loại 2: CSV Snapshot người chơi (name, elo, ...)
    if "name" in headers and "elo" in headers:
        if mode == "overwrite":
            cur.execute("DELETE FROM players")

        count = 0
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue
            cur.execute(
                """
                INSERT INTO players (name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    elo = excluded.elo,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    highest_elo = excluded.highest_elo,
                    win_streak = excluded.win_streak,
                    best_streak = excluded.best_streak,
                    last_name_change = excluded.last_name_change
                """,
                (
                    name,
                    float(row.get("elo", 1500)),
                    int(row.get("wins", 0)),
                    int(row.get("losses", 0)),
                    float(row.get("highest_elo", 1500)),
                    int(row.get("win_streak", 0)),
                    int(row.get("best_streak", 0)),
                    row.get("last_name_change") or None,
                ),
            )
            count += 1

        conn.commit()
        return {"status": "success", "message": f"Đã khôi phục thông tin {count} người chơi."}

    # Loại 3: CSV Snapshot lịch sử đấu (winner, loser, change_elo)
    if "winner" in headers and "loser" in headers and "change_elo" in headers:
        if mode == "overwrite":
            cur.execute("DELETE FROM matches")

        count = 0
        for row in reader:
            cur.execute(
                "INSERT INTO matches (winner, loser, change_elo) VALUES (?, ?, ?)",
                (row["winner"].strip(), row["loser"].strip(), int(row.get("change_elo", 0))),
            )
            count += 1

        conn.commit()
        return {"status": "success", "message": f"Đã khôi phục {count} lịch sử trận đấu."}

    return {"status": "error", "message": "Không nhận diện được định dạng cột trong file CSV."}
