from datetime import datetime, timedelta
from typing import Any, Optional

from database import connect
from elo import calculate


class EloRepoError(ValueError):
    """Lỗi nghiệp vụ / dữ liệu đầu vào cho hệ thống Elo."""


def _row_to_player_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "name": row[0],
        "elo": float(row[1]) if row[1] is not None else 1500.0,
        "wins": int(row[2] or 0),
        "losses": int(row[3] or 0),
        "highest_elo": float(row[4]) if row[4] is not None else 1500.0,
        "win_streak": int(row[5] or 0),
        "best_streak": int(row[6] or 0),
        "last_name_change": row[7],
    }


def _find_player_row(cur, name: str):
    clean = name.strip()
    if not clean:
        return None
    cur.execute(
        """
        SELECT name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change
        FROM players
        WHERE name = ?
        """,
        (clean,),
    )
    row = cur.fetchone()
    if row:
        return row

    cur.execute(
        """
        SELECT name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change
        FROM players
        WHERE LOWER(name) = LOWER(?)
        """,
        (clean,),
    )
    return cur.fetchone()


def autocomplete_player_names(current: str, limit: int = 25) -> list[str]:
    conn = connect()
    try:
        cur = conn.cursor()
        q = (current or "").strip()
        if q:
            cur.execute(
                """
                SELECT name FROM players
                WHERE LOWER(name) LIKE LOWER(?)
                ORDER BY elo DESC, name ASC
                LIMIT ?
                """,
                (f"%{q}%", limit),
            )
        else:
            cur.execute(
                """
                SELECT name FROM players
                ORDER BY elo DESC, name ASC
                LIMIT ?
                """,
                (limit,),
            )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def create_player(
    name: str,
    elo: int = 1500,
    wins: int = 0,
    losses: int = 0,
    highest_elo: Optional[int] = None,
    win_streak: int = 0,
    best_streak: Optional[int] = None,
) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise EloRepoError("Tên người chơi không được để trống.")
    if len(clean_name) > 50:
        raise EloRepoError("Tên người chơi tối đa 50 ký tự.")
    if elo < 0 or wins < 0 or losses < 0 or win_streak < 0:
        raise EloRepoError("Các chỉ số (Elo, Wins, Losses, Win Streak) không được âm.")
    if highest_elo is not None and highest_elo < 0:
        raise EloRepoError("Peak Elo không được âm.")
    if best_streak is not None and best_streak < 0:
        raise EloRepoError("Best Streak không được âm.")

    peak = float(highest_elo) if highest_elo is not None else float(elo)
    peak = max(peak, float(elo))
    best = best_streak if best_streak is not None else win_streak
    best = max(best, win_streak)

    conn = connect()
    try:
        cur = conn.cursor()
        existing = _find_player_row(cur, clean_name)
        if existing:
            raise EloRepoError(f"Người chơi **{existing[0]}** đã tồn tại trong danh sách Elo.")

        cur.execute(
            """
            INSERT INTO players (name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (clean_name, int(elo), int(wins), int(losses), peak, int(win_streak), int(best)),
        )
        conn.commit()
        created = _find_player_row(cur, clean_name)
        return _row_to_player_dict(created)
    finally:
        conn.close()


def get_player(name: str) -> Optional[dict[str, Any]]:
    conn = connect()
    try:
        cur = conn.cursor()
        row = _find_player_row(cur, name)
        if not row:
            return None
        player = _row_to_player_dict(row)
        cur.execute(
            "SELECT COUNT(*) FROM matches WHERE winner = ? OR loser = ?",
            (player["name"], player["name"]),
        )
        player["match_count"] = int(cur.fetchone()[0] or 0)
        return player
    finally:
        conn.close()


def get_player_recent_matches(name: str, limit: int = 5) -> list[dict[str, Any]]:
    conn = connect()
    try:
        cur = conn.cursor()
        row = _find_player_row(cur, name)
        if not row:
            return []
        canonical = row[0]
        cur.execute(
            """
            SELECT id, winner, loser, change_elo
            FROM matches
            WHERE winner = ? OR loser = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (canonical, canonical, limit),
        )
        return [
            {"id": m[0], "winner": m[1], "loser": m[2], "change_elo": int(m[3] or 0)}
            for m in cur.fetchall()
        ]
    finally:
        conn.close()


def list_players(
    search: str = "",
    sort_by: str = "elo",
    include_unranked: bool = True,
) -> list[dict[str, Any]]:
    order_map = {
        "elo": "elo DESC, wins DESC, name ASC",
        "name": "LOWER(name) ASC",
        "matches": "(wins + losses) DESC, elo DESC, name ASC",
        "wins": "wins DESC, elo DESC, name ASC",
        "highest_elo": "highest_elo DESC, elo DESC, name ASC",
    }
    order_clause = order_map.get(sort_by, order_map["elo"])

    conditions: list[str] = []
    params: list[Any] = []

    if not include_unranked:
        conditions.append("(wins + losses) > 0")

    q = (search or "").strip()
    if q:
        conditions.append("LOWER(name) LIKE LOWER(?)")
        params.append(f"%{q}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT name, elo, wins, losses, highest_elo, win_streak, best_streak, last_name_change
            FROM players
            {where_clause}
            ORDER BY {order_clause}
            """,
            params,
        )
        return [_row_to_player_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_player(
    player_name: str,
    new_name: Optional[str] = None,
    elo: Optional[int] = None,
    wins: Optional[int] = None,
    losses: Optional[int] = None,
    highest_elo: Optional[int] = None,
    win_streak: Optional[int] = None,
    best_streak: Optional[int] = None,
    reset_name_cooldown: bool = False,
) -> dict[str, Any]:
    conn = connect()
    try:
        cur = conn.cursor()
        row = _find_player_row(cur, player_name)
        if not row:
            raise EloRepoError(f"Không tìm thấy người chơi **{player_name}**.")

        before = _row_to_player_dict(row)
        canonical_name = before["name"]

        target_name = canonical_name
        renamed_matches = 0
        if new_name is not None:
            clean_new = new_name.strip()
            if not clean_new:
                raise EloRepoError("Tên mới không được để trống.")
            if len(clean_new) > 50:
                raise EloRepoError("Tên mới tối đa 50 ký tự.")
            if clean_new != canonical_name:
                conflict = _find_player_row(cur, clean_new)
                if conflict and conflict[0].lower() != canonical_name.lower():
                    raise EloRepoError(f"Tên **{conflict[0]}** đã tồn tại.")
                target_name = clean_new

        if elo is not None and elo < 0:
            raise EloRepoError("Điểm Elo không được âm.")
        if wins is not None and wins < 0:
            raise EloRepoError("Số trận thắng (Wins) không được âm.")
        if losses is not None and losses < 0:
            raise EloRepoError("Số trận thua (Losses) không được âm.")
        if highest_elo is not None and highest_elo < 0:
            raise EloRepoError("Peak Elo không được âm.")
        if win_streak is not None and win_streak < 0:
            raise EloRepoError("Chuỗi thắng hiện tại không được âm.")
        if best_streak is not None and best_streak < 0:
            raise EloRepoError("Chuỗi thắng cao nhất không được âm.")

        final_elo = int(elo) if elo is not None else round(before["elo"])
        final_wins = int(wins) if wins is not None else before["wins"]
        final_losses = int(losses) if losses is not None else before["losses"]

        if highest_elo is not None:
            final_highest = float(highest_elo)
        else:
            final_highest = max(before["highest_elo"], float(final_elo))

        final_streak = int(win_streak) if win_streak is not None else before["win_streak"]
        if best_streak is not None:
            final_best_streak = int(best_streak)
        else:
            final_best_streak = max(before["best_streak"], final_streak)

        final_last_change = None if reset_name_cooldown else before["last_name_change"]

        cur.execute(
            """
            UPDATE players
            SET name = ?, elo = ?, wins = ?, losses = ?, highest_elo = ?,
                win_streak = ?, best_streak = ?, last_name_change = ?
            WHERE name = ?
            """,
            (
                target_name,
                final_elo,
                final_wins,
                final_losses,
                final_highest,
                final_streak,
                final_best_streak,
                final_last_change,
                canonical_name,
            ),
        )

        if target_name != canonical_name:
            cur.execute(
                "SELECT COUNT(*) FROM matches WHERE winner = ? OR loser = ?",
                (canonical_name, canonical_name),
            )
            renamed_matches = int(cur.fetchone()[0] or 0)
            cur.execute("UPDATE matches SET winner = ? WHERE winner = ?", (target_name, canonical_name))
            cur.execute("UPDATE matches SET loser = ? WHERE loser = ?", (target_name, canonical_name))

        conn.commit()
        updated_row = _find_player_row(cur, target_name)
        return {
            "before": before,
            "after": _row_to_player_dict(updated_row),
            "renamed_matches": renamed_matches,
        }
    finally:
        conn.close()


def rename_player_by_user(old_name: str, new_name: str, cooldown_days: int = 30) -> dict[str, Any]:
    clean_new = new_name.strip()
    if not clean_new:
        raise EloRepoError("Tên mới không được để trống.")
    if len(clean_new) > 50:
        raise EloRepoError("Tên mới tối đa 50 ký tự.")

    conn = connect()
    try:
        cur = conn.cursor()
        row = _find_player_row(cur, old_name)
        if not row:
            raise EloRepoError("Không tìm thấy người chơi.")

        player = _row_to_player_dict(row)
        canonical_old = player["name"]

        conflict = _find_player_row(cur, clean_new)
        if conflict and conflict[0].lower() != canonical_old.lower():
            raise EloRepoError("Tên này đã tồn tại.")

        if player["last_name_change"]:
            last_date = datetime.strptime(player["last_name_change"], "%Y-%m-%d")
            next_change = last_date + timedelta(days=cooldown_days)
            if datetime.now() < next_change:
                remain = max(1, (next_change - datetime.now()).days)
                raise EloRepoError(f"Bạn phải chờ **{remain} ngày** nữa mới đổi tên được.")

        now_str = datetime.now().strftime("%Y-%m-%d")
        cur.execute(
            "UPDATE players SET name = ?, last_name_change = ? WHERE name = ?",
            (clean_new, now_str, canonical_old),
        )
        cur.execute("UPDATE matches SET winner = ? WHERE winner = ?", (clean_new, canonical_old))
        cur.execute("UPDATE matches SET loser = ? WHERE loser = ?", (clean_new, canonical_old))
        conn.commit()
        return {"old_name": canonical_old, "new_name": clean_new}
    finally:
        conn.close()


def reset_player(player_name: str) -> dict[str, Any]:
    return update_player(
        player_name=player_name,
        elo=1500,
        wins=0,
        losses=0,
        highest_elo=1500,
        win_streak=0,
        best_streak=0,
    )


def delete_player(player_name: str, delete_matches: bool = False) -> dict[str, Any]:
    conn = connect()
    try:
        cur = conn.cursor()
        row = _find_player_row(cur, player_name)
        if not row:
            raise EloRepoError(f"Không tìm thấy người chơi **{player_name}**.")

        canonical = row[0]
        deleted_matches = 0
        if delete_matches:
            cur.execute(
                "SELECT COUNT(*) FROM matches WHERE winner = ? OR loser = ?",
                (canonical, canonical),
            )
            deleted_matches = int(cur.fetchone()[0] or 0)
            cur.execute(
                "DELETE FROM matches WHERE winner = ? OR loser = ?",
                (canonical, canonical),
            )

        cur.execute("DELETE FROM players WHERE name = ?", (canonical,))
        conn.commit()
        return {
            "name": canonical,
            "deleted_matches": deleted_matches,
        }
    finally:
        conn.close()


def record_match(winner_name: str, loser_name: str, score: str = "2-1") -> dict[str, Any]:
    w_clean = winner_name.strip()
    l_clean = loser_name.strip()
    if not w_clean or not l_clean:
        raise EloRepoError("Tên người thắng và người thua không được để trống.")
    if w_clean.lower() == l_clean.lower():
        raise EloRepoError("Người thắng và người thua không thể là cùng một người.")

    conn = connect()
    try:
        cur = conn.cursor()

        w_row = _find_player_row(cur, w_clean)
        if not w_row:
            cur.execute("INSERT INTO players (name) VALUES (?)", (w_clean,))
            w_row = _find_player_row(cur, w_clean)

        l_row = _find_player_row(cur, l_clean)
        if not l_row:
            cur.execute("INSERT INTO players (name) VALUES (?)", (l_clean,))
            l_row = _find_player_row(cur, l_clean)

        winner = _row_to_player_dict(w_row)
        loser = _row_to_player_dict(l_row)

        change = calculate(winner["elo"], loser["elo"], score)
        new_winner_elo = round(winner["elo"] + change)
        new_loser_elo = max(0, round(loser["elo"] - change))

        new_w_streak = winner["win_streak"] + 1
        new_w_best = max(winner["best_streak"], new_w_streak)
        new_w_high = max(winner["highest_elo"], float(new_winner_elo))

        cur.execute(
            """
            UPDATE players
            SET elo = ?, wins = wins + 1, win_streak = ?, best_streak = ?, highest_elo = ?
            WHERE name = ?
            """,
            (new_winner_elo, new_w_streak, new_w_best, new_w_high, winner["name"]),
        )
        cur.execute(
            """
            UPDATE players
            SET elo = ?, losses = losses + 1, win_streak = 0
            WHERE name = ?
            """,
            (new_loser_elo, loser["name"]),
        )
        cur.execute(
            "INSERT INTO matches (winner, loser, change_elo) VALUES (?, ?, ?)",
            (winner["name"], loser["name"], change),
        )
        match_id = cur.lastrowid
        conn.commit()
        return {
            "match_id": match_id,
            "winner": winner["name"],
            "loser": loser["name"],
            "score": score,
            "change_elo": change,
            "winner_elo_before": round(winner["elo"]),
            "winner_elo_after": new_winner_elo,
            "loser_elo_before": round(loser["elo"]),
            "loser_elo_after": new_loser_elo,
        }
    finally:
        conn.close()


def list_matches(player_name: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = connect()
    try:
        cur = conn.cursor()
        if player_name and player_name.strip():
            row = _find_player_row(cur, player_name)
            target = row[0] if row else player_name.strip()
            cur.execute(
                """
                SELECT id, winner, loser, change_elo
                FROM matches
                WHERE LOWER(winner) = LOWER(?) OR LOWER(loser) = LOWER(?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (target, target, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, winner, loser, change_elo
                FROM matches
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [
            {"id": m[0], "winner": m[1], "loser": m[2], "change_elo": int(m[3] or 0)}
            for m in cur.fetchall()
        ]
    finally:
        conn.close()


def undo_match(match_id: Optional[int] = None) -> dict[str, Any]:
    conn = connect()
    try:
        cur = conn.cursor()
        if match_id is None:
            cur.execute("SELECT id, winner, loser, change_elo FROM matches ORDER BY id DESC LIMIT 1")
        else:
            cur.execute("SELECT id, winner, loser, change_elo FROM matches WHERE id = ?", (match_id,))

        match_row = cur.fetchone()
        if not match_row:
            if match_id is None:
                raise EloRepoError("Không có trận đấu nào trong lịch sử để hoàn tác.")
            raise EloRepoError(f"Không tìm thấy trận đấu có ID `{match_id}`.")

        mid, winner_name, loser_name, change_elo = (
            match_row[0],
            match_row[1],
            match_row[2],
            int(match_row[3] or 0),
        )

        w_row = _find_player_row(cur, winner_name)
        if w_row:
            w = _row_to_player_dict(w_row)
            cur.execute(
                """
                UPDATE players
                SET elo = ?, wins = ?, win_streak = ?
                WHERE name = ?
                """,
                (
                    max(0, round(w["elo"] - change_elo)),
                    max(0, w["wins"] - 1),
                    max(0, w["win_streak"] - 1),
                    w["name"],
                ),
            )

        l_row = _find_player_row(cur, loser_name)
        if l_row:
            l = _row_to_player_dict(l_row)
            cur.execute(
                """
                UPDATE players
                SET elo = ?, losses = ?
                WHERE name = ?
                """,
                (
                    round(l["elo"] + change_elo),
                    max(0, l["losses"] - 1),
                    l["name"],
                ),
            )

        cur.execute("DELETE FROM matches WHERE id = ?", (mid,))
        conn.commit()
        return {
            "match_id": mid,
            "winner": winner_name,
            "loser": loser_name,
            "change_elo": change_elo,
        }
    finally:
        conn.close()
