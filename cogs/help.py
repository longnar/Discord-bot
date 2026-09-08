import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog):

  def __init__(self, bot: commands.Bot):
    self.bot = bot

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
            "`/elo [tên]` - Xem điểm Elo cá nhân hoặc Bảng xếp hạng\n"
            "`/profile [tên]` - Xem hồ sơ chi tiết và tỉ lệ thắng người chơi\n"
            "`/setname [tên cũ] [tên mới]` - Đổi tên người chơi"
        ),
        inline=False,
    )

    embed.add_field(
        name="📚 Tra Cứu Wiki & Frame Data",
        value=(
            "`/frame [nhân vật] [chiêu thức]` - Tra cứu Frame Data chi tiết của chiêu thức\n"
            "`/glossary [thuật ngữ]` - Tra cứu định nghĩa thuật ngữ game đối kháng\n"
            "`/add character [tên]` - Thêm nhân vật mới\n"
            "`/add move [nhân vật] [tên chiêu]` - Thêm chiêu thức & frame data"

        ),
        inline=False,
    )

    embed.add_field(
        name="🎉 Giải Trí",
        value=(
            "`/teto` - Gửi GIF Kasane Teto\n"
            "`/migu` - Gửi GIF Migu"
        ),
        inline=False,
    )

    embed.set_footer(
        text="Mẹo: Bạn có thể gõ dấu / để Discord hiện menu gợi ý lệnh!"
    )

    await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
  await bot.add_cog(HelpCog(bot))