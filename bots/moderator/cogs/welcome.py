import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from database import db
from config import make_embed, COLOR_SUCCESS, COLOR_INFO, COLOR_WARNING

class Welcome(commands.Cog):
    """Module Chào mừng (Welcome), Tạm biệt (Goodbye) & Tự cấp Vai trò (Autorole)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def format_text(self, text: str, member: discord.Member) -> str:
        """Thay thế các placeholder biến động trong văn bản"""
        return text.replace("{user}", member.mention) \
                   .replace("{username}", member.name) \
                   .replace("{server}", member.guild.name) \
                   .replace("{member_count}", str(member.guild.member_count))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        settings = await db.get_guild_settings(member.guild.id)

        # 1. Tự động cấp vai trò (Autorole)
        autorole_id = settings.get("autorole_id")
        if autorole_id:
            role = member.guild.get_role(autorole_id)
            if role and member.guild.me.top_role > role:
                try:
                    await member.add_roles(role, reason="Hệ thống Autorole tự cấp vai trò khi tham gia")
                except discord.HTTPException:
                    pass

        # 2. Gửi lời chào mừng
        welcome_channel_id = settings.get("welcome_channel_id")
        if welcome_channel_id:
            channel = member.guild.get_channel(welcome_channel_id)
            if isinstance(channel, discord.TextChannel):
                raw_msg = settings.get("welcome_message") or "Chào mừng {user} đã đến với **{server}**! Bạn là thành viên thứ #{member_count}."
                formatted_msg = self.format_text(raw_msg, member)

                embed = make_embed(
                    f"🎉 Chào Mừng Đến Với {member.guild.name}!",
                    formatted_msg,
                    COLOR_SUCCESS
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                if member.guild.icon:
                    embed.set_footer(text=f"ID Thành viên: {member.id}", icon_url=member.guild.icon.url)
                
                try:
                    await channel.send(content=member.mention, embed=embed)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return

        settings = await db.get_guild_settings(member.guild.id)
        leave_channel_id = settings.get("leave_channel_id")
        if leave_channel_id:
            channel = member.guild.get_channel(leave_channel_id)
            if isinstance(channel, discord.TextChannel):
                raw_msg = settings.get("leave_message") or "**{username}** vừa rời khỏi máy chủ."
                formatted_msg = self.format_text(raw_msg, member)

                embed = make_embed("👋 Tạm Biệt Thành Viên", formatted_msg, COLOR_WARNING)
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    # --- LỆNH SLASH THIẾT LẬP CHÀO MỪNG ---
    @app_commands.command(name="setwelcome", description="Cài đặt kênh và nội dung tin nhắn chào mừng thành viên mới")
    @app_commands.describe(
        channel="Kênh gửi lời chào (để trống để tắt)",
        message="Nội dung chào mừng. Hỗ trợ: {user}, {username}, {server}, {member_count}"
    )
    @app_commands.default_permissions(administrator=True)
    async def setwelcome(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, message: Optional[str] = None):
        cid = channel.id if channel else None
        await db.update_guild_setting(interaction.guild_id, "welcome_channel_id", cid)
        if message:
            await db.update_guild_setting(interaction.guild_id, "welcome_message", message)

        if channel:
            embed = make_embed(
                "✅ Đã Cập Nhật Kênh Chào Mừng",
                f"Kênh chào mừng: {channel.mention}\n"
                f"**Tin nhắn mẫu:** {message or 'Mặc định'}\n\n"
                "💡 *Gợi ý: Dùng `/testwelcome` để xem thử giao diện chào mừng!*",
                COLOR_SUCCESS
            )
        else:
            embed = make_embed("ℹ️ Đã Tắt Chào Mừng", "Đã tắt hệ thống gửi lời chào mừng thành viên mới.", COLOR_INFO)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setleave", description="Cài đặt kênh và nội dung thông báo khi có thành viên rời server")
    @app_commands.describe(
        channel="Kênh gửi lời tạm biệt (để trống để tắt)",
        message="Nội dung tạm biệt. Hỗ trợ: {user}, {username}, {server}, {member_count}"
    )
    @app_commands.default_permissions(administrator=True)
    async def setleave(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, message: Optional[str] = None):
        cid = channel.id if channel else None
        await db.update_guild_setting(interaction.guild_id, "leave_channel_id", cid)
        if message:
            await db.update_guild_setting(interaction.guild_id, "leave_message", message)

        if channel:
            embed = make_embed(
                "✅ Đã Cập Nhật Kênh Tạm Biệt",
                f"Kênh tạm biệt: {channel.mention}\n**Tin nhắn:** {message or 'Mặc định'}",
                COLOR_SUCCESS
            )
        else:
            embed = make_embed("ℹ️ Đã Tắt Thông Báo Rời Đi", "Đã tắt hệ thống thông báo khi thành viên rời server.", COLOR_INFO)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setautorole", description="Cài đặt vai trò tự động cấp cho thành viên mới khi vừa tham gia")
    @app_commands.describe(role="Vai trò muốn tự cấp (để trống để tắt)")
    @app_commands.default_permissions(administrator=True)
    async def setautorole(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        if role:
            if role >= interaction.guild.me.top_role:
                return await interaction.response.send_message(
                    embed=make_embed("❌ Lỗi Thứ Bậc Vai Trò", f"Bot không thể cấp vai trò {role.mention} vì nó cao hơn hoặc bằng vai trò cao nhất của Bot!", COLOR_WARNING),
                    ephemeral=True
                )
            if role.is_default() or role.managed:
                return await interaction.response.send_message("Không thể dùng vai trò @everyone hoặc vai trò tích hợp ứng dụng!", ephemeral=True)

            await db.update_guild_setting(interaction.guild_id, "autorole_id", role.id)
            embed = make_embed(
                "✅ Đã Kích Hoạt AutoRole",
                f"Thành viên mới khi tham gia sẽ được tự động nhận vai trò {role.mention}.",
                COLOR_SUCCESS
            )
        else:
            await db.update_guild_setting(interaction.guild_id, "autorole_id", None)
            embed = make_embed("ℹ️ Đã Tắt AutoRole", "Đã tắt tính năng tự động cấp vai trò khi tham gia.", COLOR_INFO)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="testwelcome", description="Kiểm tra giao diện thông báo chào mừng")
    @app_commands.default_permissions(administrator=True)
    async def testwelcome(self, interaction: discord.Interaction):
        settings = await db.get_guild_settings(interaction.guild_id)
        raw_msg = settings.get("welcome_message") or "Chào mừng {user} đã đến với **{server}**! Bạn là thành viên thứ #{member_count}."
        formatted = self.format_text(raw_msg, interaction.user)

        embed = make_embed(
            f"🎉 [TEST] Chào Mừng Đến Với {interaction.guild.name}!",
            formatted,
            COLOR_SUCCESS
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if interaction.guild.icon:
            embed.set_footer(text=f"ID Thành viên: {interaction.user.id}", icon_url=interaction.guild.icon.url)

        await interaction.response.send_message(content=f"*(Xem trước giao diện chào mừng)*", embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
