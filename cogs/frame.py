import base64
import io
import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_connection
from utils.fuzzy import best_match


class FrameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="frame", description="Tra cứu Frame Data của một chiêu thức")
    @app_commands.describe(character="Tên nhân vật", move="Tên chiêu thức")
    async def frame(self, interaction: discord.Interaction, character: str, move: str):
        try:
            await interaction.response.defer()
        except Exception:
            pass

        conn = get_connection()
        try:
            character_row = conn.execute(
                "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
                (character,),
            ).fetchone()

            if not character_row:
                character_list = [row["name"] for row in conn.execute("SELECT name FROM characters ORDER BY name").fetchall()]
                matched = best_match(character, character_list, cutoff=60)
                if matched:
                    character_row = conn.execute(
                        "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
                        (matched,),
                    ).fetchone()
                else:
                    await interaction.followup.send("Không tìm thấy nhân vật phù hợp. Hãy kiểm tra lại tên hoặc chọn từ gợi ý.")
                    return

            move_row = conn.execute(
                """
                SELECT m.name, fd.startup, fd.active, fd.recovery,
                       fd.damage, fd.guard, fd.adv_on_block,
                       fd.adv_on_hit, fd.invulnerability, fd.image_url, fd.image_data, fd.notes
                FROM moves m
                LEFT JOIN frame_data fd ON fd.move_id = m.id
                WHERE m.character_id = ? AND LOWER(m.name) = LOWER(?)
                """,
                (character_row["id"], move),
            ).fetchone()

            if not move_row:
                move_list = [
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM moves WHERE character_id = ? ORDER BY name",
                        (character_row["id"],),
                    ).fetchall()
                ]
                matched_move = best_match(move, move_list, cutoff=55)
                if matched_move:
                    move_row = conn.execute(
                        """
                        SELECT m.name, fd.startup, fd.active, fd.recovery,
                               fd.damage, fd.guard, fd.adv_on_block,
                               fd.adv_on_hit, fd.invulnerability, fd.image_url, fd.image_data, fd.notes
                        FROM moves m
                        LEFT JOIN frame_data fd ON fd.move_id = m.id
                        WHERE m.character_id = ? AND LOWER(m.name) = LOWER(?)
                        """,
                        (character_row["id"], matched_move),
                    ).fetchone()
                else:
                    await interaction.followup.send(
                        f"Không tìm thấy chiêu thức phù hợp cho {character_row['name']}. Hãy thử tên gần đúng hơn."
                    )
                    return

            embed = discord.Embed(
                title=f"Frame Data - {character_row['name']}: {move_row['name']}",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Startup", value=str(move_row["startup"] if move_row["startup"] is not None else "N/A"), inline=True)
            embed.add_field(name="Active", value=str(move_row["active"] if move_row["active"] is not None else "N/A"), inline=True)
            embed.add_field(name="Recovery", value=str(move_row["recovery"] if move_row["recovery"] is not None else "N/A"), inline=True)
            embed.add_field(name="Damage", value=str(move_row["damage"] if move_row["damage"] is not None else "N/A"), inline=True)
            embed.add_field(name="Guard", value=move_row["guard"] or "N/A", inline=True)
            embed.add_field(name="Adv. on Hit", value=move_row["adv_on_hit"] or "N/A", inline=True)
            embed.add_field(name="Adv. on Block", value=move_row["adv_on_block"] or "N/A", inline=True)
            embed.add_field(name="Invulnerability", value=move_row["invulnerability"] or "N/A", inline=True)
            if move_row["notes"]:
                embed.add_field(name="Ghi chú", value=move_row["notes"], inline=False)


            file = None
            if "image_data" in move_row.keys() and move_row["image_data"]:
                try:
                    image_bytes = base64.b64decode(move_row["image_data"])
                    file = discord.File(io.BytesIO(image_bytes), filename="move.png")
                    embed.set_image(url="attachment://move.png")
                except Exception:
                    if move_row["image_url"]:
                        embed.set_image(url=move_row["image_url"])
            elif move_row["image_url"]:
                embed.set_image(url=move_row["image_url"])

            if file:
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(embed=embed)
        finally:
            conn.close()

    @staticmethod
    async def _character_autocomplete(interaction: discord.Interaction, current: str):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT name FROM characters WHERE LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT 25",
                (f"%{current}%",),
            ).fetchall()
            return [
                app_commands.Choice(name=row["name"], value=row["name"])
                for row in rows
            ]
        finally:
            conn.close()

    @staticmethod
    async def _move_autocomplete(interaction: discord.Interaction, current: str):
        character = getattr(interaction.namespace, "character", None)
        if not character:
            return []

        conn = get_connection()
        try:
            character_row = conn.execute(
                "SELECT id FROM characters WHERE LOWER(name) = LOWER(?)",
                (character,),
            ).fetchone()
            if not character_row:
                return []

            rows = conn.execute(
                "SELECT name FROM moves WHERE character_id = ? AND LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT 25",
                (character_row["id"], f"%{current}%"),
            ).fetchall()
            return [
                app_commands.Choice(name=row["name"], value=row["name"])
                for row in rows
            ]
        finally:
            conn.close()

    @frame.autocomplete("character")
    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_autocomplete(interaction, current)

    @frame.autocomplete("move")
    async def move_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._move_autocomplete(interaction, current)


async def setup(bot: commands.Bot):
    await bot.add_cog(FrameCog(bot))
