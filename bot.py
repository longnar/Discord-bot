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
from dotenv import load_dotenv

load_dotenv()


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

from utils.db import init_db

# Khởi tạo CSDL Elo và Wiki
create_tables()
init_db()

async def setup_hook():

  # Tải các cogs
  await bot.load_extension("cogs.help")
  print("[Cog] Da tai thành cong Cog: Help")
  await bot.load_extension("cogs.welcome")
  print("[Cog] Da tai thành cong Cog: Welcome")
  await bot.load_extension("cogs.frame")
  print("[Cog] Da tai thành cong Cog: Frame Data")
  await bot.load_extension("cogs.glossary")
  print("[Cog] Da tai thành cong Cog: Glossary")
  await bot.load_extension("cogs.add")
  print("[Cog] Da tai thành cong Cog: Add Wiki")
  await bot.load_extension("cogs.edit_cog")
  print("[Cog] Da tai thành cong Cog: Edit Wiki")
  await bot.load_extension("cogs.delete_cog")
  print("[Cog] Da tai thành cong Cog: Delete Wiki")
  await bot.load_extension("cogs.elo_cog")
  print("[Cog] Da tai thành cong Cog: Elo")

  # Đồng bộ lệnh Slash lên Discord
  await bot.tree.sync()
  print("[OK] Da dong bo Slash Commands!")



# Gắn setup_hook vào bot
bot.setup_hook = setup_hook



@bot.event
async def on_ready():
  print(f"[OK] Bot {bot.user} is ready!")



# --- teto ---
@bot.tree.command(name="teto", description="Gửi GIF Kasane Teto")
async def teto(interaction: discord.Interaction):
  file_gif = discord.File("Kasane Teto GIF.gif")
  await interaction.response.send_message("Teto beo vcl", file=file_gif)

# --- migu ---
@bot.tree.command(name="migu", description="Gửi GIF Migu")
async def migu(interaction: discord.Interaction):
  file_gif = discord.File("migu.gif")
  await interaction.response.send_message("?:wilted_rose: ", file=file_gif)

@bot.tree.command(name="summon-cat", description="Gửi GIF FBK")
async def fbk(interaction: discord.Interaction):
  file_gif = discord.File("fbk-eating.gif")
  await interaction.response.send_message("hmm", file=file_gif)

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
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("Thiếu DISCORD_TOKEN trong file .env!")

bot.run(token)

