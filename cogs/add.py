import base64
import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_connection


def parse_optional_int(value: str, field_name: str) -> int | None:
    value = value.strip().lstrip("+")
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


def safe_parse_int(value: str) -> int | None:
    value = value.strip().lstrip("+")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


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


class MoveExtraModal(discord.ui.Modal, title="Thông tin bổ sung (Phần 2)"):
    adv_on_hit = discord.ui.TextInput(label="Adv. on Hit", placeholder="Ví dụ: +2 hoặc KD", required=False, max_length=20)
    adv_on_block = discord.ui.TextInput(label="Adv. on Block", placeholder="Ví dụ: -3 hoặc +1", required=False, max_length=20)
    invulnerability = discord.ui.TextInput(label="Invulnerability", placeholder="Ví dụ: 1-6f Strike/Projectile hoặc None", required=False, max_length=100)
    notes = discord.ui.TextInput(label="Ghi chú", required=False, max_length=300)

    def __init__(
        self,
        character_id: int,
        character_name: str,
        move_name: str,
        image_url: str,
        image_data: str,
        startup: int | None,
        active: int | None,
        recovery: int | None,
        damage: float | None,
        guard: str,
    ):
        super().__init__()
        self.character_id = character_id
        self.character_name = character_name
        self.move_name = move_name
        self.image_url = image_url
        self.image_data = image_data
        self.startup = startup
        self.active = active
        self.recovery = recovery
        self.damage = damage
        self.guard = guard

    async def on_submit(self, interaction: discord.Interaction):
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

            adv_on_hit_str = self.adv_on_hit.value.strip()
            adv_on_block_str = self.adv_on_block.value.strip()

            conn.execute(
                """
                INSERT INTO frame_data (
                    move_id, startup, active, recovery, damage,
                    guard, adv_on_block, adv_on_hit, invulnerability, image_url, image_data
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    self.startup,
                    self.active,
                    self.recovery,
                    self.damage,
                    self.guard,
                    adv_on_block_str,
                    adv_on_hit_str,
                    self.invulnerability.value.strip(),
                    self.image_url,
                    self.image_data,
                ),
            )

            conn.commit()
            await interaction.response.send_message(
                f"✅ Đã lưu thành công chiêu **{self.move_name}** cho **{self.character_name}**!",
                ephemeral=True,
            )
        finally:
            conn.close()


class NextStepView(discord.ui.View):
    def __init__(self, extra_modal: MoveExtraModal):
        super().__init__(timeout=180)
        self.extra_modal = extra_modal

    @discord.ui.button(label="Nhập tiếp phần 2", style=discord.ButtonStyle.primary)
    async def next_step_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.extra_modal)


class MoveDetailsModal(discord.ui.Modal, title="Thông số chiêu thức (Phần 1)"):
    startup = discord.ui.TextInput(label="Startup", required=False, max_length=10)
    active = discord.ui.TextInput(label="Active", required=False, max_length=10)
    recovery = discord.ui.TextInput(label="Recovery", required=False, max_length=10)
    damage = discord.ui.TextInput(label="Damage", required=False, max_length=10)
    guard = discord.ui.TextInput(label="Guard", required=False, max_length=100)

    def __init__(self, character_id: int, character_name: str, move_name: str, image_url: str, image_data: str = ""):
        super().__init__()
        self.character_id = character_id
        self.character_name = character_name
        self.move_name = move_name.strip()
        self.image_url = image_url
        self.image_data = image_data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            startup = parse_optional_int(self.startup.value, "Startup")
            active = parse_optional_int(self.active.value, "Active")
            recovery = parse_optional_int(self.recovery.value, "Recovery")
            damage = parse_optional_float(self.damage.value, "Damage")
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        extra_modal = MoveExtraModal(
            character_id=self.character_id,
            character_name=self.character_name,
            move_name=self.move_name,
            image_url=self.image_url,
            image_data=self.image_data,
            startup=startup,
            active=active,
            recovery=recovery,
            damage=damage,
            guard=self.guard.value.strip(),
        )

        view = NextStepView(extra_modal)
        await interaction.response.send_message(
            f"✅ Đã ghi nhận thông số Phần 1 cho chiêu **{self.move_name}**!\n"
            f"Nhấn nút **Nhập tiếp phần 2** bên dưới để điền tiếp Adv. on Hit, Adv. on Block, Invulnerability, Ghi chú...",
            view=view,
            ephemeral=True,
        )


class AddCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    add = app_commands.Group(name="add", description="Thêm dữ liệu vào wiki")

    @add.command(name="character", description="Thêm một nhân vật mới")
    @app_commands.describe(name="Tên nhân vật")
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
        image_data = ""
        if image:
            if not image.content_type or not image.content_type.startswith("image/"):
                await interaction.response.send_message("File đính kèm phải là ảnh.", ephemeral=True)
                return
            image_url = image.url
            try:
                img_bytes = await image.read()
                image_data = base64.b64encode(img_bytes).decode("utf-8")
            except Exception:
                image_data = ""

        await interaction.response.send_modal(
            MoveDetailsModal(character_row["id"], character_row["name"], name, image_url, image_data)
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
