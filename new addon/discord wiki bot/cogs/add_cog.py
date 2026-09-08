import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_connection


def parse_optional_int(value: str, field_name: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} phải là số nguyên hoặc để trống.") from exc


def parse_optional_float(value: str, field_name: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} phải là số hoặc để trống.") from exc


class CharacterModal(discord.ui.Modal, title="Thêm nhân vật"):
    display_name = discord.ui.TextInput(
        label="Tên hiển thị",
        placeholder="Để trống nếu giống tên nhân vật",
        required=False,
        max_length=100,
    )
    aliases = discord.ui.TextInput(
        label="Tên khác",
        placeholder="Ngăn cách bằng dấu phẩy",
        required=False,
        max_length=500,
    )

    def __init__(self, character_name: str):
        super().__init__()
        self.character_name = character_name.strip()

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT 1 FROM characters WHERE LOWER(name) = LOWER(?)",
                (self.character_name,),
            ).fetchone()
            if existing:
                await interaction.response.send_message("Nhân vật này đã tồn tại.", ephemeral=True)
                return

            conn.execute(
                "INSERT INTO characters (name, display_name, aliases) VALUES (?, ?, ?)",
                (
                    self.character_name,
                    self.display_name.value.strip() or self.character_name,
                    self.aliases.value.strip(),
                ),
            )
            conn.commit()
            await interaction.response.send_message(
                f"Đã thêm nhân vật **{self.character_name}**.", ephemeral=True
            )
        finally:
            conn.close()


class MoveDetailsModal(discord.ui.Modal, title="Thông số chiêu thức"):
    startup = discord.ui.TextInput(label="Startup", required=False, max_length=10)
    active = discord.ui.TextInput(label="Active", required=False, max_length=10)
    recovery = discord.ui.TextInput(label="Recovery", required=False, max_length=10)
    on_hit = discord.ui.TextInput(label="On hit", required=False, max_length=10)
    on_block = discord.ui.TextInput(label="On block", required=False, max_length=10)

    def __init__(self, character_id: int, character_name: str, move_name: str, image_url: str):
        super().__init__()
        self.character_id = character_id
        self.character_name = character_name
        self.move_name = move_name.strip()
        self.image_url = image_url

    async def on_submit(self, interaction: discord.Interaction):
        try:
            startup = parse_optional_int(self.startup.value, "Startup")
            active = parse_optional_int(self.active.value, "Active")
            recovery = parse_optional_int(self.recovery.value, "Recovery")
            on_hit = parse_optional_int(self.on_hit.value, "On hit")
            on_block = parse_optional_int(self.on_block.value, "On block")
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await interaction.response.send_modal(
            MoveExtraModal(
                character_id=self.character_id,
                character_name=self.character_name,
                move_name=self.move_name,
                image_url=self.image_url,
                startup=startup,
                active=active,
                recovery=recovery,
                on_hit=on_hit,
                on_block=on_block,
            )
        )


class MoveExtraModal(discord.ui.Modal, title="Thông tin bổ sung"):
    damage = discord.ui.TextInput(label="Damage", required=False, max_length=10)
    guard = discord.ui.TextInput(label="Guard", required=False, max_length=100)
    adv_on_block = discord.ui.TextInput(label="Adv. on Block", required=False, max_length=20)
    adv_on_hit = discord.ui.TextInput(label="Adv. on Hit", required=False, max_length=20)
    invulnerability = discord.ui.TextInput(label="Invulnerability", required=False, max_length=100)

    def __init__(
        self,
        character_id: int,
        character_name: str,
        move_name: str,
        image_url: str,
        startup: int | None,
        active: int | None,
        recovery: int | None,
        on_hit: int | None,
        on_block: int | None,
    ):
        super().__init__()
        self.character_id = character_id
        self.character_name = character_name
        self.move_name = move_name
        self.image_url = image_url
        self.startup = startup
        self.active = active
        self.recovery = recovery
        self.on_hit = on_hit
        self.on_block = on_block

    async def on_submit(self, interaction: discord.Interaction):
        try:
            damage = parse_optional_float(self.damage.value, "Damage")
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT 1 FROM moves WHERE character_id = ? AND LOWER(name) = LOWER(?)",
                (self.character_id, self.move_name),
            ).fetchone()
            if existing:
                await interaction.response.send_message(
                    f"Chiêu **{self.move_name}** của **{self.character_name}** đã tồn tại.",
                    ephemeral=True,
                )
                return

            cursor = conn.execute(
                """
                INSERT INTO moves (character_id, name, normalized_name, move_type, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.character_id,
                    self.move_name,
                    self.move_name.lower(),
                    "normal",
                    self.notes.value.strip(),
                ),
            )
            conn.execute(
                """
                INSERT INTO frame_data (
                    move_id, startup, active, recovery, on_hit, on_block, damage,
                    guard, adv_on_block, adv_on_hit, invulnerability, image_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    self.startup,
                    self.active,
                    self.recovery,
                    self.on_hit,
                    self.on_block,
                    damage,
                    self.guard.value.strip(),
                    self.adv_on_block.value.strip(),
                    self.adv_on_hit.value.strip(),
                    self.invulnerability.value.strip(),
                    self.image_url,
                ),
            )
            conn.commit()
            await interaction.response.send_message(
                f"Đã thêm chiêu **{self.move_name}** cho **{self.character_name}**.",
                ephemeral=True,
            )
        finally:
            conn.close()


class AddCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    add = app_commands.Group(name="add", description="Thêm dữ liệu vào wiki")

    @add.command(name="character", description="Thêm một nhân vật mới")
    @app_commands.describe(name="Tên nhân vật")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_character(self, interaction: discord.Interaction, name: str):
        if not name.strip():
            await interaction.response.send_message("Tên nhân vật không được để trống.", ephemeral=True)
            return
        await interaction.response.send_modal(CharacterModal(name))

    @add.command(name="move", description="Thêm chiêu thức và frame data")
    @app_commands.describe(
        character="Tên nhân vật",
        name="Tên chiêu thức",
        image="Ảnh minh họa chiêu thức (tùy chọn)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_move(
        self,
        interaction: discord.Interaction,
        character: str,
        name: str,
        image: discord.Attachment | None = None,
    ):
        if not name.strip():
            await interaction.response.send_message("Tên chiêu thức không được để trống.", ephemeral=True)
            return

        conn = get_connection()
        try:
            character_row = conn.execute(
                "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
                (character,),
            ).fetchone()
        finally:
            conn.close()

        if not character_row:
            await interaction.response.send_message(
                f"Không tìm thấy nhân vật **{character}**. Hãy thêm nhân vật trước.",
                ephemeral=True,
            )
            return
        image_url = ""
        if image:
            if not image.content_type or not image.content_type.startswith("image/"):
                await interaction.response.send_message("File đính kèm phải là ảnh.", ephemeral=True)
                return
            image_url = image.url
        await interaction.response.send_modal(
            MoveDetailsModal(character_row["id"], character_row["name"], name, image_url)
        )

    @add_move.autocomplete("character")
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


async def setup(bot: commands.Bot):
    await bot.add_cog(AddCog(bot))