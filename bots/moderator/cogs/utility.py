import discord
from discord import app_commands
from discord.ext import commands
import datetime
import platform
from typing import Optional

from database import db
from config import make_embed, BOT_NAME, BOT_VERSION, COLOR_MAIN, COLOR_INFO

class Utility(commands.Cog):
    """Module Thông tin Máy chủ & Tiện ích Quản trị (Server Info & Utilities)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = datetime.datetime.now(datetime.timezone.utc)

    # --- LỆNH PING ---
    @app_commands.command(name="ping", description="Kiểm tra độ trễ và tốc độ phản hồi của Bot")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000, 2)
        embed = make_embed(
            "🏓 Pong!",
            f"• **WebSocket Latency:** `{latency_ms} ms`\n• **Trạng thái:** Hoạt động ổn định",
            COLOR_INFO
        )
        await interaction.response.send_message(embed=embed)

    # --- LỆNH SERVERINFO ---
    @app_commands.command(name="serverinfo", description="Xem thông tin chi tiết về máy chủ")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return

        total_members = guild.member_count or 0
        bots = len([m for m in guild.members if m.bot])
        humans = total_members - bots

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        roles_count = len(guild.roles)
        emojis_count = len(guild.emojis)

        owner = guild.owner
        owner_str = f"{owner.mention} (`{owner.id}`)" if owner else "Không xác định"

        created_ts = int(guild.created_at.timestamp())

        embed = make_embed(f"📊 Thông Tin Máy Chủ - {guild.name}", "", COLOR_MAIN)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(name="👑 Chủ Sở Hữu", value=owner_str, inline=False)
        embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="📅 Ngày Tạo", value=f"<t:{created_ts}:F>\n(<t:{created_ts}:R>)", inline=True)
        
        embed.add_field(
            name=f"👥 Thành Viên ({total_members})",
            value=f"• Người: `{humans}`\n• Bots: `{bots}`",
            inline=True
        )
        embed.add_field(
            name="💬 Kênh Trò Chuyện",
            value=f"• Văn bản: `{text_channels}`\n• Thoại: `{voice_channels}`\n• Danh mục: `{categories}`",
            inline=True
        )
        embed.add_field(
            name="🚀 Nitro Boost",
            value=f"• Cấp: `{guild.premium_tier}`\n• Số Boost: `{guild.premium_subscription_count}`",
            inline=True
        )
        embed.add_field(
            name="🛡️ Khác",
            value=f"• Vai trò: `{roles_count}`\n• Emoji: `{emojis_count}`\n• Mức xác minh: `{str(guild.verification_level).title()}`",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    # --- LỆNH USERINFO ---
    @app_commands.command(name="userinfo", description="Xem thông tin chi tiết của một thành viên")
    @app_commands.describe(member="Thành viên cần xem (để trống để xem chính mình)")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            return

        warns = await db.get_warnings(interaction.guild_id, target.id)
        created_ts = int(target.created_at.timestamp())
        joined_ts = int(target.joined_at.timestamp()) if target.joined_at else 0

        roles = [r.mention for r in target.roles if r.name != "@everyone"]
        roles.reverse()
        roles_str = ", ".join(roles[:10]) if roles else "Không có"
        if len(roles) > 10:
            roles_str += f" *(và {len(roles) - 10} vai trò khác)*"

        embed = make_embed(f"👤 Hồ Sơ Thành Viên - {target.display_name}", "", COLOR_INFO)
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Tên tài khoản", value=f"{target.name} (`{target.id}`)", inline=True)
        embed.add_field(name="Biệt danh", value=target.nick or "Không có", inline=True)
        embed.add_field(name="Loại tài khoản", value="🤖 Bot" if target.bot else "👤 Người dùng", inline=True)

        embed.add_field(name="📅 Ngày Tạo Tài Khoản", value=f"<t:{created_ts}:D>\n(<t:{created_ts}:R>)", inline=True)
        if joined_ts:
            embed.add_field(name="📥 Ngày Tham Gia Server", value=f"<t:{joined_ts}:D>\n(<t:{joined_ts}:R>)", inline=True)

        embed.add_field(name="⚠️ Lịch Sử Vi Phạm", value=f"`{len(warns)}` lần cảnh cáo", inline=True)
        embed.add_field(name=f"🛡️ Vai Trò ({len(roles)})", value=roles_str, inline=False)
        embed.add_field(name="Vai trò cao nhất", value=target.top_role.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    # --- LỆNH AVATAR ---
    @app_commands.command(name="avatar", description="Xem và tải ảnh đại diện chất lượng cao của thành viên")
    @app_commands.describe(member="Thành viên cần xem avatar")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        avatar_url = target.display_avatar.url
        embed = make_embed(f"🖼️ Ảnh Đại Diện Của {target.display_name}", f"[Nhấn vào đây để tải ảnh gốc]({avatar_url})", COLOR_INFO)
        embed.set_image(url=avatar_url)
        await interaction.response.send_message(embed=embed)

    # --- LỆNH BOTINFO ---
    @app_commands.command(name="botinfo", description="Xem thông số kỹ thuật và tình trạng của Bot")
    async def botinfo(self, interaction: discord.Interaction):
        uptime = datetime.datetime.now(datetime.timezone.utc) - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        guild_count = len(self.bot.guilds)
        user_count = sum(g.member_count or 0 for g in self.bot.guilds)

        embed = make_embed(f"🤖 Giới Thiệu {BOT_NAME}", "Bot quản trị server Discord toàn diện, bảo mật & tự động hóa cao cấp.", COLOR_MAIN)
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="Phiên Bản", value=f"`v{BOT_VERSION}`", inline=True)
        embed.add_field(name="Thời Gian Chạy", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="Độ Trễ (Ping)", value=f"`{round(self.bot.latency * 1000, 1)} ms`", inline=True)

        embed.add_field(name="Máy Chủ Phục Vụ", value=f"`{guild_count}` server", inline=True)
        embed.add_field(name="Tổng Thành Viên Quản Lý", value=f"`{user_count}` người", inline=True)
        embed.add_field(name="Nền Tảng", value=f"Python `{platform.python_version()}`\nDiscord.py `{discord.__version__}`", inline=True)

        embed.add_field(
            name="Tính Năng Cốt Lõi",
            value="• Kiểm duyệt & Xử phạt (Kick, Ban, Timeout, Purge, Lock)\n"
                  "• Hồ sơ vi phạm & Cảnh cáo tự động (Warn System)\n"
                  "• Bảo vệ tự động (Anti-Invite, Anti-Spam, Filter từ cấm, Anti-Mass Mention)\n"
                  "• Nhật ký hoạt động chi tiết (Audit & Mod Logs)\n"
                  "• Chào mừng thành viên & Tự cấp vai trò (Welcome & Autorole)\n"
                  "• Cổng xác minh 1-click (Interactive Verification View)\n"
                  "• Hệ thống Ticket hỗ trợ BQT (Ticket Support System)",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    # --- LỆNH HELP TỔNG QUAN ---
    @app_commands.command(name="help", description="Xem danh sách toàn bộ các lệnh quản trị và hướng dẫn sử dụng")
    async def help(self, interaction: discord.Interaction):
        embed = make_embed(
            f"📚 Bảng Hướng Dẫn Sử Dụng - {BOT_NAME}",
            "Tất cả các lệnh được thiết kế theo tiêu chuẩn Slash Command (`/`). Gõ `/` để thấy gợi ý trực quan từ Discord.",
            COLOR_MAIN
        )

        embed.add_field(
            name="🔨 Kiểm Duyệt & Xử Phạt (Moderation)",
            value="`/kick` - Đuổi thành viên\n"
                  "`/ban` - Cấm thành viên\n"
                  "`/unban` - Gỡ cấm qua ID\n"
                  "`/timeout` & `/untimeout` - Cách ly tạm thời / Mute\n"
                  "`/warn` - Cảnh cáo thành viên (tự động phạt khi đạt 3, 5 lần)\n"
                  "`/warnings` - Xem lịch sử cảnh cáo\n"
                  "`/clearwarns` - Xóa lịch sử cảnh cáo\n"
                  "`/purge` - Xóa nhanh tin nhắn hàng loạt\n"
                  "`/slowmode` - Đặt thời gian chờ kênh chat\n"
                  "`/lock` & `/unlock` - Khóa / mở khóa kênh chat\n"
                  "`/nick` - Đổi biệt danh thành viên",
            inline=False
        )

        embed.add_field(
            name="🛡️ Tự Động Bảo Vệ (AutoMod)",
            value="`/automod status` - Xem trạng thái bảo vệ\n"
                  "`/automod toggle` - Bật/tắt Anti-Invite, Anti-Spam, Anti-Mention\n"
                  "`/automod add_word` - Thêm từ vào danh sách cấm\n"
                  "`/automod remove_word` - Gỡ từ khỏi danh sách cấm\n"
                  "`/automod list_words` - Xem các từ ngữ đang bị chặn",
            inline=False
        )

        embed.add_field(
            name="⚙️ Cài Đặt Hệ Thống (Server Setup)",
            value="`/setlog` - Đặt kênh ghi nhận toàn bộ nhật ký (tin nhắn sửa/xóa, join/leave...)\n"
                  "`/setmodlog` - Đặt kênh ghi nhật ký xử phạt BQT\n"
                  "`/setwelcome` - Đặt kênh và lời chào mừng thành viên mới\n"
                  "`/setleave` - Đặt thông báo thành viên rời server\n"
                  "`/setautorole` - Đặt vai trò tự cấp cho người mới gia nhập\n"
                  "`/setup_verification` - Tạo bảng nút bấm xác minh nhận vai trò\n"
                  "`/setup_ticket` - Tạo bảng nút bấm mở ticket hỗ trợ",
            inline=False
        )

        embed.add_field(
            name="📊 Tiện Ích & Tra Cứu (Utilities)",
            value="`/serverinfo` - Thông tin đầy đủ về server\n"
                  "`/userinfo` - Hồ sơ thành viên và cảnh cáo\n"
                  "`/avatar` - Lấy ảnh đại diện nét cao\n"
                  "`/botinfo` - Thông số kỹ thuật của bot\n"
                  "`/ping` - Kiểm tra tốc độ phản hồi",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
