from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_connection


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, action_type: str, item_name: str, delete_callback):
        super().__init__(timeout=60)
        self.action_type = action_type
        self.item_name = item_name
        self.delete_callback = delete_callback

    @discord.ui.button(label="Xác nhận xóa", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        msg = await self.delete_callback()
        embed = discord.Embed(
            title="🗑️ Đã xóa thành công",
            description=msg,
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="❌ Đã hủy thao tác xóa",
            description=f"Dữ liệu **{self.item_name}** vẫn được giữ nguyên.",
            color=discord.Color.greyple(),
        )
        await interaction.response.edit_message(embed=embed, view=self)


class DeleteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    delete = app_commands.Group(name="delete", description="Xóa dữ liệu trong wiki")

    # --- DELETE CHARACTER ---
    @delete.command(name="character", description="Xóa một nhân vật cùng toàn bộ chiêu thức")
    @app_commands.describe(character="Tên nhân vật cần xóa")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_character(self, interaction: discord.Interaction, character: str):
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
                (character,),
            ).fetchone()

            if not row:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy nhân vật **{character}**.", ephemeral=True
                )
                return

            char_id = row["id"]
            char_name = row["name"]

            async def do_delete():
                c = get_connection()
                try:
                    # Lấy danh sách move_id thuộc character
                    moves = c.execute(
                        "SELECT id FROM moves WHERE character_id = ?", (char_id,)
                    ).fetchall()
                    move_ids = [m["id"] for m in moves]

                    if move_ids:
                        placeholders = ",".join("?" * len(move_ids))
                        c.execute(f"DELETE FROM frame_data WHERE move_id IN ({placeholders})", move_ids)
                        c.execute("DELETE FROM moves WHERE character_id = ?", (char_id,))

                    c.execute("DELETE FROM characters WHERE id = ?", (char_id,))
                    c.commit()
                    return f"Đã xóa nhân vật **{char_name}** và **{len(move_ids)}** chiêu thức liên quan."
                finally:
                    c.close()

            embed = discord.Embed(
                title="⚠️ Xác nhận xóa nhân vật",
                description=f"Bạn có chắc chắn muốn xóa nhân vật **{char_name}**?\n"
                f" Hành động này sẽ xóa vĩnh viễn toàn bộ chiêu thức và frame data của nhân vật này!",
                color=discord.Color.gold(),
            )
            view = ConfirmDeleteView("character", char_name, do_delete)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        finally:
            conn.close()

    @delete_character.autocomplete("character")
    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT name FROM characters WHERE LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT 25",
                (f"%{current}%",),
            ).fetchall()
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]
        finally:
            conn.close()

    # --- DELETE MOVE ---
    @delete.command(name="move", description="Xóa một chiêu thức của nhân vật")
    @app_commands.describe(character="Tên nhân vật", move="Tên chiêu thức cần xóa")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_move(self, interaction: discord.Interaction, character: str, move: str):
        conn = get_connection()
        try:
            m_row = conn.execute(
                """
                SELECT m.id AS move_id, m.name AS move_name, c.name AS char_name
                FROM moves m
                JOIN characters c ON c.id = m.character_id
                WHERE LOWER(c.name) = LOWER(?) AND LOWER(m.name) = LOWER(?)
                """,
                (character, move),
            ).fetchone()

            if not m_row:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy chiêu **{move}** của nhân vật **{character}**.", ephemeral=True
                )
                return

            move_id = m_row["move_id"]
            move_name = m_row["move_name"]
            char_name = m_row["char_name"]

            async def do_delete():
                c = get_connection()
                try:
                    c.execute("DELETE FROM frame_data WHERE move_id = ?", (move_id,))
                    c.execute("DELETE FROM moves WHERE id = ?", (move_id,))
                    c.commit()
                    return f"Đã xóa chiêu **{move_name}** của **{char_name}**."
                finally:
                    c.close()

            embed = discord.Embed(
                title="⚠️ Xác nhận xóa chiêu thức",
                description=f"Bạn có chắc chắn muốn xóa chiêu **{move_name}** của **{char_name}**?",
                color=discord.Color.gold(),
            )
            view = ConfirmDeleteView("move", f"{char_name} - {move_name}", do_delete)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        finally:
            conn.close()

    @delete_move.autocomplete("character")
    async def move_character_autocomplete(self, interaction: discord.Interaction, current: str):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT name FROM characters WHERE LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT 25",
                (f"%{current}%",),
            ).fetchall()
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]
        finally:
            conn.close()

    @delete_move.autocomplete("move")
    async def move_name_autocomplete(self, interaction: discord.Interaction, current: str):
        selected_char = getattr(interaction.namespace, "character", None)
        conn = get_connection()
        try:
            if selected_char:
                rows = conn.execute(
                    """
                    SELECT m.name FROM moves m
                    JOIN characters c ON c.id = m.character_id
                    WHERE LOWER(c.name) = LOWER(?) AND LOWER(m.name) LIKE LOWER(?)
                    ORDER BY m.name LIMIT 25
                    """,
                    (selected_char, f"%{current}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT name FROM moves WHERE LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT 25",
                    (f"%{current}%",),
                ).fetchall()
            return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]
        finally:
            conn.close()

    # --- DELETE GLOSSARY ---
    @delete.command(name="glossary", description="Xóa một thuật ngữ trong wiki")
    @app_commands.describe(term="Thuật ngữ cần xóa")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_glossary(self, interaction: discord.Interaction, term: str):
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, term FROM glossary WHERE LOWER(term) = LOWER(?)",
                (term,),
            ).fetchone()

            if not row:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy thuật ngữ **{term}**.", ephemeral=True
                )
                return

            term_id = row["id"]
            term_name = row["term"]

            async def do_delete():
                c = get_connection()
                try:
                    c.execute("DELETE FROM glossary WHERE id = ?", (term_id,))
                    c.commit()
                    return f"Đã xóa thuật ngữ **{term_name}**."
                finally:
                    c.close()

            embed = discord.Embed(
                title="⚠️ Xác nhận xóa thuật ngữ",
                description=f"Bạn có chắc chắn muốn xóa thuật ngữ **{term_name}**?",
                color=discord.Color.gold(),
            )
            view = ConfirmDeleteView("glossary", term_name, do_delete)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        finally:
            conn.close()

    @delete_glossary.autocomplete("term")
    async def glossary_autocomplete(self, interaction: discord.Interaction, current: str):
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT term FROM glossary WHERE LOWER(term) LIKE LOWER(?) ORDER BY term LIMIT 25",
                (f"%{current}%",),
            ).fetchall()
            return [app_commands.Choice(name=row["term"], value=row["term"]) for row in rows]
        finally:
            conn.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(DeleteCog(bot))
