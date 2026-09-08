import base64
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_connection


# --- MODAL EDIT CHARACTER ---
class EditCharacterModal(discord.ui.Modal, title="Sửa nhân vật"):
    display_name = discord.ui.TextInput(
        label="Tên hiển thị",
        placeholder="Nhập tên hiển thị mới",
        required=False,
        max_length=100,
    )
    aliases = discord.ui.TextInput(
        label="Tên khác (Aliases)",
        placeholder="Ngăn cách bằng dấu phẩy",
        required=False,
        max_length=500,
    )

    def __init__(self, character_id: int, current_name: str, current_display: str, current_aliases: str):
        super().__init__()
        self.character_id = character_id
        self.current_name = current_name
        self.display_name.default = current_display or ""
        self.aliases.default = current_aliases or ""

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE characters
                SET display_name = ?, aliases = ?
                WHERE id = ?
                """,
                (
                    self.display_name.value.strip() or self.current_name,
                    self.aliases.value.strip(),
                    self.character_id,
                ),
            )
            conn.commit()
            await interaction.response.send_message(
                f"✅ Đã cập nhật nhân vật **{self.current_name}** thành công!", ephemeral=True
            )
        finally:
            conn.close()


# --- MODAL EDIT GLOSSARY ---
class EditGlossaryModal(discord.ui.Modal, title="Sửa thuật ngữ"):
    definition = discord.ui.TextInput(
        label="Định nghĩa",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )
    category = discord.ui.TextInput(
        label="Phân loại",
        placeholder="Ví dụ: pressure, defense, general",
        required=False,
        max_length=100,
    )
    aliases = discord.ui.TextInput(
        label="Tên gọi khác",
        placeholder="Ngăn cách bằng dấu phẩy",
        required=False,
        max_length=500,
    )

    def __init__(self, term_id: int, term: str, current_def: str, current_cat: str, current_aliases: str):
        super().__init__()
        self.term_id = term_id
        self.term = term
        self.definition.default = current_def or ""
        self.category.default = current_cat or ""
        self.aliases.default = current_aliases or ""

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE glossary
                SET definition = ?, category = ?, aliases = ?
                WHERE id = ?
                """,
                (
                    self.definition.value.strip(),
                    self.category.value.strip() or "general",
                    self.aliases.value.strip(),
                    self.term_id,
                ),
            )
            conn.commit()
            await interaction.response.send_message(
                f"✅ Đã cập nhật thuật ngữ **{self.term}** thành công!", ephemeral=True
            )
        finally:
            conn.close()


# --- MODAL EDIT MOVE (PART 1) ---
class EditMoveModal(discord.ui.Modal, title="Sửa thông số chiêu thức"):
    startup = discord.ui.TextInput(label="Startup", required=False, max_length=10)
    active = discord.ui.TextInput(label="Active", required=False, max_length=10)
    recovery = discord.ui.TextInput(label="Recovery", required=False, max_length=10)
    damage = discord.ui.TextInput(label="Damage", required=False, max_length=10)
    guard = discord.ui.TextInput(label="Guard", required=False, max_length=100)

    def __init__(
        self,
        move_id: int,
        character_name: str,
        move_name: str,
        fd_row: dict,
        new_image_url: str = "",
        new_image_data: str = "",
    ):
        super().__init__()
        self.move_id = move_id
        self.character_name = character_name
        self.move_name = move_name
        self.fd_row = fd_row or {}
        self.new_image_url = new_image_url
        self.new_image_data = new_image_data

        if self.fd_row.get("startup") is not None:
            self.startup.default = str(self.fd_row.get("startup"))
        if self.fd_row.get("active") is not None:
            self.active.default = str(self.fd_row.get("active"))
        if self.fd_row.get("recovery") is not None:
            self.recovery.default = str(self.fd_row.get("recovery"))
        if self.fd_row.get("damage") is not None:
            self.damage.default = str(self.fd_row.get("damage"))
        if self.fd_row.get("guard"):
            self.guard.default = str(self.fd_row.get("guard"))

    async def on_submit(self, interaction: discord.Interaction):
        # Mở tiếp Modal Part 2 (Extra Modal)
        extra_modal = EditMoveExtraModal(
            move_id=self.move_id,
            character_name=self.character_name,
            move_name=self.move_name,
            startup_val=self.startup.value.strip(),
            active_val=self.active.value.strip(),
            recovery_val=self.recovery.value.strip(),
            damage_val=self.damage.value.strip(),
            guard_val=self.guard.value.strip(),
            fd_row=self.fd_row,
            new_image_url=self.new_image_url,
            new_image_data=self.new_image_data,
        )
        view = EditNextStepView(extra_modal)
        await interaction.response.send_message(
            f"✅ Đã ghi nhận thông số Phần 1 cho **{self.move_name}**!\n"
            f"Bấm nút **Nhập tiếp phần 2** bên dưới để cập nhật Adv. on Hit/Block, Invulnerability và Ghi chú.",
            view=view,
            ephemeral=True,
        )


class EditNextStepView(discord.ui.View):
    def __init__(self, extra_modal):
        super().__init__(timeout=180)
        self.extra_modal = extra_modal

    @discord.ui.button(label="Nhập tiếp phần 2", style=discord.ButtonStyle.primary)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.extra_modal)


# --- MODAL EDIT MOVE (PART 2) ---
class EditMoveExtraModal(discord.ui.Modal, title="Sửa thông số bổ sung (Phần 2)"):
    adv_on_hit = discord.ui.TextInput(label="Adv. on Hit", required=False, max_length=20)
    adv_on_block = discord.ui.TextInput(label="Adv. on Block", required=False, max_length=20)
    invulnerability = discord.ui.TextInput(label="Invulnerability", required=False, max_length=100)
    notes = discord.ui.TextInput(label="Ghi chú", required=False, max_length=300)

    def __init__(
        self,
        move_id: int,
        character_name: str,
        move_name: str,
        startup_val: str,
        active_val: str,
        recovery_val: str,
        damage_val: str,
        guard_val: str,
        fd_row: dict,
        new_image_url: str = "",
        new_image_data: str = "",
    ):
        super().__init__()
        self.move_id = move_id
        self.character_name = character_name
        self.move_name = move_name
        self.startup_val = startup_val
        self.active_val = active_val
        self.recovery_val = recovery_val
        self.damage_val = damage_val
        self.guard_val = guard_val
        self.fd_row = fd_row or {}
        self.new_image_url = new_image_url
        self.new_image_data = new_image_data

        if self.fd_row.get("adv_on_hit"):
            self.adv_on_hit.default = str(self.fd_row.get("adv_on_hit"))
        if self.fd_row.get("adv_on_block"):
            self.adv_on_block.default = str(self.fd_row.get("adv_on_block"))
        if self.fd_row.get("invulnerability"):
            self.invulnerability.default = str(self.fd_row.get("invulnerability"))
        if self.fd_row.get("notes"):
            self.notes.default = str(self.fd_row.get("notes"))

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_connection()
        try:
            # Parse kiểu dữ liệu
            startup = int(self.startup_val) if self.startup_val.lstrip("+-").isdigit() else None
            active = int(self.active_val) if self.active_val.lstrip("+-").isdigit() else None
            recovery = int(self.recovery_val) if self.recovery_val.lstrip("+-").isdigit() else None
            try:
                damage = float(self.damage_val) if self.damage_val else None
            except ValueError:
                damage = None

            # Cập nhật bảng moves
            conn.execute(
                "UPDATE moves SET notes = ? WHERE id = ?",
                (self.notes.value.strip(), self.move_id),
            )

            # Cập nhật hoặc chèn bảng frame_data
            fd_exists = conn.execute(
                "SELECT 1 FROM frame_data WHERE move_id = ?", (self.move_id,)
            ).fetchone()

            img_url = self.new_image_url or self.fd_row.get("image_url", "")
            img_data = self.new_image_data or self.fd_row.get("image_data", "")

            if fd_exists:
                conn.execute(
                    """
                    UPDATE frame_data
                    SET startup=?, active=?, recovery=?, damage=?, guard=?,
                        adv_on_block=?, adv_on_hit=?, invulnerability=?,
                        image_url=CASE WHEN ? != '' THEN ? ELSE image_url END,
                        image_data=CASE WHEN ? != '' THEN ? ELSE image_data END,
                        notes=?
                    WHERE move_id=?
                    """,
                    (
                        startup,
                        active,
                        recovery,
                        damage,
                        self.guard_val,
                        self.adv_on_block.value.strip(),
                        self.adv_on_hit.value.strip(),
                        self.invulnerability.value.strip(),
                        img_url,
                        img_url,
                        img_data,
                        img_data,
                        self.notes.value.strip(),
                        self.move_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO frame_data (
                        move_id, startup, active, recovery, damage, guard,
                        adv_on_block, adv_on_hit, invulnerability, image_url, image_data, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.move_id,
                        startup,
                        active,
                        recovery,
                        damage,
                        self.guard_val,
                        self.adv_on_block.value.strip(),
                        self.adv_on_hit.value.strip(),
                        self.invulnerability.value.strip(),
                        img_url,
                        img_data,
                        self.notes.value.strip(),
                    ),
                )

            conn.commit()
            await interaction.response.send_message(
                f"✅ Đã cập nhật thành công chiêu **{self.move_name}** của **{self.character_name}**!",
                ephemeral=True,
            )
        finally:
            conn.close()


# --- EDIT COG ---
class EditCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    edit = app_commands.Group(name="edit", description="Chỉnh sửa thông tin trong wiki")

    # --- EDIT CHARACTER ---
    @edit.command(name="character", description="Chỉnh sửa thông tin nhân vật")
    @app_commands.describe(character="Tên nhân vật cần sửa")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def edit_character(self, interaction: discord.Interaction, character: str):
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, name, display_name, aliases FROM characters WHERE LOWER(name) = LOWER(?)",
                (character,),
            ).fetchone()

            if not row:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy nhân vật **{character}**.", ephemeral=True
                )
                return

            await interaction.response.send_modal(
                EditCharacterModal(
                    character_id=row["id"],
                    current_name=row["name"],
                    current_display=row["display_name"],
                    current_aliases=row["aliases"],
                )
            )
        finally:
            conn.close()

    @edit_character.autocomplete("character")
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

    # --- EDIT GLOSSARY ---
    @edit.command(name="glossary", description="Chỉnh sửa định nghĩa thuật ngữ")
    @app_commands.describe(term="Thuật ngữ cần sửa")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def edit_glossary(self, interaction: discord.Interaction, term: str):
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, term, definition, category, aliases FROM glossary WHERE LOWER(term) = LOWER(?)",
                (term,),
            ).fetchone()

            if not row:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy thuật ngữ **{term}**.", ephemeral=True
                )
                return

            await interaction.response.send_modal(
                EditGlossaryModal(
                    term_id=row["id"],
                    term=row["term"],
                    current_def=row["definition"],
                    current_cat=row["category"],
                    current_aliases=row["aliases"],
                )
            )
        finally:
            conn.close()

    @edit_glossary.autocomplete("term")
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

    # --- EDIT MOVE ---
    @edit.command(name="move", description="Chỉnh sửa chiêu thức và frame data")
    @app_commands.describe(
        character="Tên nhân vật",
        move="Tên chiêu thức cần sửa",
        image="Ảnh minh họa mới (tùy chọn)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def edit_move(
        self,
        interaction: discord.Interaction,
        character: str,
        move: str,
        image: Optional[discord.Attachment] = None,
    ):
        conn = get_connection()
        try:
            m_row = conn.execute(
                """
                SELECT m.id AS move_id, m.name AS move_name, c.name AS char_name,
                       fd.startup, fd.active, fd.recovery, fd.damage, fd.guard,
                       fd.adv_on_block, fd.adv_on_hit, fd.invulnerability,
                       fd.image_url, fd.image_data, fd.notes
                FROM moves m
                JOIN characters c ON c.id = m.character_id
                LEFT JOIN frame_data fd ON fd.move_id = m.id
                WHERE LOWER(c.name) = LOWER(?) AND LOWER(m.name) = LOWER(?)
                """,
                (character, move),
            ).fetchone()

            if not m_row:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy chiêu **{move}** của **{character}**.", ephemeral=True
                )
                return

            new_image_url = ""
            new_image_data = ""
            if image:
                if not image.content_type or not image.content_type.startswith("image/"):
                    await interaction.response.send_message("File đính kèm phải là ảnh.", ephemeral=True)
                    return
                new_image_url = image.url
                try:
                    img_bytes = await image.read()
                    new_image_data = base64.b64encode(img_bytes).decode("utf-8")
                except Exception:
                    new_image_data = ""

            fd_dict = dict(m_row) if m_row else {}

            await interaction.response.send_modal(
                EditMoveModal(
                    move_id=m_row["move_id"],
                    character_name=m_row["char_name"],
                    move_name=m_row["move_name"],
                    fd_row=fd_dict,
                    new_image_url=new_image_url,
                    new_image_data=new_image_data,
                )
            )
        finally:
            conn.close()

    @edit_move.autocomplete("character")
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

    @edit_move.autocomplete("move")
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


async def setup(bot: commands.Bot):
    await bot.add_cog(EditCog(bot))
