import discord
from discord.ext import commands

from app.config import DISCORD_GUILD_ID, DISCORD_TOKEN

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if DISCORD_GUILD_ID:
        guild = discord.Object(id=DISCORD_GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()

    print("Slash commands synced.")


async def load_cogs():
    await bot.load_extension("cogs.frame_cog")
    await bot.load_extension("cogs.glossary_cog")
    await bot.load_extension("cogs.add_cog")


async def main():
    await load_cogs()
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
