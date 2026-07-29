import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog):

  def __init__(self, bot: commands.Bot):
    self.bot = bot

  # Viết lệnh slash /help bình thường bên trong class
  @app_commands.command(
      name="help", description="Xem danh sách toàn bộ lệnh và cách dùng bot"
  )
  async def slash_help(self, interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Hướng Dẫn Sử Dụng Bot",
        description="Dưới đây là danh sách các lệnh Slash `/` đang hoạt động:",
        color=discord.Color.blue(),
    )

    # Thêm các mục giới thiệu lệnh
    embed.add_field(
        name="🏆 Hệ Thống Elo",
        value=(
            "`/elo [tên]` - Xem điểm Elo cá nhân hoặc Bảng xếp hạng"
        ),
        inline=False,
    )

    embed.add_field(
        name="Profile",
        value="`/profile [tên]` - Xem hồ sơ chi tiết và tỉ lệ thắng của người chơi",
        inline=False,
    )

    embed.add_field(
        name="Set name",
        value="`/setname [tên cũ] [tên mới]` - Đổi tên người chơi",
        inline=False,
    )

    embed.set_footer(
        text="Mẹo: Bạn có thể gõ dấu / để Discord hiện menu gợi ý lệnh!"
    )

    await interaction.response.send_message(embed=embed)


# Hàm bắt buộc ở cuối file để discord.py nhận diện đây là 1 Cog
async def setup(bot: commands.Bot):
  await bot.add_cog(HelpCog(bot))