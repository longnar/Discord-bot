import asyncio
import os
from pathlib import Path

from aiohttp import web
import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from database import create_tables
from utils.db import init_db

BASE_DIR = Path(__file__).resolve().parent

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def setup_hook():
    # Tải các cogs
    await bot.load_extension("cogs.help")
    print("[Cog] Da tai thanh cong Cog: Help")
    await bot.load_extension("cogs.welcome")
    print("[Cog] Da tai thanh cong Cog: Welcome")
    await bot.load_extension("cogs.frame")
    print("[Cog] Da tai thanh cong Cog: Frame Data")
    await bot.load_extension("cogs.glossary")
    print("[Cog] Da tai thanh cong Cog: Glossary")
    await bot.load_extension("cogs.add")
    print("[Cog] Da tai thanh cong Cog: Add Wiki")
    await bot.load_extension("cogs.edit_cog")
    print("[Cog] Da tai thanh cong Cog: Edit Wiki")
    await bot.load_extension("cogs.delete_cog")
    print("[Cog] Da tai thanh cong Cog: Delete Wiki")
    await bot.load_extension("cogs.elo_cog")
    print("[Cog] Da tai thanh cong Cog: Elo")

    # Chỉ đồng bộ Slash Commands tự động khi bật SYNC_COMMANDS=true (tránh rate limit khi restart)
    if os.getenv("SYNC_COMMANDS", "false").strip().lower() in ("1", "true", "yes"):
        await bot.tree.sync()
        print("[OK] Da dong bo Slash Commands!")
    else:
        print("[INFO] Bo qua tree.sync() khi khoi dong (bat SYNC_COMMANDS=true hoac dung !sync).")


# Gắn setup_hook vào bot
bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    print(f"[OK] Bot {bot.user} is ready!")


@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync_commands(ctx: commands.Context):
    """Đồng bộ lại Slash Commands lên Discord thủ công (Admin)."""
    synced = await bot.tree.sync()
    await ctx.send(f"✅ Đã đồng bộ **{len(synced)}** Slash Commands lên Discord.")


# --- teto ---
@bot.tree.command(name="teto", description="Gửi GIF Kasane Teto")
async def teto(interaction: discord.Interaction):
    file_gif = discord.File(BASE_DIR / "Kasane Teto GIF.gif")
    await interaction.response.send_message("Teto beo vcl", file=file_gif)


# --- migu ---
@bot.tree.command(name="migu", description="Gửi GIF Migu")
async def migu(interaction: discord.Interaction):
    file_gif = discord.File(BASE_DIR / "migu.gif")
    await interaction.response.send_message("?:wilted_rose: ", file=file_gif)


@bot.tree.command(name="summon-cat", description="Gửi GIF FBK")
async def fbk(interaction: discord.Interaction):
    file_gif = discord.File(BASE_DIR / "fbk-eating.gif")
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


async def start_health_server(discord_bot: commands.Bot) -> web.AppRunner | None:
    """Khởi chạy HTTP healthcheck server khi có biến PORT (Render Web Service) hoặc ENABLE_HEALTH_SERVER=true."""
    port_env = os.getenv("PORT", "").strip()
    enable_health = os.getenv("ENABLE_HEALTH_SERVER", "false").strip().lower() in ("1", "true", "yes")
    if not port_env and not enable_health:
        return None

    port = int(port_env or "10000")

    async def health_handler(request: web.Request) -> web.Response:
        ready = discord_bot.is_ready()
        payload = {
            "status": "ok",
            "bot_ready": ready,
            "user": str(discord_bot.user) if discord_bot.user else None,
            "latency_ms": round(discord_bot.latency * 1000, 1) if ready else None,
        }
        return web.json_response(payload, status=200)

    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"[OK] Healthcheck server dang lang nghe tai http://0.0.0.0:{port}/health")
    return runner


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "your_discord_bot_token_here":
        raise RuntimeError(
            "Thieu bien moi truong DISCORD_TOKEN! Hay cap nhat trong .env hoac Render Environment Variables."
        )

    runner = await start_health_server(bot)
    try:
        # Khởi tạo schema Elo và Wiki (Turso hoặc SQLite fallback)
        create_tables()
        init_db()
        async with bot:
            await bot.start(token)
    finally:
        if runner is not None:
            await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[INFO] Bot da dung.")

