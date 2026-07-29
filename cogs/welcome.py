import discord
from discord.ext import commands

class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Lắng nghe sự kiện: Có người mới tham gia Server
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        
        # ĐIỀN ID KÊNH CHÀO MỪNG CỦA BẠN VÀO ĐÂY
        WELCOME_CHANNEL_ID =  1413537805824557110
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)

        # Nếu kênh không tồn tại (nhập sai ID) thì bỏ qua để không báo lỗi
        if not channel:
            return

        # member.guild.member_count sẽ đếm tổng số thành viên hiện tại (đã bao gồm người vừa vào)
        total_members = member.guild.member_count

        # Tạo một khung Embed chào mừng thật đẹp
        embed = discord.Embed(
            title="Chào mừng gia nhập Tà Giáo",
            description=f"Chào mừng {member.mention} đã gia nhập **{member.guild.name}**!",
            color=discord.Color.green()
        )
        
        # Lấy ảnh đại diện (Avatar) của người mới vào để gắn lên Embed
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        RULES_CHANNEL_ID = 1522601060127080519 
        ROLE_CHANNEL_ID = 1522437793060622487
        MAIN_CHANNEL_ID = 1413539401128218786
        
        embed.add_field(
                    name="📜 Lưu ý", 
                    value=f"""
        Đừng quên đọc luật server tại kênh <#{RULES_CHANNEL_ID}> nhé!
        Nhặt cái role tại <#{ROLE_CHANNEL_ID}> nhé!
        Nhớ chui vào <#{MAIN_CHANNEL_ID}> để giao lưu với mọi người nhé!
                    """,
                    inline=False
                )
        embed.set_footer(text=f"Bạn là thành viên thứ {total_members} của Tà Giáo")

        # Gửi tin nhắn ra kênh chào mừng
        await channel.send(content=f"Chào đằng ấy {member.mention} 👋", embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))