import asyncio
import io
import math
import re
from datetime import datetime
from typing import Any, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import connect
from utils.elo_exporter import (
    export_elo_csv,
    export_elo_json,
    import_elo_from_csv,
    import_elo_from_json,
)
from utils.elo_repo import (
    EloRepoError,
    autocomplete_player_names,
    create_player,
    delete_player,
    get_player,
    get_player_recent_matches,
    list_matches,
    list_players,
    record_match,
    rename_player_by_user,
    reset_player,
    undo_match,
    update_player,
)


# --- AUTOCOMPLETE ---
async def player_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    names = await asyncio.to_thread(autocomplete_player_names, current, 25)
    return [app_commands.Choice(name=n, value=n) for n in names]


def _parse_int_pair(raw: str, field_name: str) -> tuple[int, int]:
    parts = [p for p in re.split(r"[-/\s,]+", raw.strip()) if p]
    if len(parts) != 2:
        raise EloRepoError(f"**{field_name}** phải có định dạng `a-b` (ví dụ: `10-4`).")
    try:
        first = int(parts[0])
        second = int(parts[1])
    except ValueError as exc:
        raise EloRepoError(f"**{field_name}** chỉ được chứa số nguyên (ví dụ: `10-4`).") from exc
    if first < 0 or second < 0:
        raise EloRepoError(f"**{field_name}** không được chứa số âm.")
    return first, second


# --- PAGINATION VIEW ---
class PlayerListPaginationView(discord.ui.View):
    def __init__(
        self,
        players: list[dict[str, Any]],
        mode: str = "leaderboard",
        title: str = "🏆 ISDVN Leaderboard",
        author_id: Optional[int] = None,
        per_page: int = 15,
    ):
        super().__init__(timeout=120)
        self.players = players
        self.mode = mode
        self.title = title
        self.author_id = author_id
        self.per_page = per_page
        self.page = 0
        self.total_pages = max(1, math.ceil(len(players) / per_page))
        self.message: Optional[discord.Message] = None
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.first_btn.disabled = self.page <= 0
        self.prev_btn.disabled = self.page <= 0
        self.page_indicator.label = f"Trang {self.page + 1}/{self.total_pages}"
        self.next_btn.disabled = self.page >= self.total_pages - 1
        self.last_btn.disabled = self.page >= self.total_pages - 1

    def build_embed(self) -> discord.Embed:
        start = self.page * self.per_page
        end = start + self.per_page
        chunk = self.players[start:end]

        color = discord.Color.gold() if self.mode == "leaderboard" else discord.Color.blurple()
        embed = discord.Embed(title=self.title, color=color)

        lines: list[str] = []
        for idx, p in enumerate(chunk, start + 1):
            if idx == 1:
                icon = "🥇"
            elif idx == 2:
                icon = "🥈"
            elif idx == 3:
                icon = "🥉"
            else:
                icon = "▫️"

            elo_val = round(p["elo"])
            if self.mode == "leaderboard":
                lines.append(
                    f"{icon} **#{idx}** {p['name']} • **{elo_val}** ({p['wins']}W-{p['losses']}L)"
                )
            else:
                peak_val = round(p["highest_elo"])
                lines.append(
                    f"{icon} **#{idx}** `{p['name']}` • **{elo_val}** (Peak: {peak_val}) | "
                    f"{p['wins']}W-{p['losses']}L | Streak: {p['win_streak']}/{p['best_streak']}"
                )

        embed.description = "\n".join(lines) if lines else "Không có dữ liệu."
        embed.set_footer(
            text=f"Tổng: {len(self.players)} người chơi • Trang {self.page + 1}/{self.total_pages}"
        )
        return embed

    async def _guard_user(self, interaction: discord.Interaction) -> bool:
        if self.author_id is not None and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Chỉ người dùng lệnh mới có thể chuyển trang danh sách này.", ephemeral=True
            )
            return False
        return True

    async def _update_page(self, interaction: discord.Interaction, new_page: int) -> None:
        if not await self._guard_user(interaction):
            return
        self.page = max(0, min(self.total_pages - 1, new_page))
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_page(interaction, 0)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_page(interaction, self.page - 1)

    @discord.ui.button(label="Trang 1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_page(interaction, self.page + 1)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_page(interaction, self.total_pages - 1)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# --- MODAL EDIT PLAYER ---
class EditPlayerModal(discord.ui.Modal, title="Chỉnh sửa thông tin người chơi Elo"):
    new_name = discord.ui.TextInput(
        label="Tên người chơi",
        max_length=50,
        required=True,
    )
    elo_input = discord.ui.TextInput(
        label="Điểm Elo hiện tại",
        max_length=10,
        required=True,
    )
    highest_elo_input = discord.ui.TextInput(
        label="Peak Elo (Cao nhất)",
        max_length=10,
        required=True,
    )
    wl_input = discord.ui.TextInput(
        label="Thắng - Thua (vd: 12-5)",
        placeholder="Nhập dạng wins-losses, ví dụ: 12-5",
        max_length=25,
        required=True,
    )
    streak_input = discord.ui.TextInput(
        label="Chuỗi thắng - Cao nhất (vd: 2-6)",
        placeholder="Nhập dạng streak-best, ví dụ: 2-6",
        max_length=25,
        required=True,
    )

    def __init__(self, player_data: dict[str, Any]):
        super().__init__()
        self.original_name = player_data["name"]
        self.new_name.default = player_data["name"]
        self.elo_input.default = str(round(player_data["elo"]))
        self.highest_elo_input.default = str(round(player_data["highest_elo"]))
        self.wl_input.default = f"{player_data['wins']}-{player_data['losses']}"
        self.streak_input.default = f"{player_data['win_streak']}-{player_data['best_streak']}"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            elo_val = int(self.elo_input.value.strip())
            highest_val = int(self.highest_elo_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ **Điểm Elo** và **Peak Elo** phải là số nguyên.", ephemeral=True
            )
            return

        try:
            wins_val, losses_val = _parse_int_pair(self.wl_input.value, "Thắng - Thua")
            streak_val, best_streak_val = _parse_int_pair(
                self.streak_input.value, "Chuỗi thắng - Cao nhất"
            )
            res = await asyncio.to_thread(
                update_player,
                player_name=self.original_name,
                new_name=self.new_name.value.strip(),
                elo=elo_val,
                wins=wins_val,
                losses=losses_val,
                highest_elo=highest_val,
                win_streak=streak_val,
                best_streak=best_streak_val,
            )
        except EloRepoError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        before = res["before"]
        after = res["after"]
        embed = _build_update_summary_embed(before, after, res["renamed_matches"])
        await interaction.response.send_message(embed=embed, ephemeral=True)


def _build_update_summary_embed(
    before: dict[str, Any], after: dict[str, Any], renamed_matches: int = 0
) -> discord.Embed:
    embed = discord.Embed(title="✏️ Cập nhật hồ sơ Elo thành công", color=discord.Color.green())
    if before["name"] != after["name"]:
        name_text = f"`{before['name']}` ➔ **`{after['name']}`**"
        if renamed_matches:
            name_text += f"\n*(Đã đồng bộ {renamed_matches} trận trong lịch sử)*"
    else:
        name_text = f"**`{after['name']}`**"

    embed.add_field(name="Người chơi", value=name_text, inline=False)
    embed.add_field(
        name="💎 Elo",
        value=f"{round(before['elo'])} ➔ **{round(after['elo'])}**",
        inline=True,
    )
    embed.add_field(
        name="🏅 Peak Elo",
        value=f"{round(before['highest_elo'])} ➔ **{round(after['highest_elo'])}**",
        inline=True,
    )
    embed.add_field(
        name="⚔ W-L",
        value=f"{before['wins']}W-{before['losses']}L ➔ **{after['wins']}W-{after['losses']}L**",
        inline=True,
    )
    embed.add_field(
        name="🔥 Streak / Best",
        value=(
            f"{before['win_streak']}/{before['best_streak']} ➔ "
            f"**{after['win_streak']}/{after['best_streak']}**"
        ),
        inline=True,
    )
    return embed


# --- CONFIRM VIEWS ---
class ConfirmEloDeleteView(discord.ui.View):
    def __init__(self, player_name: str, author_id: int):
        super().__init__(timeout=60)
        self.player_name = player_name
        self.author_id = author_id

    async def _guard(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message(
                "❌ Chỉ quản trị viên thực hiện lệnh mới được xác nhận thao tác này.", ephemeral=True
            )
            return False
        return True

    def _disable_all(self) -> None:
        for ch in self.children:
            ch.disabled = True

    @discord.ui.button(label="Xóa chỉ hồ sơ", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_profile_only(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not await self._guard(inter):
            return
        try:
            res = await asyncio.to_thread(delete_player, self.player_name, False)
        except EloRepoError as e:
            await inter.response.send_message(f"❌ {e}", ephemeral=True)
            return

        self._disable_all()
        emb = discord.Embed(
            title="🗑️ Đã xóa hồ sơ người chơi",
            description=(
                f"Đã xóa **{res['name']}** khỏi bảng Elo.\n"
                f"Lịch sử trận đấu cũ vẫn được giữ nguyên."
            ),
            color=discord.Color.red(),
        )
        await inter.response.edit_message(embed=emb, view=self)

    @discord.ui.button(label="Xóa hồ sơ + Lịch sử đấu", style=discord.ButtonStyle.danger, emoji="🔥")
    async def delete_with_matches(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not await self._guard(inter):
            return
        try:
            res = await asyncio.to_thread(delete_player, self.player_name, True)
        except EloRepoError as e:
            await inter.response.send_message(f"❌ {e}", ephemeral=True)
            return

        self._disable_all()
        emb = discord.Embed(
            title="🔥 Đã xóa hồ sơ & lịch sử đấu",
            description=(
                f"Đã xóa **{res['name']}** khỏi hệ thống Elo và dọn sạch "
                f"**{res['deleted_matches']}** trận đấu liên quan."
            ),
            color=discord.Color.red(),
        )
        await inter.response.edit_message(embed=emb, view=self)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not await self._guard(inter):
            return
        self._disable_all()
        emb = discord.Embed(
            title="❌ Đã hủy",
            description=f"Hồ sơ người chơi **{self.player_name}** vẫn được giữ nguyên.",
            color=discord.Color.greyple(),
        )
        await inter.response.edit_message(embed=emb, view=self)


class ConfirmEloResetView(discord.ui.View):
    def __init__(self, player_name: str, author_id: int):
        super().__init__(timeout=60)
        self.player_name = player_name
        self.author_id = author_id

    async def _guard(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message(
                "❌ Chỉ quản trị viên thực hiện lệnh mới được xác nhận thao tác này.", ephemeral=True
            )
            return False
        return True

    def _disable_all(self) -> None:
        for ch in self.children:
            ch.disabled = True

    @discord.ui.button(label="Xác nhận Reset", style=discord.ButtonStyle.danger, emoji="🔄")
    async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not await self._guard(inter):
            return
        try:
            await asyncio.to_thread(reset_player, self.player_name)
        except EloRepoError as e:
            await inter.response.send_message(f"❌ {e}", ephemeral=True)
            return

        self._disable_all()
        emb = discord.Embed(
            title="🔄 Đã reset chỉ số người chơi",
            description=(
                f"Đã đưa **{self.player_name}** về mặc định: "
                f"Elo `1500`, `0W-0L`, Peak `1500`, Streak `0/0`."
            ),
            color=discord.Color.orange(),
        )
        await inter.response.edit_message(embed=emb, view=self)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not await self._guard(inter):
            return
        self._disable_all()
        emb = discord.Embed(
            title="❌ Đã hủy",
            description=f"Chỉ số của **{self.player_name}** vẫn được giữ nguyên.",
            color=discord.Color.greyple(),
        )
        await inter.response.edit_message(embed=emb, view=self)


# --- ELO COG ---
class EloCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- GROUP QUẢN LÝ CRUD ELO (ADMIN) ---
    elo_manage = app_commands.Group(
        name="elo_manage",
        description="Quản lý CRUD danh sách người chơi & trận đấu Elo (Admin)",
        default_permissions=discord.Permissions(administrator=True),
    )

    # --- ELO QUERY / LEADERBOARD (PUBLIC) ---
    @app_commands.command(name="elo", description="Xem Elo của người chơi hoặc bảng xếp hạng")
    @app_commands.autocomplete(player_name=player_name_autocomplete)
    async def elo(self, interaction: discord.Interaction, player_name: Optional[str] = None):
        if player_name:
            player = await asyncio.to_thread(get_player, player_name)
            if not player:
                await interaction.response.send_message("❌ Không tìm thấy người chơi.", ephemeral=True)
                return

            total = player["wins"] + player["losses"]
            wl_text = (
                f"{player['wins']}W • {player['losses']}L"
                if total > 0
                else "0W • 0L (Chưa đánh trận nào)"
            )
            embed = discord.Embed(title="🏆 ISDVN Player Elo", color=discord.Color.blue())
            embed.add_field(name="Tên", value=player["name"], inline=False)
            embed.add_field(name="💎 Elo", value=str(round(player["elo"])), inline=True)
            embed.add_field(name="⚔ W-L", value=wl_text, inline=True)
            await interaction.response.send_message(embed=embed)
            return

        players = await asyncio.to_thread(list_players, "", "elo", False)
        if not players:
            await interaction.response.send_message("Chưa có dữ liệu người chơi.", ephemeral=True)
            return

        view = PlayerListPaginationView(
            players=players,
            mode="leaderboard",
            title="🏆 ISDVN Leaderboard",
            author_id=None,
            per_page=15,
        )
        embed = view.build_embed()
        if view.total_pages > 1:
            await interaction.response.send_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        else:
            await interaction.response.send_message(embed=embed)

    # --- PROFILE (PUBLIC) ---
    @app_commands.command(name="profile", description="Xem thông tin chi tiết của người chơi")
    @app_commands.autocomplete(player_name=player_name_autocomplete)
    async def profile(self, interaction: discord.Interaction, player_name: Optional[str] = None):
        target_name = player_name if player_name is not None else interaction.user.name
        player = await asyncio.to_thread(get_player, target_name)

        if not player:
            await interaction.response.send_message("❌ Không tìm thấy người chơi.", ephemeral=True)
            return

        total = player["wins"] + player["losses"]
        if total == 0:
            record = "N/A"
            winrate = "N/A"
            streak_str = "N/A"
            best_str = "N/A"
        else:
            record = f"{player['wins']}W • {player['losses']}L"
            winrate = f"{round(player['wins'] / total * 100, 1)}%"
            streak_str = str(player["win_streak"])
            best_str = str(player["best_streak"])

        embed = discord.Embed(title=f"🏆 ISDVN {player['name']}'s Profile", color=discord.Color.blue())
        embed.add_field(name="💎 Elo", value=str(round(player["elo"])), inline=True)
        embed.add_field(name="⚔ W-L", value=record, inline=True)
        embed.add_field(name="📈 Tỉ Lệ Thắng", value=winrate, inline=True)
        embed.add_field(name="🏅 Peak Elo", value=str(round(player["highest_elo"])), inline=True)
        embed.add_field(name="🔥 Chuỗi Thắng", value=streak_str, inline=True)
        embed.add_field(name="⭐ Chuỗi Thắng Cao Nhất", value=best_str, inline=True)

        recent = await asyncio.to_thread(get_player_recent_matches, player["name"], 5)
        if recent:
            recent_lines = []
            for m in recent:
                if m["winner"] == player["name"]:
                    recent_lines.append(f"🟢 Thắng **{m['loser']}** (`+{m['change_elo']}`)")
                else:
                    recent_lines.append(f"🔴 Thua **{m['winner']}** (`-{m['change_elo']}`)")
            embed.add_field(
                name="🕒 5 trận gần nhất",
                value="\n".join(recent_lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # --- SETNAME (PUBLIC) ---
    @app_commands.command(name="setname", description="Đổi tên người chơi")
    @app_commands.autocomplete(old_name=player_name_autocomplete)
    async def setname(self, interaction: discord.Interaction, old_name: str, new_name: str):
        try:
            res = await asyncio.to_thread(rename_player_by_user, old_name, new_name)
        except EloRepoError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        embed = discord.Embed(title="✏️ Đổi tên thành công", color=discord.Color.green())
        embed.add_field(name="Tên cũ", value=res["old_name"], inline=True)
        embed.add_field(name="Tên mới", value=res["new_name"], inline=True)
        await interaction.response.send_message(embed=embed)

    # ==========================================================
    # === CRUD DANH SÁCH ELO (/elo_manage ...) =================
    # ==========================================================

    # --- CREATE ---
    @elo_manage.command(name="add", description="Thêm người chơi mới vào danh sách Elo (Admin)")
    @app_commands.describe(
        name="Tên người chơi",
        elo="Điểm Elo ban đầu (mặc định 1500)",
        wins="Số trận thắng (mặc định 0)",
        losses="Số trận thua (mặc định 0)",
        highest_elo="Peak Elo (để trống sẽ tự lấy theo Elo)",
        win_streak="Chuỗi thắng hiện tại (mặc định 0)",
        best_streak="Chuỗi thắng cao nhất (để trống sẽ lấy theo chuỗi thắng)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_add(
        self,
        interaction: discord.Interaction,
        name: str,
        elo: int = 1500,
        wins: int = 0,
        losses: int = 0,
        highest_elo: Optional[int] = None,
        win_streak: int = 0,
        best_streak: Optional[int] = None,
    ):
        try:
            created = await asyncio.to_thread(
                create_player,
                name=name,
                elo=elo,
                wins=wins,
                losses=losses,
                highest_elo=highest_elo,
                win_streak=win_streak,
                best_streak=best_streak,
            )
        except EloRepoError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        embed = discord.Embed(title="✅ Đã thêm người chơi mới vào Elo", color=discord.Color.green())
        embed.add_field(name="Tên", value=f"**`{created['name']}`**", inline=False)
        embed.add_field(name="💎 Elo", value=str(round(created["elo"])), inline=True)
        embed.add_field(name="🏅 Peak Elo", value=str(round(created["highest_elo"])), inline=True)
        embed.add_field(name="⚔ W-L", value=f"{created['wins']}W-{created['losses']}L", inline=True)
        embed.add_field(
            name="🔥 Streak / Best",
            value=f"{created['win_streak']}/{created['best_streak']}",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- READ (LIST ALL / SEARCH / SORT) ---
    @elo_manage.command(name="list", description="Xem toàn bộ danh sách Elo (gồm cả 0W-0L) với lọc & phân trang")
    @app_commands.describe(
        search="Lọc theo tên người chơi (tùy chọn)",
        sort_by="Tiêu chí sắp xếp",
        include_unranked="Có hiển thị người chơi 0W-0L chưa đấu trận nào không",
    )
    @app_commands.choices(
        sort_by=[
            app_commands.Choice(name="Elo cao nhất", value="elo"),
            app_commands.Choice(name="Tên A-Z", value="name"),
            app_commands.Choice(name="Tổng số trận", value="matches"),
            app_commands.Choice(name="Số trận thắng", value="wins"),
            app_commands.Choice(name="Peak Elo", value="highest_elo"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_list(
        self,
        interaction: discord.Interaction,
        search: str = "",
        sort_by: str = "elo",
        include_unranked: bool = True,
    ):
        players = await asyncio.to_thread(list_players, search, sort_by, include_unranked)
        if not players:
            msg = (
                f"ℹ️ Không tìm thấy người chơi nào khớp từ khóa `{search}`."
                if search.strip()
                else "ℹ️ Danh sách Elo hiện đang trống."
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return

        title = f"📋 Danh sách Elo ({f'Lọc: {search}' if search.strip() else 'Tất cả'})"
        view = PlayerListPaginationView(
            players=players,
            mode="admin",
            title=title,
            author_id=interaction.user.id,
            per_page=15,
        )
        embed = view.build_embed()
        if view.total_pages > 1:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await interaction.original_response()
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- READ (INSPECT RAW DETAILS) ---
    @elo_manage.command(name="inspect", description="Xem toàn bộ dữ liệu thô của 1 người chơi (Admin)")
    @app_commands.describe(player="Tên người chơi")
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_inspect(self, interaction: discord.Interaction, player: str):
        data = await asyncio.to_thread(get_player, player)
        if not data:
            await interaction.response.send_message(f"❌ Không tìm thấy người chơi **{player}**.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🔍 Chi tiết dữ liệu: {data['name']}", color=discord.Color.blurple())
        embed.add_field(name="💎 Elo", value=str(round(data["elo"])), inline=True)
        embed.add_field(name="🏅 Peak Elo", value=str(round(data["highest_elo"])), inline=True)
        embed.add_field(name="⚔ W-L", value=f"{data['wins']}W • {data['losses']}L", inline=True)
        embed.add_field(name="🔥 Win Streak", value=str(data["win_streak"]), inline=True)
        embed.add_field(name="⭐ Best Streak", value=str(data["best_streak"]), inline=True)
        embed.add_field(name="📜 Số bản ghi matches", value=str(data["match_count"]), inline=True)
        embed.add_field(
            name="🕒 Đổi tên gần nhất",
            value=data["last_name_change"] or "Chưa đổi lần nào",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- UPDATE (MODAL OR INLINE PARAMS) ---
    @elo_manage.command(
        name="edit",
        description="Chỉnh sửa thông tin người chơi (bỏ trống các thông số để mở form Modal)",
    )
    @app_commands.describe(
        player="Tên người chơi cần sửa",
        new_name="Đổi sang tên mới (bỏ qua cooldown 30 ngày)",
        elo="Điểm Elo mới",
        wins="Số trận thắng mới",
        losses="Số trận thua mới",
        highest_elo="Peak Elo mới",
        win_streak="Chuỗi thắng hiện tại mới",
        best_streak="Chuỗi thắng cao nhất mới",
        reset_name_cooldown="Xóa thời gian chờ đổi tên 30 ngày",
    )
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_edit(
        self,
        interaction: discord.Interaction,
        player: str,
        new_name: Optional[str] = None,
        elo: Optional[int] = None,
        wins: Optional[int] = None,
        losses: Optional[int] = None,
        highest_elo: Optional[int] = None,
        win_streak: Optional[int] = None,
        best_streak: Optional[int] = None,
        reset_name_cooldown: bool = False,
    ):
        has_inline_params = any(
            v is not None for v in (new_name, elo, wins, losses, highest_elo, win_streak, best_streak)
        ) or reset_name_cooldown

        if not has_inline_params:
            player_data = await asyncio.to_thread(get_player, player)
            if not player_data:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy người chơi **{player}**.", ephemeral=True
                )
                return
            await interaction.response.send_modal(EditPlayerModal(player_data))
            return

        try:
            res = await asyncio.to_thread(
                update_player,
                player_name=player,
                new_name=new_name,
                elo=elo,
                wins=wins,
                losses=losses,
                highest_elo=highest_elo,
                win_streak=win_streak,
                best_streak=best_streak,
                reset_name_cooldown=reset_name_cooldown,
            )
        except EloRepoError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        embed = _build_update_summary_embed(res["before"], res["after"], res["renamed_matches"])
        if reset_name_cooldown:
            embed.set_footer(text="Đã xóa cooldown đổi tên 30 ngày cho người chơi này.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- DELETE ---
    @elo_manage.command(name="delete", description="Xóa người chơi khỏi danh sách Elo (Admin)")
    @app_commands.describe(player="Tên người chơi cần xóa")
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_delete(self, interaction: discord.Interaction, player: str):
        data = await asyncio.to_thread(get_player, player)
        if not data:
            await interaction.response.send_message(
                f"❌ Không tìm thấy người chơi **{player}**.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚠️ Xác nhận xóa người chơi Elo",
            description=(
                f"Bạn có chắc chắn muốn xóa **{data['name']}**?\n\n"
                f"- **Elo hiện tại:** `{round(data['elo'])}` ({data['wins']}W-{data['losses']}L)\n"
                f"- **Số trận liên quan trong bảng `matches`:** `{data['match_count']}` trận"
            ),
            color=discord.Color.gold(),
        )
        view = ConfirmEloDeleteView(data["name"], interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- RESET SINGLE PLAYER ---
    @elo_manage.command(name="reset_player", description="Đưa chỉ số 1 người chơi về mặc định 1500 (Admin)")
    @app_commands.describe(player="Tên người chơi cần reset")
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_reset_player(self, interaction: discord.Interaction, player: str):
        data = await asyncio.to_thread(get_player, player)
        if not data:
            await interaction.response.send_message(
                f"❌ Không tìm thấy người chơi **{player}**.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚠️ Xác nhận reset chỉ số người chơi",
            description=(
                f"Bạn có chắc chắn muốn reset **{data['name']}** "
                f"(hiện tại `{round(data['elo'])}`, {data['wins']}W-{data['losses']}L) "
                f"về mặc định `1500`, `0W-0L`?"
            ),
            color=discord.Color.gold(),
        )
        view = ConfirmEloResetView(data["name"], interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- MATCH CRUD: RECORD MATCH ---
    @elo_manage.command(name="match_add", description="Ghi nhận kết quả 1 trận đấu & tự tính Elo (Admin)")
    @app_commands.describe(
        winner="Người thắng",
        loser="Người thua",
        score="Tỉ số trận đấu (2-0 và 3-0 được nhân hệ số K)",
    )
    @app_commands.choices(
        score=[
            app_commands.Choice(name="2-1 / Thắng thường (x1.0)", value="2-1"),
            app_commands.Choice(name="2-0 (x1.2)", value="2-0"),
            app_commands.Choice(name="3-0 (x1.3)", value="3-0"),
            app_commands.Choice(name="3-1 / 3-2 (x1.0)", value="3-1"),
        ]
    )
    @app_commands.autocomplete(winner=player_name_autocomplete, loser=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_match_add(
        self,
        interaction: discord.Interaction,
        winner: str,
        loser: str,
        score: str = "2-1",
    ):
        try:
            res = await asyncio.to_thread(record_match, winner, loser, score)
        except EloRepoError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"⚔️ Đã ghi nhận trận đấu #{res['match_id']} ({res['score']})",
            color=discord.Color.green(),
        )
        embed.add_field(
            name=f"🏆 Thắng: {res['winner']}",
            value=f"{res['winner_elo_before']} ➔ **{res['winner_elo_after']}** (`+{res['change_elo']}`)",
            inline=True,
        )
        embed.add_field(
            name=f"💀 Thua: {res['loser']}",
            value=f"{res['loser_elo_before']} ➔ **{res['loser_elo_after']}** (`-{res['change_elo']}`)",
            inline=True,
        )
        await interaction.response.send_message(embed=embed)

    # --- MATCH CRUD: LIST MATCHES ---
    @elo_manage.command(name="match_list", description="Xem lịch sử các trận đấu gần nhất kèm ID (Admin)")
    @app_commands.describe(
        player="Lọc theo tên người chơi (tùy chọn)",
        limit="Số trận tối đa hiển thị (mặc định 15, tối đa 25)",
    )
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_match_list(
        self,
        interaction: discord.Interaction,
        player: Optional[str] = None,
        limit: app_commands.Range[int, 1, 25] = 15,
    ):
        matches = await asyncio.to_thread(list_matches, player, limit)
        if not matches:
            await interaction.response.send_message("ℹ️ Chưa có trận đấu nào phù hợp.", ephemeral=True)
            return

        lines = [
            f"`#{m['id']}` **{m['winner']}** thắng **{m['loser']}** (`±{m['change_elo']}` Elo)"
            for m in matches
        ]
        title = f"📜 Lịch sử trận đấu{f' ({player})' if player else ''}"
        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Dùng /elo_manage match_undo [match_id] để hoàn tác trận nhập nhầm.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- MATCH CRUD: UNDO / DELETE MATCH ---
    @elo_manage.command(name="match_undo", description="Hoàn tác 1 trận đấu (mặc định trận gần nhất) (Admin)")
    @app_commands.describe(match_id="ID trận đấu muốn hoàn tác (bỏ trống sẽ hoàn tác trận mới nhất)")
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_match_undo(self, interaction: discord.Interaction, match_id: Optional[int] = None):
        try:
            res = await asyncio.to_thread(undo_match, match_id)
        except EloRepoError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"↩️ Đã hoàn tác trận đấu #{res['match_id']}",
            description=(
                f"Đã xóa trận **{res['winner']}** vs **{res['loser']}** (`±{res['change_elo']}` Elo) "
                f"và hoàn lại điểm Elo + W/L cho cả 2 người chơi."
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(
            text="Lưu ý: Nếu cần chỉnh lại Peak Elo hoặc Best Streak chính xác, hãy dùng /elo_manage edit."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- EXPORT ELO ---
    @app_commands.command(name="export_elo", description="Xuất toàn bộ dữ liệu Elo ra file JSON hoặc CSV để sao lưu")
    @app_commands.describe(file_format="Định dạng file xuất (json hoặc csv)")
    @app_commands.choices(
        file_format=[
            app_commands.Choice(name="JSON (Snapshot 1 file đầy đủ)", value="json"),
            app_commands.Choice(name="CSV (2 file: Players & Matches)", value="csv"),
        ]
    )
    async def export_elo(self, interaction: discord.Interaction, file_format: str = "json"):
        await interaction.response.defer(ephemeral=True)

        def _do_export():
            conn = connect()
            try:
                if file_format == "json":
                    return ("json", export_elo_json(conn), None)
                players_csv, matches_csv = export_elo_csv(conn)
                return ("csv", players_csv, matches_csv)
            finally:
                conn.close()

        fmt, data1, data2 = await asyncio.to_thread(_do_export)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if fmt == "json":
            file_fp = io.BytesIO(data1.encode("utf-8"))
            discord_file = discord.File(file_fp, filename=f"elo_backup_{ts}.json")
            embed = discord.Embed(
                title="📦 Export Elo thành công",
                description="File sao lưu JSON chứa thông tin người chơi và lịch sử trận đấu.",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed, file=discord_file, ephemeral=True)
        else:
            file_p = discord.File(io.BytesIO(data1.encode("utf-8")), filename=f"elo_players_{ts}.csv")
            file_m = discord.File(io.BytesIO(data2.encode("utf-8")), filename=f"elo_matches_{ts}.csv")
            embed = discord.Embed(
                title="📦 Export Elo thành công (CSV)",
                description="Đính kèm file CSV danh sách người chơi và lịch sử trận đấu.",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed, files=[file_p, file_m], ephemeral=True)

    # --- RESTORE / IMPORT ELO ---
    @app_commands.command(name="restore_elo", description="Khôi phục hoặc nạp dữ liệu Elo từ file JSON/CSV sao lưu")
    @app_commands.describe(
        file="File đính kèm (.json hoặc .csv)",
        mode="Chế độ nhập: 'upsert' (Cập nhật/Ghi đè người chơi) hoặc 'overwrite' (Xóa hết dữ liệu cũ và nạp lại)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Upsert (Ghi đè/Cập nhật người chơi trùng tên)", value="upsert"),
            app_commands.Choice(name="Overwrite (Xóa toàn bộ database cũ trước khi nạp)", value="overwrite"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def restore_elo(
        self, interaction: discord.Interaction, file: discord.Attachment, mode: str = "upsert"
    ):
        await interaction.response.defer(ephemeral=True)

        filename = file.filename.lower()
        file_bytes = await file.read()

        try:
            content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            await interaction.followup.send(
                "❌ Không thể đọc file. File phải ở dạng văn bản mã hóa UTF-8.", ephemeral=True
            )
            return

        def _do_import():
            conn = connect()
            try:
                if filename.endswith(".json"):
                    return ("json", import_elo_from_json(conn, content, mode=mode))
                if filename.endswith(".csv"):
                    return ("csv", import_elo_from_csv(conn, content, mode=mode))
                return ("invalid", None)
            finally:
                conn.close()

        try:
            kind, result = await asyncio.to_thread(_do_import)
            if kind == "json":
                embed = discord.Embed(
                    title="✅ Khôi phục Elo thành công (JSON)",
                    description=(
                        f"**Chế độ:** `{mode}`\n"
                        f"- Số người chơi đã nạp/cập nhật: **{result['players']}**\n"
                        f"- Số trận đấu đã nạp: **{result['matches']}**"
                    ),
                    color=discord.Color.green(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            elif kind == "csv":
                if result["status"] == "success":
                    embed = discord.Embed(
                        title="✅ Khôi phục/Import CSV thành công",
                        description=f"**Chế độ:** `{mode}`\n{result['message']}",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ {result['message']}", ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ Định dạng file không hợp lệ. Vui lòng đính kèm file `.json` hoặc `.csv`.",
                    ephemeral=True,
                )
        except Exception as e:
            await interaction.followup.send(f"❌ Xảy ra lỗi khi nạp file: `{str(e)}`", ephemeral=True)

    # --- PREFIX COMMANDS FOR BACKWARD COMPATIBILITY ---
    @commands.command(name="exportelo")
    @commands.has_permissions(administrator=True)
    async def prefix_exportelo(self, ctx, file_format: str = "json"):
        """Lệnh prefix xuất dữ liệu Elo: !exportelo [json|csv]"""
        conn = connect()
        try:
            if file_format.lower() == "csv":
                players_csv, matches_csv = export_elo_csv(conn)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_p = discord.File(io.BytesIO(players_csv.encode("utf-8")), filename=f"elo_players_{ts}.csv")
                file_m = discord.File(io.BytesIO(matches_csv.encode("utf-8")), filename=f"elo_matches_{ts}.csv")
                await ctx.send("📦 **Dữ liệu Elo Export (CSV):**", files=[file_p, file_m])
            else:
                json_str = export_elo_json(conn)
                file_fp = io.BytesIO(json_str.encode("utf-8"))
                filename = f"elo_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                discord_file = discord.File(file_fp, filename=filename)
                await ctx.send("📦 **Dữ liệu Elo Snapshot (JSON):**", file=discord_file)
        finally:
            conn.close()

    @commands.command(name="importelo")
    @commands.has_permissions(administrator=True)
    async def prefix_importelo(self, ctx):
        """Lệnh prefix import file CSV (hỗ trợ cả CSV trận đấu lẫn CSV snapshot Elo)."""
        if not ctx.message.attachments:
            await ctx.send("❌ Bạn chưa gửi file CSV kèm theo lệnh.")
            return

        file = ctx.message.attachments[0]
        file_bytes = await file.read()
        csv_text = file_bytes.decode("utf-8")

        conn = connect()
        try:
            result = import_elo_from_csv(conn, csv_text, mode="upsert")
            if result["status"] == "success":
                await ctx.send(f"✅ {result['message']}")
            else:
                await ctx.send(f"❌ {result['message']}")
        finally:
            conn.close()

    @commands.command(name="resetelo")
    @commands.has_permissions(administrator=True)
    async def prefix_resetelo(self, ctx):
        """Lệnh reset toàn bộ Elo."""
        db = connect()
        try:
            cur = db.cursor()
            cur.execute(
                """
                UPDATE players
                SET elo=1500, wins=0, losses=0, highest_elo=1500, win_streak=0, best_streak=0
                """
            )
            cur.execute("DELETE FROM matches")
            db.commit()
        finally:
            db.close()

        await ctx.send("🔄 Đã reset toàn bộ dữ liệu Elo về 1500.")

    # --- APP COMMAND ERROR HANDLER ---
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Bạn cần quyền **Administrator** để sử dụng lệnh này."
        elif isinstance(error, app_commands.CheckFailure):
            msg = "❌ Bạn không đủ quyền để thực hiện thao tác này."
        else:
            msg = f"❌ Đã xảy ra lỗi: `{error}`"

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EloCog(bot))
