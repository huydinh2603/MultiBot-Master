import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from database import db
from config import make_embed, COLOR_SUCCESS, COLOR_INFO, COLOR_ERROR

class VerificationView(discord.ui.View):
    """View tương tác vĩnh viễn cho nút bấm xác minh thành viên"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Xác Minh / Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="persistent_verification_button"
    )
    async def verify_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return

        settings = await db.get_guild_settings(guild.id)
        role_id = settings.get("verification_role_id")

        if not role_id:
            return await interaction.response.send_message(
                "❌ Hệ thống xác minh chưa được cấu hình vai trò hợp lệ. Vui lòng liên hệ BQT!",
                ephemeral=True
            )

        role = guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message(
                "❌ Không tìm thấy vai trò xác minh trên server. Vui lòng liên hệ BQT!",
                ephemeral=True
            )

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        if role in member.roles:
            return await interaction.response.send_message(
                "ℹ️ Bạn đã hoàn tất xác minh trước đó rồi!",
                ephemeral=True
            )

        try:
            await member.add_roles(role, reason="Hoàn tất xác minh qua nút bấm tương tác")
            await interaction.response.send_message(
                f"🎉 **Chúc mừng!** Bạn đã xác minh thành công và được cấp vai trò **{role.name}**. Bạn có thể truy cập các kênh của server ngay bây giờ!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot thiếu quyền để cấp vai trò này. Hãy đảm bảo vai trò của Bot nằm cao hơn vai trò xác minh!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)

class Verification(commands.Cog):
    """Module Cổng Xác Minh Thành Viên (Member Verification Gate)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký persistent view để nút bấm luôn hoạt động kể cả sau khi bot khởi động lại
        self.bot.add_view(VerificationView())

    @app_commands.command(name="setup_verification", description="Tạo bảng xác minh thành viên với nút bấm nhận vai trò")
    @app_commands.describe(
        channel="Kênh đặt bảng xác minh",
        role="Vai trò sẽ cấp cho người dùng sau khi xác minh",
        title="Tiêu đề bảng xác minh",
        description="Nội dung hướng dẫn xác minh"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_verification(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        title: Optional[str] = "🛡️ Cổng Xác Minh Thành Viên",
        description: Optional[str] = "Chào mừng bạn đến với máy chủ! Vui lòng đọc kỹ nội quy server và nhấn vào nút bên dưới để xác minh và mở khóa toàn bộ các kênh trò chuyện."
    ):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                embed=make_embed("❌ Lỗi Thứ Bậc", f"Vai trò {role.mention} phải thấp hơn vai trò cao nhất của Bot để Bot có thể cấp cho thành viên!", COLOR_ERROR),
                ephemeral=True
            )

        # Lưu role_id vào database
        await db.update_guild_setting(interaction.guild_id, "verification_role_id", role.id)

        # Gửi bảng xác minh kèm nút bấm
        embed = make_embed(title, description, COLOR_SUCCESS)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text=f"{interaction.guild.name} • Bảo mật & Chống Raid")

        view = VerificationView()
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            embed=make_embed(
                "✅ Đã Thiết Lập Bảng Xác Minh",
                f"Đã gửi bảng xác minh tới {channel.mention}.\n**Vai trò xác minh:** {role.mention}",
                COLOR_SUCCESS
            ),
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
