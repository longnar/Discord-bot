import sqlite3


def connect():
    return sqlite3.connect("database.db")



def create_tables():

    db = connect()
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


    # thêm cột cho database cũ nếu chưa có

    try:

        cur.execute(
            """
            ALTER TABLE players
            ADD COLUMN last_name_change TEXT
            """
        )

        db.commit()

    except sqlite3.OperationalError:
        pass


    try:

        cur.execute(
            """
            ALTER TABLE players
            ADD COLUMN best_streak INTEGER DEFAULT 0
            """
        )

        db.commit()

    except sqlite3.OperationalError:
        pass


    db.close()