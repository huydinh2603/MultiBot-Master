import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional

from database import db
from config import make_embed, COLOR_INFO, COLOR_WARNING, COLOR_ERROR, COLOR_SUCCESS

class Logs(commands.Cog):
    """Module Nhật ký Hoạt động (Audit Logging)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Lấy kênh ghi nhật ký hệ thống của server"""
        settings = await db.get_guild_settings(guild.id)
        log_channel_id = settings.get("log_channel_id")
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if isinstance(channel, discord.TextChannel):
                return channel
        return None

    # --- SỰ KIỆN: TIN NHẮN BỊ XÓA ---
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        channel = await self.get_log_channel(message.guild)
        if not channel:
            return

        embed = make_embed(
            "🗑️ Tin Nhắn Bị Xóa",
            f"**Tác giả:** {message.author.mention} (`{message.author.id}`)\n**Kênh:** {message.channel.mention}",
            COLOR_ERROR,
            author=message.author
        )
        content = message.content if message.content else "*[Không có văn bản hoặc chỉ có file/embed]*"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(name="Nội dung đã xóa:", value=content, inline=False)

        if message.attachments:
            att_names = [a.filename for a in message.attachments]
            embed.add_field(name="Tệp đính kèm:", value=", ".join(att_names), inline=False)

        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # --- SỰ KIỆN: TIN NHẮN BỊ CHỈNH SỬA ---
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        channel = await self.get_log_channel(before.guild)
        if not channel:
            return

        embed = make_embed(
            "✏️ Tin Nhắn Đã Chỉnh Sửa",
            f"**Tác giả:** {before.author.mention} (`{before.author.id}`)\n**Kênh:** {before.channel.mention}\n[Nhảy tới tin nhắn]({after.jump_url})",
            COLOR_INFO,
            author=before.author
        )
        b_content = before.content if before.content else "*[Trống]*"
        a_content = after.content if after.content else "*[Trống]*"
        if len(b_content) > 1000:
            b_content = b_content[:997] + "..."
        if len(a_content) > 1000:
            a_content = a_content[:997] + "..."

        embed.add_field(name="Nội dung trước:", value=b_content, inline=False)
        embed.add_field(name="Nội dung sau:", value=a_content, inline=False)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # --- SỰ KIỆN: THÀNH VIÊN MỚI THAM GIA ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = await self.get_log_channel(member.guild)
        if not channel:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        created_at = member.created_at
        account_age = now - created_at

        # Cảnh báo nếu tài khoản mới tạo dưới 3 ngày
        risk_alert = ""
        if account_age.days < 3:
            risk_alert = "\n🚨 **CẢNH BÁO:** Tài khoản này mới tạo dưới 3 ngày (Nguy cơ clone / raid)!"

        embed = make_embed(
            "📥 Thành Viên Tham Gia",
            f"**Người dùng:** {member.mention} (`{member.name}`)\n**ID:** `{member.id}`\n**Ngày tạo Discord:** <t:{int(created_at.timestamp())}:R>{risk_alert}",
            COLOR_SUCCESS,
            author=member
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Tổng thành viên:", value=str(member.guild.member_count), inline=True)
        embed.timestamp = now

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # --- SỰ KIỆN: THÀNH VIÊN RỜI SERVER ---
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = await self.get_log_channel(member.guild)
        if not channel:
            return

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "Không có"

        embed = make_embed(
            "📤 Thành Viên Rời Khỏi",
            f"**Người dùng:** {member.mention} (`{member.name}`)\n**ID:** `{member.id}`\n**Vai trò đã có:** {roles_str}",
            COLOR_ERROR,
            author=member
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Còn lại:", value=str(member.guild.member_count), inline=True)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # --- SỰ KIỆN: CẬP NHẬT THÀNH VIÊN (ROLE, TIMEOUT, BIỆT DANH) ---
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        channel = await self.get_log_channel(before.guild)
        if not channel:
            return

        # 1. Thay đổi biệt danh
        if before.nick != after.nick:
            embed = make_embed(
                "📝 Cập Nhật Biệt Danh",
                f"**Thành viên:** {after.mention}\n**Trước:** `{before.nick or before.name}`\n**Sau:** `{after.nick or after.name}`",
                COLOR_INFO,
                author=after
            )
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

        # 2. Thay đổi vai trò (Roles)
        if before.roles != after.roles:
            added_roles = [r.mention for r in after.roles if r not in before.roles]
            removed_roles = [r.mention for r in before.roles if r not in after.roles]

            if added_roles or removed_roles:
                desc = f"**Thành viên:** {after.mention}\n"
                if added_roles:
                    desc += f"➕ **Được thêm vai trò:** {', '.join(added_roles)}\n"
                if removed_roles:
                    desc += f"➖ **Bị xóa vai trò:** {', '.join(removed_roles)}\n"

                embed = make_embed("🛡️ Cập Nhật Vai Trò", desc, COLOR_INFO, author=after)
                embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

        # 3. Timeout Status
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                embed = make_embed(
                    "⏳ Thành Viên Bị Cách Ly",
                    f"**Thành viên:** {after.mention}\n**Hết hạn:** <t:{int(after.timed_out_until.timestamp())}:R>",
                    COLOR_WARNING,
                    author=after
                )
            else:
                embed = make_embed(
                    "✅ Thành Viên Hết Cách Ly",
                    f"**Thành viên:** {after.mention} đã được gỡ trạng thái cách ly.",
                    COLOR_SUCCESS,
                    author=after
                )
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # --- SỰ KIỆN: TẠO HOẶC XÓA KÊNH ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        log_channel = await self.get_log_channel(channel.guild)
        if not log_channel or channel.id == log_channel.id:
            return

        embed = make_embed(
            "📁 Kênh Mới Được Tạo",
            f"**Tên:** `#{channel.name}`\n**ID:** `{channel.id}`\n**Loại:** `{channel.type}`",
            COLOR_SUCCESS
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        try:
            await log_channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        log_channel = await self.get_log_channel(channel.guild)
        if not log_channel:
            return

        embed = make_embed(
            "🗑️ Kênh Đã Bị Xóa",
            f"**Tên:** `#{channel.name}`\n**ID:** `{channel.id}`\n**Loại:** `{channel.type}`",
            COLOR_ERROR
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        try:
            await log_channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # --- LỆNH SLASH THIẾT LẬP KÊNH NHẬT KÝ ---
    @app_commands.command(name="setlog", description="Thiết lập kênh ghi nhận toàn bộ nhật ký (Audit Log) server")
    @app_commands.describe(channel="Kênh văn bản muốn nhận log (để trống để tắt log)")
    @app_commands.default_permissions(administrator=True)
    async def setlog(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel_id = channel.id if channel else None
        await db.update_guild_setting(interaction.guild_id, "log_channel_id", channel_id)

        if channel:
            embed = make_embed(
                "✅ Đã Cài Đặt Nhật Ký",
                f"Kênh {channel.mention} đã được thiết lập để nhận thông báo nhật ký hoạt động server.",
                COLOR_SUCCESS
            )
        else:
            embed = make_embed(
                "ℹ️ Đã Tắt Nhật Ký",
                "Đã tắt chức năng ghi nhật ký hoạt động server.",
                COLOR_INFO
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setmodlog", description="Thiết lập kênh riêng cho nhật ký phạt (Kick/Ban/Timeout/Warn)")
    @app_commands.describe(channel="Kênh văn bản muốn nhận mod log (để trống để dùng chung với setlog)")
    @app_commands.default_permissions(administrator=True)
    async def setmodlog(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel_id = channel.id if channel else None
        await db.update_guild_setting(interaction.guild_id, "mod_log_channel_id", channel_id)

        if channel:
            embed = make_embed(
                "✅ Đã Cài Đặt Mod Log",
                f"Kênh {channel.mention} đã được thiết lập nhận thông báo xử phạt (Ban/Kick/Timeout/Warn/AutoMod).",
                COLOR_SUCCESS
            )
        else:
            embed = make_embed(
                "ℹ️ Đã Đặt Lại Mod Log",
                "Mod log sẽ được gửi chung vào kênh Audit Log chính nếu có.",
                COLOR_INFO
            )
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
