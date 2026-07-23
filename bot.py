import discord
from discord.ext import commands
import pandas as pd

from database import connect, create_tables
from elo import calculate

from datetime import datetime, timedelta


intents = discord.Intents.default()
intents.message_content = True
intents.members = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    create_tables()
    print("Bot đã chạy!")

#ELO

@bot.command()
async def elo(ctx, *, player_name=None):

    db = connect()
    cur = db.cursor()

    if player_name:

        cur.execute(
            """
            SELECT
                name,
                elo,
                wins,
                losses
            FROM players
            WHERE name=?
            """,
            (player_name,)
        )

        player = cur.fetchone()

        if not player:

            await ctx.send(
                "Không tìm thấy người chơi"
            )

            db.close()
            return


        name, elo, wins, losses = player


        if wins + losses == 0:

            await ctx.send(
                f"{name} chưa đánh mà đòi có Elo à :v"
            )

            db.close()
            return


        embed = discord.Embed(
            title="🏆 ISDVN Player Elo",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Tên",
            value=name,
            inline=False
        )

        embed.add_field(
            name="💎 Elo",
            value=round(elo),
            inline=True
        )

        embed.add_field(
            name="⚔ W-L",
            value=f"{wins}W • {losses}L",
            inline=True
        )


        await ctx.send(embed=embed)

        db.close()
        return


    cur.execute(
        """
        SELECT
            name,
            elo,
            wins,
            losses
        FROM players
        WHERE wins + losses > 0
        ORDER BY elo DESC
        """
    )

    players = cur.fetchall()

    if not players:

        await ctx.send(
            "Chưa có dữ liệu"
        )

        db.close()
        return


    embed = discord.Embed(
        title="🏆 ISDVN Leaderboard",
        color=discord.Color.gold()
    )

    text = ""

    for i, player in enumerate(players, 1):

        icon = "▫️"

        if i == 1:
            icon = "🥇"
        elif i == 2:
            icon = "🥈"
        elif i == 3:
            icon = "🥉"

        text += (
            f"{icon} **#{i}** "
            f"{player[0]} • "
            f"**{round(player[1])}** "
            f"({player[2]}W-{player[3]}L)\n"
        )

    embed.description = text


    await ctx.send(embed=embed)

    db.close()

#pròile

@bot.command()
async def profile(ctx, *, player_name=None):

    if player_name is None:
        player_name = ctx.author.name


    db = connect()
    cur = db.cursor()


    cur.execute(
        """
        SELECT
            elo,
            wins,
            losses,
            highest_elo,
            win_streak,
            best_streak
        FROM players
        WHERE name=?
        """,
        (player_name,)
    )


    player = cur.fetchone()


    if not player:

        await ctx.send(
            "Không tìm thấy người chơi"
        )

        db.close()
        return


    elo = player[0]
    wins = player[1]
    losses = player[2]
    highest = player[3]
    streak = player[4]
    best = player[5]


    total = wins + losses


    if total == 0:

        record = "N/A"
        winrate = "N/A"
        streak = "N/A"
        best = "N/A"

    else:

        record = f"{wins}W • {losses}L"

        winrate = (
            f"{round(wins / total * 100, 1)}%"
        )


    embed = discord.Embed(
         title=f"🏆 ISDVN {player_name}'s Profile",
        color=discord.Color.blue()
    )


    embed.add_field(
        name="💎 Elo",
        value=round(elo),
        inline=True
    )


    embed.add_field(
        name="⚔ W-L",
        value=record,
        inline=True
    )


    embed.add_field(
        name="📈 Tỉ Lệ Thắng",
        value=winrate,
        inline=True
    )


    embed.add_field(
        name="🏅 Peak Elo",
        value=round(highest),
        inline=True
    )


    embed.add_field(
        name="🔥 Chuỗi Thắng",
        value=streak,
        inline=True
    )


    embed.add_field(
        name="⭐ Chuỗi Thắng Cao Nhất",
        value=best,
        inline=True
    )



    await ctx.send(
        embed=embed
    )


    db.close()

#gửi file giải

@bot.command()
async def importelo(ctx):

    if not ctx.message.attachments:

        await ctx.send(
            "Chưa gửi file CSV"
        )

        return


    file = ctx.message.attachments[0]

    await file.save(
        "result.csv"
    )


    df = pd.read_csv(
        "result.csv"
    )


    db = connect()
    cur = db.cursor()


    for _, row in df.iterrows():

        winner = row["winner"]
        loser = row["loser"]
        score = row["score"]


        for player in [winner, loser]:

            cur.execute(
                """
                INSERT OR IGNORE INTO players(name)
                VALUES(?)
                """,
                (player,)
            )


        cur.execute(
            """
            SELECT elo
            FROM players
            WHERE name=?
            """,
            (winner,)
        )

        winner_elo = cur.fetchone()[0]


        cur.execute(
            """
            SELECT elo
            FROM players
            WHERE name=?
            """,
            (loser,)
        )

        loser_elo = cur.fetchone()[0]


        change = calculate(
            winner_elo,
            loser_elo,
            score
        )


        new_winner_elo = winner_elo + change
        new_loser_elo = loser_elo - change


        cur.execute(
            """
            UPDATE players

            SET
                elo=?,
                wins=wins+1,
                win_streak=win_streak+1,
                best_streak=MAX(best_streak, win_streak+1),
                highest_elo=MAX(highest_elo,?)

            WHERE name=?
            """,
            (
                new_winner_elo,
                new_winner_elo,
                winner
            )
        )

        cur.execute(
            """
            UPDATE players

            SET
                elo=?,
                losses=losses+1,
                win_streak=0

            WHERE name=?
            """,
            (
                new_loser_elo,
                loser
            )
        )

        cur.execute(
            """
            INSERT INTO matches
            (winner, loser, change_elo)

            VALUES(?,?,?)
            """,
            (
                winner,
                loser,
                change
            )
        )


    db.commit()
    db.close()


    await ctx.send(
        "✅ Đã import file và cập nhật Elo."
    )



#resetelo

@bot.command()
@commands.has_permissions(administrator=True)
async def resetelo(ctx):

    db = connect()
    cur = db.cursor()


    cur.execute(
        """
        UPDATE players

        SET
            elo=1500,
            wins=0,
            losses=0,
            highest_elo=1500,
            win_streak=0,
            best_streak=0
        """
    )


    cur.execute(
        """
        DELETE FROM matches
        """
    )


    db.commit()
    db.close()


    await ctx.send(
        "🔄 Đã reset toàn bộ Elo."
    )

#changename

@bot.command()
async def setname(ctx, old_name, new_name):

    db = connect()
    cur = db.cursor()


    cur.execute(
        """
        SELECT last_name_change
        FROM players
        WHERE name=?
        """,
        (old_name,)
    )

    player = cur.fetchone()


    if not player:

        await ctx.send(
            "❌ Không tìm thấy người chơi."
        )

        db.close()
        return


    cur.execute(
        """
        SELECT name
        FROM players
        WHERE name=?
        """,
        (new_name,)
    )

    if cur.fetchone():

        await ctx.send(
            "❌ Tên này đã tồn tại."
        )

        db.close()
        return


    last_change = player[0]


    if last_change:

        last_date = datetime.strptime(
            last_change,
            "%Y-%m-%d"
        )

        next_change = last_date + timedelta(days=30)

        if datetime.now() < next_change:

            remain = (
                next_change - datetime.now()
            ).days

            await ctx.send(
                f"⏳ Bạn phải chờ **{remain} ngày** nữa mới đổi tên được."
            )

            db.close()
            return


    cur.execute(
        """
        UPDATE players

        SET
            name=?,
            last_name_change=?

        WHERE name=?
        """,
        (
            new_name,
            datetime.now().strftime("%Y-%m-%d"),
            old_name
        )
    )

    cur.execute(
        """
        UPDATE matches
        SET winner=?
        WHERE winner=?
        """,
        (
            new_name,
            old_name
        )
    )


    cur.execute(
        """
        UPDATE matches
        SET loser=?
        WHERE loser=?
        """,
        (
            new_name,
            old_name
        )
    )


    db.commit()
    db.close()


    embed = discord.Embed(
        title="✏️ Đổi tên thành công",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Tên cũ",
        value=old_name,
        inline=True
    )

    embed.add_field(
        name="Tên mới",
        value=new_name,
        inline=True
    )


    await ctx.send(embed=embed)



#skipspam

@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    raise error



#token

bot.run("REDACTED_DISCORD_TOKEN")