import asyncio
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands


class WelcomeCog(commands.Cog):
    WELCOME_CHANNEL_ID = 1413537805824557110
    RULES_CHANNEL_ID = 1522601060127080519
    ROLE_CHANNEL_ID = 1522437793060622487
    MAIN_CHANNEL_ID = 1413539401128218786

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._has_synced = False

    def build_single_welcome_embed(self, member: discord.Member, total_members: int) -> discord.Embed:
        """Tạo embed chào mừng cho 1 thành viên."""
        embed = discord.Embed(
            title="Chào mừng gia nhập Tà Giáo",
            description=f"Chào mừng {member.mention} đã gia nhập **{member.guild.name}**!",
            color=discord.Color.green()
        )

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        embed.add_field(
            name="📜 Lưu ý",
            value=f"""Đừng quên đọc luật server tại kênh <#{self.RULES_CHANNEL_ID}> nhé!
Nhặt cái role tại <#{self.ROLE_CHANNEL_ID}> nhé!
Nhớ chui vào <#{self.MAIN_CHANNEL_ID}> để giao lưu với mọi người nhé!""",
            inline=False
        )
        embed.set_footer(text=f"Bạn là thành viên thứ {total_members} của Tà Giáo")
        return embed

    def build_batch_welcome_embed(self, members: list[discord.Member], guild: discord.Guild) -> discord.Embed:
        """Tạo embed chào mừng gộp khi có nhiều thành viên mới cùng lúc."""
        mentions = ", ".join(m.mention for m in members)
        embed = discord.Embed(
            title="Chào mừng gia nhập Tà Giáo",
            description=f"Chào mừng các bạn {mentions} đã gia nhập **{guild.name}**!",
            color=discord.Color.green()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="📜 Lưu ý",
            value=f"""Đừng quên đọc luật server tại kênh <#{self.RULES_CHANNEL_ID}> nhé!
Nhặt cái role tại <#{self.ROLE_CHANNEL_ID}> nhé!
Nhớ chui vào <#{self.MAIN_CHANNEL_ID}> để giao lưu với mọi người nhé!""",
            inline=False
        )
        embed.set_footer(text=f"Server hiện có {guild.member_count} thành viên của Tà Giáo")
        return embed

    async def catchup_welcome(self, guild: discord.Guild = None) -> list[discord.Member]:
        """
        Quét kênh chào mừng để tìm tin nhắn chào mừng gần nhất,
        đối chiếu với danh sách thành viên server và chào mừng những người bị sót.
        """
        channel = self.bot.get_channel(self.WELCOME_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.WELCOME_CHANNEL_ID)
            except Exception:
                print(f"[Welcome] Không tìm thấy kênh chào mừng với ID {self.WELCOME_CHANNEL_ID}")
                return []

        target_guild = guild or channel.guild
        if not target_guild:
            return []

        # Tải đầy đủ danh sách member nếu cache chưa đủ
        if not target_guild.chunked:
            try:
                await target_guild.chunk()
            except Exception as e:
                print(f"[Welcome] Không thể chunk guild: {e}")

        # Quét lịch sử 50 tin nhắn gần nhất tìm tin chào mừng gần nhất của bot
        last_welcome_time = None
        welcomed_user_ids = set()

        async for msg in channel.history(limit=50):
            if msg.author == self.bot.user:
                is_welcome_msg = False
                if msg.embeds:
                    for emb in msg.embeds:
                        title = emb.title or ""
                        if "Chào mừng" in title:
                            is_welcome_msg = True
                            break

                if not is_welcome_msg and ("Chào mừng" in msg.content or "Chào đằng ấy" in msg.content):
                    is_welcome_msg = True

                if is_welcome_msg:
                    last_welcome_time = msg.created_at
                    # Ghi nhận các user đã được mention trong tin nhắn này
                    for user in msg.mentions:
                        welcomed_user_ids.add(user.id)
                    break

        # Nếu không tìm thấy tin chào mừng nào trong 50 tin gần nhất,
        # chỉ giới hạn trong vòng 2 ngày gần nhất để tránh spam chào lại cả server
        if not last_welcome_time:
            last_welcome_time = datetime.now(timezone.utc) - timedelta(days=2)

        # Lọc các thành viên vào sau mốc tin nhắn gần nhất
        missing_members: list[discord.Member] = []
        for m in target_guild.members:
            if m.bot:
                continue
            if m.id in welcomed_user_ids:
                continue
            if m.joined_at and m.joined_at > last_welcome_time:
                missing_members.append(m)

        # Sắp xếp theo thứ tự tham gia từ cũ đến mới
        missing_members.sort(key=lambda m: m.joined_at or datetime.min.replace(tzinfo=timezone.utc))

        if not missing_members:
            return []

        # Tiến hành gửi tin chào mừng bù
        if len(missing_members) <= 2:
            # Số lượng ít: gửi từng embed riêng biệt kèm delay nhẹ
            for m in missing_members:
                embed = self.build_single_welcome_embed(m, target_guild.member_count)
                await channel.send(content=f"Chào đằng ấy {m.mention} 👋", embed=embed)
                await asyncio.sleep(1.5)
        else:
            # Số lượng từ 3 người trở lên: gộp thành 1 embed để tránh spam ping / rate limit
            embed = self.build_batch_welcome_embed(missing_members, target_guild)
            mentions_text = " ".join(m.mention for m in missing_members)
            await channel.send(content=f"Chào mừng các bạn mới {mentions_text} 👋", embed=embed)

        return missing_members

    # Sự kiện khi bot online / khởi động lại
    @commands.Cog.listener()
    async def on_ready(self):
        if self._has_synced:
            return
        self._has_synced = True

        print("[Welcome] Đang kiểm tra thành viên mới bỏ sót trong thời gian bot offline...")
        try:
            await self.bot.wait_until_ready()
            # Đợi nhẹ 3 giây để Discord ổn định session và intents
            await asyncio.sleep(3)
            missing = await self.catchup_welcome()
            if missing:
                print(f"[Welcome] Đã chào mừng bù {len(missing)} thành viên mới: {[m.name for m in missing]}")
            else:
                print("[Welcome] Không có thành viên mới nào bị bỏ sót.")
        except Exception as e:
            print(f"[Welcome] Lỗi khi kiểm tra thành viên mới: {e}")

    # Lắng nghe sự kiện: Có người mới tham gia Server trong lúc bot đang chạy
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        channel = self.bot.get_channel(self.WELCOME_CHANNEL_ID)
        if not channel:
            return

        embed = self.build_single_welcome_embed(member, member.guild.member_count)
        await channel.send(content=f"Chào đằng ấy {member.mention} 👋", embed=embed)

    # Slash command cho Quản trị viên kích hoạt quét bù thủ công
    @app_commands.command(
        name="sync_welcome",
        description="Quét và chào mừng các thành viên mới chưa được chào đón"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def slash_sync_welcome(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            missing = await self.catchup_welcome(guild=interaction.guild)
            if missing:
                names = ", ".join(m.display_name for m in missing)
                await interaction.followup.send(
                    f"✅ Đã tìm thấy và gửi chào mừng bù cho **{len(missing)}** thành viên:\n{names}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "ℹ️ Không có thành viên mới nào chưa được chào mừng.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Có lỗi xảy ra trong quá trình quét: `{e}`",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))