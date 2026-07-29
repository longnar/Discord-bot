import csv
from datetime import datetime, timedelta
from enum import member
import io
from random import random
from database import connect, create_tables
import discord
from discord.ext import commands
from elo import calculate
from discord import app_commands
from typing import List
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def setup_hook():
  # Tải file help.py từ thư mục cogs
  await bot.load_extension("cogs.help")
  print("📦 Đã tải thành công Cog: Help")
  await bot.load_extension("cogs.welcome")
  # Đồng bộ lệnh Slash lên Discord (Nếu test thì để guild=MY_GUILD như bài trước)
  await bot.tree.sync()
  print("✅ Đã đồng bộ Slash Commands!")


# Gắn setup_hook vào bot
bot.setup_hook = setup_hook


@bot.event
async def on_ready():
  print(f"Bot {bot.user} đã sẵn sàng!")


#--- DATABASE AUTOCOMMPLETE ---
async def player_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
  db = connect()
  cur = db.cursor()

  # 'current' chính là những chữ cái mà người dùng đang gõ dở trong khung chat
  if current:
    # Nếu người dùng đang gõ chữ -> Tìm các tên có chứa chữ cái đó (không phân biệt hoa/thường)
    # LIMIT 25 là bắt buộc để không vi phạm luật của Discord
    cur.execute(
        """
            SELECT name FROM players 
            WHERE name LIKE ? 
            ORDER BY elo DESC 
            LIMIT 25
            """,
        (f"%{current}%",),
    )
  else:
    # Nếu người dùng chưa gõ chữ nào (chỉ mới bấm vào lệnh /elo) -> Gợi ý ngay Top 25 người Elo cao nhất
    cur.execute("""
            SELECT name FROM players 
            ORDER BY elo DESC 
            LIMIT 25
            """)

  players = cur.fetchall()
  db.close()

  # Biến đổi dữ liệu từ SQLite thành định dạng Choice của Discord
  # name: Chữ hiển thị trên menu gợi ý | value: Giá trị thực sự gửi cho bot khi bấm chọn
  return [app_commands.Choice(name=row[0], value=row[0]) for row in players]

# --- ELO COMMANDS ---


@bot.tree.command(name="elo", description="Xem Elo của người chơi hoặc bảng xếp hạng")
@app_commands.autocomplete(player_name=player_name_autocomplete)
async def elo(interaction: discord.Interaction, player_name: str = None):
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
      await interaction.response.send_message("Không tìm thấy người chơi")
      db.close()
      return

    name, elo_val, wins, losses = player

    if wins + losses == 0:
      await interaction.response.send_message(f"{name} chưa đánh mà đòi có Elo à :v")
      db.close()
      return

    embed = discord.Embed(title="🏆 ISDVN Player Elo", color=discord.Color.blue())
    embed.add_field(name="Tên", value=name, inline=False)
    embed.add_field(name="💎 Elo", value=round(elo_val), inline=True)
    embed.add_field(name="⚔ W-L", value=f"{wins}W • {losses}L", inline=True)

    await interaction.response.send_message(embed=embed)
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
    await interaction.response.send_message("Chưa có dữ liệu")
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
  await interaction.response.send_message(embed=embed)
  db.close()


# --- PROFILE COMMAND ---


@bot.tree.command(name="profile", description="Xem thông tin chi tiết của người chơi")
async def profile(interaction: discord.Interaction, player_name: str = None):
  if player_name is None:
    player_name = interaction.user.name

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
    await interaction.response.send_message("Không tìm thấy người chơi")
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

  await interaction.response.send_message(embed=embed)
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
    score = row["score"].strip()  # hoặc int(row["score"]) tùy logic elo của bạn

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


@bot.tree.command(name="setname", description="Đổi tên người chơi")
async def setname(interaction: discord.Interaction, old_name: str, new_name: str):
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
    await interaction.response.send_message("❌ Không tìm thấy người chơi.")
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
    await interaction.response.send_message("❌ Tên này đã tồn tại.")
    db.close()
    return

  last_change = player[0]

  if last_change:
    last_date = datetime.strptime(last_change, "%Y-%m-%d")
    next_change = last_date + timedelta(days=30)

    if datetime.now() < next_change:
      remain = (next_change - datetime.now()).days
      await interaction.response.send_message(f"⏳ Bạn phải chờ **{remain} ngày** nữa mới đổi tên được.")
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

  await interaction.response.send_message(embed=embed)


# --- teto ---
@bot.tree.command(name="teto", description="Gửi GIF Kasane Teto")
async def teto(interaction: discord.Interaction):
  file_gif = discord.File("Kasane Teto GIF.gif")
  await interaction.response.send_message("Teto beo vcl", file=file_gif)

# --- migu ---
@bot.tree.command(name="migu", description="Gửi GIF Migu")
async def migu(interaction: discord.Interaction):
  file_gif = discord.File("migu.gif")
  await interaction.response.send_message("Vc Migu là sao??:wilted_rose: ", file=file_gif)

# --- Gambling? ---
# @bot.tree.command(name="gamble", description="Làm tí may rủi?")
# async def gamble(interaction: discord.Interaction):
#   folder_path = "images"  # Tên folder chứa ảnh của bạn

#   # 1. Kiểm tra xem folder có tồn tại không
#   if not os.path.exists(folder_path):
#     await interaction.response.send_message(
#         "❌ Lỗi: Không tìm thấy thư mục `images`!", ephemeral=True
#     )
#     return

#   # 2. Lấy toàn bộ danh sách file trong folder (lọc bỏ các file rác không phải là ảnh)
#   valid_extensions = (".png", ".jpg", ".jpeg", ".gif")
#   all_images = [
#       file
#       for file in os.listdir(folder_path)
#       if file.lower().endswith(valid_extensions)
#   ]

#   # 3. Kiểm tra xem trong folder có ảnh nào không
#   if not all_images:
#     await interaction.response.send_message(
#         "❌ Thư mục `images` hiện đang trống, chưa có ảnh nào!", ephemeral=True
#     )
#     return

#   # 4. Chọn ngẫu nhiên 1 tên file ảnh từ danh sách
#   random_image = random.choice(all_images)
#   file_path = os.path.join(
#       folder_path, random_image
#   )  # Tạo đường dẫn (ví dụ: images/meme.png)

#   # 5. Gói file và gửi lên Discord
#   image_file = discord.File(file_path, filename=random_image)

#   await interaction.response.send_message(
#       content=f"🎲 Bạn đã quay được bức ảnh: **{random_image}**", file=image_file
#   )

# --- ERROR HANDLING ---

@bot.event
async def on_command_error(ctx, error):
  if isinstance(error, commands.CommandNotFound):
    return
  raise error
#token

bot.run("REDACTED_DISCORD_TOKEN")

