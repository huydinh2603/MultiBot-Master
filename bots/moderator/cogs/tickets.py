import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from typing import Optional

from database import db
from config import make_embed, COLOR_MAIN, COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO

class TicketControlView(discord.ui.View):
    """View điều khiển bên trong kênh Ticket (Nút Đóng Ticket)"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Đóng Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="persistent_close_ticket_button"
    )
    async def close_ticket_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        ticket_data = await db.get_ticket_by_channel(channel.id)
        if not ticket_data:
            return await interaction.response.send_message("❌ Kênh này không phải là kênh Ticket hợp lệ!", ephemeral=True)

        await db.close_ticket(channel.id)
        embed = make_embed(
            "🔒 Đóng Ticket",
            f"Ticket đã được đóng bởi **{interaction.user.mention}**.\nKênh này sẽ tự động bị xóa sau 5 giây...",
            COLOR_ERROR
        )
        await interaction.response.send_message(embed=embed)

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Đóng ticket bởi {interaction.user}")
        except discord.HTTPException:
            pass

class TicketLauncherView(discord.ui.View):
    """View bảng mở Ticket với nút bấm tương tác vĩnh viễn"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Tạo Ticket Hỗ Trợ",
        style=discord.ButtonStyle.primary,
        emoji="📩",
        custom_id="persistent_open_ticket_button"
    )
    async def open_ticket_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            return

        # Kiểm tra xem người dùng đã mở ticket trước đó mà chưa đóng không
        channel_name = f"ticket-{user.name.lower()[:20]}"
        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing:
            return await interaction.response.send_message(
                f"⚠️ Bạn đang có một ticket hỗ trợ chưa đóng tại {existing.mention}! Vui lòng giải quyết ticket cũ trước.",
                ephemeral=True
            )

        settings = await db.get_guild_settings(guild.id)
        category_id = settings.get("ticket_category_id")
        category = guild.get_channel(category_id) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        # Cấu hình quyền truy cập kênh Ticket riêng tư
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        # Cấp quyền xem cho các role Quản trị viên
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket hỗ trợ cho {user} (ID: {user.id})"
            )
        except Exception as e:
            return await interaction.response.send_message(f"❌ Không thể tạo kênh ticket: {e}", ephemeral=True)

        # Lưu vào CSDL
        ticket_id = await db.create_ticket(guild.id, ticket_channel.id, user.id)

        # Gửi lời chào trong kênh ticket mới
        embed = make_embed(
            f"🎫 Yêu Cầu Hỗ Trợ #{ticket_id}",
            f"Xin chào {user.mention}!\n\n"
            "Ban Quản Trị đã nhận được thông báo hỗ trợ của bạn.\n"
            "Vui lòng mô tả chi tiết vấn đề, câu hỏi hoặc đính kèm ảnh minh họa để được xử lý nhanh nhất.\n\n"
            "Khi đã giải quyết xong vấn đề, vui lòng nhấn nút **Đóng Ticket** bên dưới.",
            COLOR_MAIN
        )
        embed.set_footer(text=f"Ticket ID: {ticket_id} • Người tạo: {user.name}")
        await ticket_channel.send(content=f"{user.mention}", embed=embed, view=TicketControlView())

        await interaction.response.send_message(
            f"✅ Ticket của bạn đã được tạo thành công tại {ticket_channel.mention}!",
            ephemeral=True
        )

class Tickets(commands.Cog):
    """Module Quản lý Hệ thống Ticket Hỗ trợ (Support Ticket System)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký các persistent view
        self.bot.add_view(TicketLauncherView())
        self.bot.add_view(TicketControlView())

    @app_commands.command(name="setup_ticket", description="Thiết lập bảng tạo Ticket hỗ trợ cho server")
    @app_commands.describe(
        channel="Kênh đặt bảng tạo ticket",
        category="Danh mục tạo các kênh ticket (tùy chọn)",
        title="Tiêu đề bảng ticket",
        description="Nội dung hướng dẫn mở ticket"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_ticket(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        category: Optional[discord.CategoryChannel] = None,
        title: Optional[str] = "📩 Trung Tâm Hỗ Trợ & Khiếu Nại",
        description: Optional[str] = "Bạn cần liên hệ với Ban Quản Trị, khiếu nại vi phạm, hoặc nhận hỗ trợ?\nNhấn vào nút **Tạo Ticket Hỗ Trợ** bên dưới để tạo kênh trò chuyện riêng tư với đội ngũ Admin/Mod."
    ):
        if category:
            await db.update_guild_setting(interaction.guild_id, "ticket_category_id", category.id)

        embed = make_embed(title, description, COLOR_MAIN)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_footer(text=f"{interaction.guild.name} • Hệ thống Hỗ trợ")

        view = TicketLauncherView()
        await channel.send(embed=embed, view=view)

        category_text = f"trong danh mục **{category.name}**" if category else "(không có danh mục)"
        await interaction.response.send_message(
            embed=make_embed(
                "✅ Đã Thiết Lập Bảng Ticket",
                f"Đã gửi bảng ticket tới {channel.mention} {category_text}.",
                COLOR_SUCCESS
            ),
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
