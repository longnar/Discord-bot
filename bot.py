import csv
from datetime import datetime, timedelta
import io
from database import connect, create_tables
import discord
from discord.ext import commands
from elo import calculate

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  create_tables()
  print("Bot đã chạy!")


# --- ELO COMMANDS ---


@bot.command()
async def elo(ctx, *, player_name=None):
  db = connect()
  cur = db.cursor()

  if player_name:
    cur.execute(
        """
            SELECT name, elo, wins, losses
            FROM players
            WHERE name=?
            """,
        (player_name,),
    )
    player = cur.fetchone()

    if not player:
      await ctx.send("Không tìm thấy người chơi")
      db.close()
      return

    name, elo_val, wins, losses = player

    if wins + losses == 0:
      await ctx.send(f"{name} chưa đánh mà đòi có Elo à :v")
      db.close()
      return

    embed = discord.Embed(title="🏆 ISDVN Player Elo", color=discord.Color.blue())
    embed.add_field(name="Tên", value=name, inline=False)
    embed.add_field(name="💎 Elo", value=round(elo_val), inline=True)
    embed.add_field(name="⚔ W-L", value=f"{wins}W • {losses}L", inline=True)

    await ctx.send(embed=embed)
    db.close()
    return

  # Leaderboard
  cur.execute("""
        SELECT name, elo, wins, losses
        FROM players
        WHERE wins + losses > 0
        ORDER BY elo DESC
        """)
  players = cur.fetchall()

  if not players:
    await ctx.send("Chưa có dữ liệu")
    db.close()
    return

  embed = discord.Embed(title="🏆 ISDVN Leaderboard", color=discord.Color.gold())
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
        f"{icon} **#{i}** {player[0]} • **{round(player[1])}**"
        f" ({player[2]}W-{player[3]}L)\n"
    )

  embed.description = text
  await ctx.send(embed=embed)
  db.close()


# --- PROFILE COMMAND ---


@bot.command()
async def profile(ctx, *, player_name=None):
  if player_name is None:
    player_name = ctx.author.name

  db = connect()
  cur = db.cursor()

  cur.execute(
      """
        SELECT elo, wins, losses, highest_elo, win_streak, best_streak
        FROM players
        WHERE name=?
        """,
      (player_name,),
  )
  player = cur.fetchone()

  if not player:
    await ctx.send("Không tìm thấy người chơi")
    db.close()
    return

  elo_val, wins, losses, highest, streak, best = player
  total = wins + losses

  if total == 0:
    record = "N/A"
    winrate = "N/A"
    streak = "N/A"
    best = "N/A"
  else:
    record = f"{wins}W • {losses}L"
    winrate = f"{round(wins / total * 100, 1)}%"

  embed = discord.Embed(
      title=f"🏆 ISDVN {player_name}'s Profile", color=discord.Color.blue()
  )
  embed.add_field(name="💎 Elo", value=round(elo_val), inline=True)
  embed.add_field(name="⚔ W-L", value=record, inline=True)
  embed.add_field(name="📈 Tỉ Lệ Thắng", value=winrate, inline=True)
  embed.add_field(name="🏅 Peak Elo", value=round(highest), inline=True)
  embed.add_field(name="🔥 Chuỗi Thắng", value=streak, inline=True)
  embed.add_field(name="⭐ Chuỗi Thắng Cao Nhất", value=best, inline=True)

  await ctx.send(embed=embed)
  db.close()


# --- IMPORT ELO (ĐÃ THAY THẾ PANDAS BẰNG CSV MẶC ĐỊNH) ---


@bot.command()
async def importelo(ctx):
  if not ctx.message.attachments:
    await ctx.send("Chưa gửi file CSV")
    return

  file = ctx.message.attachments[0]

  # Đọc trực tiếp dữ liệu file từ bộ nhớ tạm (không cần lưu file ra máy rồi đọc lại)
  file_bytes = await file.read()
  csv_text = file_bytes.decode("utf-8")

  db = connect()
  cur = db.cursor()

  # Sử dụng thư viện csv mặc định của Python
  reader = csv.DictReader(io.StringIO(csv_text))

  for row in reader:
    winner = row["winner"].strip()
    loser = row["loser"].strip()
    score = float(row["score"])  # hoặc int(row["score"]) tùy logic elo của bạn

    for player in [winner, loser]:
      cur.execute(
          """
                INSERT OR IGNORE INTO players(name)
                VALUES(?)
                """,
          (player,),
      )

    cur.execute(
        """
            SELECT elo FROM players WHERE name=?
            """,
        (winner,),
    )
    winner_elo = cur.fetchone()[0]

    cur.execute(
        """
            SELECT elo FROM players WHERE name=?
            """,
        (loser,),
    )
    loser_elo = cur.fetchone()[0]

    change = calculate(winner_elo, loser_elo, score)

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
        (new_winner_elo, new_winner_elo, winner),
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
        (new_loser_elo, loser),
    )

    cur.execute(
        """
            INSERT INTO matches (winner, loser, change_elo)
            VALUES(?,?,?)
            """,
        (winner, loser, change),
    )

  db.commit()
  db.close()

  await ctx.send("✅ Đã import file và cập nhật Elo.")


# --- RESET ELO ---


@bot.command()
@commands.has_permissions(administrator=True)
async def resetelo(ctx):
  db = connect()
  cur = db.cursor()

  cur.execute("""
        UPDATE players
        SET
            elo=1500,
            wins=0,
            losses=0,
            highest_elo=1500,
            win_streak=0,
            best_streak=0
        """)

  cur.execute("DELETE FROM matches")

  db.commit()
  db.close()

  await ctx.send("🔄 Đã reset toàn bộ Elo.")


# --- SET NAME ---


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
      (old_name,),
  )
  player = cur.fetchone()

  if not player:
    await ctx.send("❌ Không tìm thấy người chơi.")
    db.close()
    return

  cur.execute(
      """
        SELECT name
        FROM players
        WHERE name=?
        """,
      (new_name,),
  )
  if cur.fetchone():
    await ctx.send("❌ Tên này đã tồn tại.")
    db.close()
    return

  last_change = player[0]

  if last_change:
    last_date = datetime.strptime(last_change, "%Y-%m-%d")
    next_change = last_date + timedelta(days=30)

    if datetime.now() < next_change:
      remain = (next_change - datetime.now()).days
      await ctx.send(f"⏳ Bạn phải chờ **{remain} ngày** nữa mới đổi tên được.")
      db.close()
      return

  cur.execute(
      """
        UPDATE players
        SET name=?, last_name_change=?
        WHERE name=?
        """,
      (new_name, datetime.now().strftime("%Y-%m-%d"), old_name),
  )

  cur.execute(
      """
        UPDATE matches SET winner=? WHERE winner=?
        """,
      (new_name, old_name),
  )

  cur.execute(
      """
        UPDATE matches SET loser=? WHERE loser=?
        """,
      (new_name, old_name),
  )

  db.commit()
  db.close()

  embed = discord.Embed(title="✏️ Đổi tên thành công", color=discord.Color.green())
  embed.add_field(name="Tên cũ", value=old_name, inline=True)
  embed.add_field(name="Tên mới", value=new_name, inline=True)

  await ctx.send(embed=embed)


# --- ERROR HANDLING ---


@bot.event
async def on_command_error(ctx, error):
  if isinstance(error, commands.CommandNotFound):
    return
  raise error
#token

bot.run("REDACTED_DISCORD_TOKEN")