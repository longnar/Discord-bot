import io
from datetime import datetime, timedelta
from typing import List, Optional

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


# --- AUTOCOMPLETE ---
async def player_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    db = connect()
    cur = db.cursor()
    if current:
        cur.execute(
            """
            SELECT name FROM players 
            WHERE name LIKE ? 
            ORDER BY elo DESC 
            LIMIT 25
            """,
            (f"%{current}%",),
        )
    else:
        cur.execute(
            """
            SELECT name FROM players 
            ORDER BY elo DESC 
            LIMIT 25
            """
        )
    players = cur.fetchall()
    db.close()
    return [app_commands.Choice(name=row[0], value=row[0]) for row in players]


class EloCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- ELO QUERY / LEADERBOARD ---
    @app_commands.command(name="elo", description="Xem Elo của người chơi hoặc bảng xếp hạng")
    @app_commands.autocomplete(player_name=player_name_autocomplete)
    async def elo(self, interaction: discord.Interaction, player_name: Optional[str] = None):
        db = connect()
        cur = db.cursor()

        if player_name:
            cur.execute(
                "SELECT name, elo, wins, losses FROM players WHERE name=?",
                (player_name,),
            )
            player = cur.fetchone()

            if not player:
                await interaction.response.send_message("❌ Không tìm thấy người chơi.", ephemeral=True)
                db.close()
                return

            name, elo_val, wins, losses = player

            if wins + losses == 0:
                await interaction.response.send_message(f"⚠️ {name} chưa đánh trận nào nên chưa có Elo.", ephemeral=True)
                db.close()
                return

            embed = discord.Embed(title="🏆 ISDVN Player Elo", color=discord.Color.blue())
            embed.add_field(name="Tên", value=name, inline=False)
            embed.add_field(name="💎 Elo", value=str(round(elo_val)), inline=True)
            embed.add_field(name="⚔ W-L", value=f"{wins}W • {losses}L", inline=True)

            await interaction.response.send_message(embed=embed)
            db.close()
            return

        # Leaderboard
        cur.execute(
            """
            SELECT name, elo, wins, losses
            FROM players
            WHERE wins + losses > 0
            ORDER BY elo DESC
            """
        )
        players = cur.fetchall()

        if not players:
            await interaction.response.send_message("Chưa có dữ liệu người chơi.", ephemeral=True)
            db.close()
            return

        embed = discord.Embed(title="🏆 ISDVN Leaderboard", color=discord.Color.gold())
        text = ""

        for i, player in enumerate(players, 1):
            icon = "▫️"
            if i == 1:
                icon = "🥇"
            elif i == 2:
                icon = "🥈"
            elif i == 3:
                icon = "🥉"

            text += f"{icon} **#{i}** {player[0]} • **{round(player[1])}** ({player[2]}W-{player[3]}L)\n"

        embed.description = text
        await interaction.response.send_message(embed=embed)
        db.close()

    # --- PROFILE ---
    @app_commands.command(name="profile", description="Xem thông tin chi tiết của người chơi")
    async def profile(self, interaction: discord.Interaction, player_name: Optional[str] = None):
        if player_name is None:
            player_name = interaction.user.name

        db = connect()
        cur = db.cursor()

        cur.execute(
            """
            SELECT elo, wins, losses, highest_elo, win_streak, best_streak
            FROM players
            WHERE name=?
            """,
            (player_name,),
        )
        player = cur.fetchone()

        if not player:
            await interaction.response.send_message("❌ Không tìm thấy người chơi.", ephemeral=True)
            db.close()
            return

        elo_val, wins, losses, highest, streak, best = player
        total = wins + losses

        if total == 0:
            record = "N/A"
            winrate = "N/A"
            streak_str = "N/A"
            best_str = "N/A"
        else:
            record = f"{wins}W • {losses}L"
            winrate = f"{round(wins / total * 100, 1)}%"
            streak_str = str(streak)
            best_str = str(best)

        embed = discord.Embed(title=f"🏆 ISDVN {player_name}'s Profile", color=discord.Color.blue())
        embed.add_field(name="💎 Elo", value=str(round(elo_val)), inline=True)
        embed.add_field(name="⚔ W-L", value=record, inline=True)
        embed.add_field(name="📈 Tỉ Lệ Thắng", value=winrate, inline=True)
        embed.add_field(name="🏅 Peak Elo", value=str(round(highest)), inline=True)
        embed.add_field(name="🔥 Chuỗi Thắng", value=streak_str, inline=True)
        embed.add_field(name="⭐ Chuỗi Thắng Cao Nhất", value=best_str, inline=True)

        await interaction.response.send_message(embed=embed)
        db.close()

    # --- SETNAME ---
    @app_commands.command(name="setname", description="Đổi tên người chơi")
    async def setname(self, interaction: discord.Interaction, old_name: str, new_name: str):
        db = connect()
        cur = db.cursor()

        cur.execute("SELECT last_name_change FROM players WHERE name=?", (old_name,))
        player = cur.fetchone()

        if not player:
            await interaction.response.send_message("❌ Không tìm thấy người chơi.", ephemeral=True)
            db.close()
            return

        cur.execute("SELECT name FROM players WHERE name=?", (new_name,))
        if cur.fetchone():
            await interaction.response.send_message("❌ Tên này đã tồn tại.", ephemeral=True)
            db.close()
            return

        last_change = player[0]
        if last_change:
            last_date = datetime.strptime(last_change, "%Y-%m-%d")
            next_change = last_date + timedelta(days=30)

            if datetime.now() < next_change:
                remain = (next_change - datetime.now()).days
                await interaction.response.send_message(
                    f"⏳ Bạn phải chờ **{remain} ngày** nữa mới đổi tên được.", ephemeral=True
                )
                db.close()
                return

        now_str = datetime.now().strftime("%Y-%m-%d")
        cur.execute(
            "UPDATE players SET name=?, last_name_change=? WHERE name=?",
            (new_name, now_str, old_name),
        )
        cur.execute("UPDATE matches SET winner=? WHERE winner=?", (new_name, old_name))
        cur.execute("UPDATE matches SET loser=? WHERE loser=?", (new_name, old_name))

        db.commit()
        db.close()

        embed = discord.Embed(title="✏️ Đổi tên thành công", color=discord.Color.green())
        embed.add_field(name="Tên cũ", value=old_name, inline=True)
        embed.add_field(name="Tên mới", value=new_name, inline=True)

        await interaction.response.send_message(embed=embed)

    # --- ELO EDIT ---
    @app_commands.command(name="elo_edit", description="Chỉnh sửa điểm Elo và tỉ lệ thắng/thua của người chơi (Admin)")
    @app_commands.describe(
        player="Tên người chơi",
        elo="Điểm Elo mới (tùy chọn)",
        wins="Số trận thắng mới (tùy chọn)",
        losses="Số trận thua mới (tùy chọn)",
    )
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def elo_edit(
        self,
        interaction: discord.Interaction,
        player: str,
        elo: Optional[int] = None,
        wins: Optional[int] = None,
        losses: Optional[int] = None,
    ):
        if elo is None and wins is None and losses is None:
            await interaction.response.send_message(
                "⚠️ Bạn phải nhập ít nhất 1 thông số cần sửa (elo, wins, hoặc losses).", ephemeral=True
            )
            return

        db = connect()
        cur = db.cursor()
        cur.execute("SELECT elo, wins, losses, highest_elo FROM players WHERE name=?", (player,))
        p = cur.fetchone()

        if not p:
            await interaction.response.send_message(f"❌ Không tìm thấy người chơi **{player}**.", ephemeral=True)
            db.close()
            return

        curr_elo, curr_wins, curr_losses, curr_highest = p
        new_elo = elo if elo is not None else curr_elo
        new_wins = wins if wins is not None else curr_wins
        new_losses = losses if losses is not None else curr_losses
        new_highest = max(curr_highest, new_elo)

        cur.execute(
            """
            UPDATE players
            SET elo=?, wins=?, losses=?, highest_elo=?
            WHERE name=?
            """,
            (new_elo, new_wins, new_losses, new_highest, player),
        )
        db.commit()
        db.close()

        embed = discord.Embed(title="✏️ Cập nhật thông số Elo thành công", color=discord.Color.green())
        embed.add_field(name="Người chơi", value=player, inline=False)
        embed.add_field(name="💎 Elo", value=f"{curr_elo} ➔ **{new_elo}**", inline=True)
        embed.add_field(name="⚔ Wins", value=f"{curr_wins} ➔ **{new_wins}**", inline=True)
        embed.add_field(name="⚔ Losses", value=f"{curr_losses} ➔ **{new_losses}**", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- ELO DELETE ---
    @app_commands.command(name="elo_delete", description="Xóa hồ sơ người chơi khỏi hệ thống Elo (Admin)")
    @app_commands.describe(player="Tên người chơi cần xóa")
    @app_commands.autocomplete(player=player_name_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def elo_delete(self, interaction: discord.Interaction, player: str):
        db = connect()
        cur = db.cursor()
        cur.execute("SELECT name FROM players WHERE name=?", (player,))
        if not cur.fetchone():
            await interaction.response.send_message(f"❌ Không tìm thấy người chơi **{player}**.", ephemeral=True)
            db.close()
            return
        db.close()

        class ConfirmEloDeleteView(discord.ui.View):
            def __init__(self, player_name: str):
                super().__init__(timeout=60)
                self.player_name = player_name

            @discord.ui.button(label="Xác nhận xóa", style=discord.ButtonStyle.danger, emoji="🗑️")
            async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                c = connect()
                c.cursor().execute("DELETE FROM players WHERE name=?", (self.player_name,))
                c.commit()
                c.close()

                for ch in self.children:
                    ch.disabled = True

                emb = discord.Embed(
                    title="🗑️ Đã xóa người chơi",
                    description=f"Đã xóa hồ sơ người chơi **{self.player_name}** khỏi hệ thống Elo.",
                    color=discord.Color.red(),
                )
                await inter.response.edit_message(embed=emb, view=self)

            @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji="❌")
            async def cancel(self, inter: discord.Interaction, btn: discord.ui.Button):
                for ch in self.children:
                    ch.disabled = True
                emb = discord.Embed(
                    title="❌ Đã hủy",
                    description=f"Hồ sơ người chơi **{self.player_name}** vẫn được giữ nguyên.",
                    color=discord.Color.greyple(),
                )
                await inter.response.edit_message(embed=emb, view=self)

        embed = discord.Embed(
            title="⚠️ Xác nhận xóa người chơi",
            description=f"Bạn có chắc chắn muốn xóa người chơi **{player}** khỏi bảng Elo?",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, view=ConfirmEloDeleteView(player), ephemeral=True)


    # --- EXPORT ELO ---
    @app_commands.command(name="export_elo", description="Xuất toàn bộ dữ liệu Elo ra file JSON hoặc CSV để sao lưu")
    @app_commands.describe(file_format="Định dạng file xuất (json hoặc csv)")
    @app_commands.choices(
        file_format=[
            app_commands.Choice(name="JSON (Snapshot 1 file đầy đủ)", value="json"),
            app_commands.Choice(name="CSV (2 file: Players & Matches)", value="csv"),
        ]
    )
    # @app_commands.checks.has_permissions(administrator=True)
    async def export_elo(self, interaction: discord.Interaction, file_format: str = "json"):
        await interaction.response.defer(ephemeral=True)

        conn = connect()
        try:
            if file_format == "json":
                json_str = export_elo_json(conn)
                file_fp = io.BytesIO(json_str.encode("utf-8"))
                filename = f"elo_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                discord_file = discord.File(file_fp, filename=filename)

                embed = discord.Embed(
                    title="📦 Export Elo thành công",
                    description=f"File sao lưu JSON chứa thông tin người chơi và lịch sử trận đấu.",
                    color=discord.Color.green(),
                )
                await interaction.followup.send(embed=embed, file=discord_file, ephemeral=True)

            else:
                players_csv, matches_csv = export_elo_csv(conn)
                file_p = discord.File(
                    io.BytesIO(players_csv.encode("utf-8")),
                    filename=f"elo_players_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                )
                file_m = discord.File(
                    io.BytesIO(matches_csv.encode("utf-8")),
                    filename=f"elo_matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                )

                embed = discord.Embed(
                    title="📦 Export Elo thành công (CSV)",
                    description="Đính kèm file CSV danh sách người chơi và lịch sử trận đấu.",
                    color=discord.Color.green(),
                )
                await interaction.followup.send(embed=embed, files=[file_p, file_m], ephemeral=True)

        finally:
            conn.close()

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
            await interaction.followup.send("❌ Không thể đọc file. File phải ở dạng văn bản mã hóa UTF-8.", ephemeral=True)
            return

        conn = connect()
        try:
            if filename.endswith(".json"):
                result = import_elo_from_json(conn, content, mode=mode)
                embed = discord.Embed(
                    title="✅ Khôi phục Elo thành công (JSON)",
                    description=f"**Chế độ:** `{mode}`\n"
                    f"- Số người chơi đã nạp/cập nhật: **{result['players']}**\n"
                    f"- Số trận đấu đã nạp: **{result['matches']}**",
                    color=discord.Color.green(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif filename.endswith(".csv"):
                result = import_elo_from_csv(conn, content, mode=mode)
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
                await interaction.followup.send("❌ Định dạng file không hợp lệ. Vui lòng đính kèm file `.json` hoặc `.csv`.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Xảy ra lỗi khi nạp file: `{str(e)}`", ephemeral=True)
        finally:
            conn.close()

    # --- PREFIX COMMANDS FOR BACKWARD COMPATIBILITY ---
    @commands.command(name="exportelo")
    @commands.has_permissions(administrator=True)
    async def prefix_exportelo(self, ctx, file_format: str = "json"):
        """Lệnh prefix xuất dữ liệu Elo: !exportelo [json|csv]"""
        conn = connect()
        try:
            if file_format.lower() == "csv":
                players_csv, matches_csv = export_elo_csv(conn)
                file_p = discord.File(
                    io.BytesIO(players_csv.encode("utf-8")),
                    filename=f"elo_players_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                )
                file_m = discord.File(
                    io.BytesIO(matches_csv.encode("utf-8")),
                    filename=f"elo_matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                )
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
        cur = db.cursor()
        cur.execute(
            """
            UPDATE players
            SET elo=1500, wins=0, losses=0, highest_elo=1500, win_streak=0, best_streak=0
            """
        )
        cur.execute("DELETE FROM matches")
        db.commit()
        db.close()

        await ctx.send("🔄 Đã reset toàn bộ dữ liệu Elo về 1500.")


async def setup(bot: commands.Bot):
    await bot.add_cog(EloCog(bot))
