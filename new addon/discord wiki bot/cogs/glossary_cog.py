import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_connection
from utils.fuzzy import best_match


class GlossaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="glossary", description="Tra cứu định nghĩa thuật ngữ trong game")
    @app_commands.describe(term="Thuật ngữ cần tra cứu")
    async def glossary(self, interaction: discord.Interaction, term: str):
        await interaction.response.defer()

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT term, definition, category, aliases FROM glossary WHERE LOWER(term) = LOWER(?)",
                (term,),
            ).fetchone()

            if not row:
                terms = [item["term"] for item in conn.execute("SELECT term FROM glossary ORDER BY term").fetchall()]
                matched = best_match(term, terms, cutoff=60)
                if matched:
                    row = conn.execute(
                        "SELECT term, definition, category, aliases FROM glossary WHERE LOWER(term) = LOWER(?)",
                        (matched,),
                    ).fetchone()
                else:
                    await interaction.followup.send("Không tìm thấy thuật ngữ phù hợp. Hãy thử từ khóa gần đúng hơn.")
                    return

            embed = discord.Embed(
                title=f"Thuật ngữ: {row['term']}",
                description=row["definition"],
                color=discord.Color.green(),
            )
            embed.add_field(name="Phân loại", value=row["category"] or "General", inline=True)
            if row["aliases"]:
                embed.add_field(name="Alias", value=row["aliases"], inline=True)

            await interaction.followup.send(embed=embed)
        finally:
            conn.close()

    @staticmethod
    async def _term_autocomplete(interaction: discord.Interaction, current: str):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT term FROM glossary WHERE LOWER(term) LIKE LOWER(?) ORDER BY term LIMIT 25",
                (f"%{current}%",),
            ).fetchall()
            return [
                app_commands.Choice(name=row["term"], value=row["term"])
                for row in rows
            ]
        finally:
            conn.close()

    @glossary.autocomplete("term")
    async def term_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._term_autocomplete(interaction, current)


async def setup(bot: commands.Bot):
    await bot.add_cog(GlossaryCog(bot))
