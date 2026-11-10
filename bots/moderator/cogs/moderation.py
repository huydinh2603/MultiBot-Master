import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
from typing import Optional

from database import db
from config import make_embed, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR, COLOR_INFO

def parse_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """Phân tích chuỗi thời gian (ví dụ: 10s, 30m, 2h, 1d) thành timedelta"""
    match = re.match(r"^(\d+)([smhd])$", duration_str.strip().lower())
    if not match:
        return None
    amount, unit = match.groups()
    amount = int(amount)
    if unit == 's':
        return datetime.timedelta(seconds=amount)
    elif unit == 'm':
        return datetime.timedelta(minutes=amount)
    elif unit == 'h':
        return datetime.timedelta(hours=amount)
    elif unit == 'd':
        return datetime.timedelta(days=amount)
    return None

class Moderation(commands.Cog):
    """Module Quản lý & Xử phạt thành viên (Moderation)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_mod_action(self, guild: discord.Guild, embed: discord.Embed):
        """Gửi log kiểm duyệt tới kênh Mod Log nếu được cài đặt"""
        settings = await db.get_guild_settings(guild.id)
        mod_log_id = settings.get("mod_log_channel_id") or settings.get("log_channel_id")
        if mod_log_id:
            channel = guild.get_channel(mod_log_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    def check_hierarchy(self, actor: discord.Member, target: discord.Member) -> Optional[str]:
        """Kiểm tra thứ bậc vai trò để đảm bảo an toàn"""
        if target.id == actor.guild.owner_id:
            return "Không thể thực hiện hành động lên Chủ sở hữu server!"
        if target.id == actor.id:
            return "Bạn không thể tự phạt chính mình!"
        if actor.id != actor.guild.owner_id and target.top_role >= actor.top_role:
            return f"Bạn không thể xử lý **{target.display_name}** vì vai trò của họ cao hơn hoặc ngang bằng bạn!"
        
        bot_member = actor.guild.me
        if target.top_role >= bot_member.top_role:
            return f"Bot không thể xử lý **{target.display_name}** vì vai trò của họ cao hơn vai trò cao nhất của Bot!"
        return None

    # --- Lệnh KICK ---
    @app_commands.command(name="kick", description="Đuổi thành viên ra khỏi server")
    @app_commands.describe(member="Thành viên cần đuổi", reason="Lý do đuổi")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "Không có lý do cụ thể"):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return

        err = self.check_hierarchy(actor, member)
        if err:
            return await interaction.response.send_message(embed=make_embed("❌ Không Thể Thực Hiện", err, COLOR_ERROR), ephemeral=True)

        try:
            # Gửi tin nhắn DM thông báo lý do
            try:
                dm_embed = make_embed(
                    "⚠️ Bạn Đã Bị Đuổi (Kick)",
                    f"Bạn đã bị đuổi khỏi server **{interaction.guild.name}**.\n**Lý do:** {reason}",
                    COLOR_WARNING
                )
                await member.send(embed=dm_embed)
            except discord.HTTPException:
                pass

            await member.kick(reason=f"{reason} (Bởi {interaction.user})")
            
            embed = make_embed(
                "✅ Đã Đuổi Thành Viên",
                f"Thành viên **{member.mention}** (`{member.id}`) đã bị đuổi khỏi server.\n**Lý do:** {reason}",
                COLOR_SUCCESS,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed)
            await self.log_mod_action(interaction.guild, embed)
        except Exception as e:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", f"Không thể đuổi thành viên: {e}", COLOR_ERROR), ephemeral=True)

    # --- Lệnh BAN ---
    @app_commands.command(name="ban", description="Cấm vĩnh viễn thành viên khỏi server")
    @app_commands.describe(member="Thành viên cần cấm", reason="Lý do cấm", delete_days="Số ngày tin nhắn cần xóa (0 - 7)")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "Không có lý do cụ thể", delete_days: int = 0):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return

        err = self.check_hierarchy(actor, member)
        if err:
            return await interaction.response.send_message(embed=make_embed("❌ Không Thể Thực Hiện", err, COLOR_ERROR), ephemeral=True)

        delete_days = max(0, min(7, delete_days))
        delete_seconds = delete_days * 86400

        try:
            try:
                dm_embed = make_embed(
                    "⛔ Bạn Đã Bị Cấm (Ban)",
                    f"Bạn đã bị cấm khỏi server **{interaction.guild.name}**.\n**Lý do:** {reason}",
                    COLOR_ERROR
                )
                await member.send(embed=dm_embed)
            except discord.HTTPException:
                pass

            await member.ban(reason=f"{reason} (Bởi {interaction.user})", delete_message_seconds=delete_seconds)
            
            embed = make_embed(
                "⛔ Đã Cấm Thành Viên",
                f"Thành viên **{member.mention}** (`{member.id}`) đã bị cấm khỏi server.\n**Lý do:** {reason}\n**Xóa tin nhắn:** {delete_days} ngày",
                COLOR_ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed)
            await self.log_mod_action(interaction.guild, embed)
        except Exception as e:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", f"Không thể cấm thành viên: {e}", COLOR_ERROR), ephemeral=True)

    # --- Lệnh UNBAN ---
    @app_commands.command(name="unban", description="Gỡ cấm thành viên theo ID")
    @app_commands.describe(user_id="ID Discord của người dùng cần gỡ cấm", reason="Lý do gỡ cấm")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = "Gỡ cấm bởi BQT"):
        try:
            uid = int(user_id.strip())
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"{reason} (Bởi {interaction.user})")
            
            embed = make_embed(
                "✅ Đã Gỡ Cấm",
                f"Đã gỡ cấm cho người dùng **{user.name}** (`{user.id}`).\n**Lý do:** {reason}",
                COLOR_SUCCESS,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed)
            await self.log_mod_action(interaction.guild, embed)
        except ValueError:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", "ID người dùng không hợp lệ!", COLOR_ERROR), ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message(embed=make_embed("❌ Không Tìm Thấy", "Người dùng này không có trong danh sách cấm hoặc không tồn tại!", COLOR_WARNING), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", f"Không thể gỡ cấm: {e}", COLOR_ERROR), ephemeral=True)

    # --- Lệnh TIMEOUT (MUTE) ---
    @app_commands.command(name="timeout", description="Cách ly tạm thời (Timeout/Mute) thành viên")
    @app_commands.describe(member="Thành viên cần cách ly", duration="Thời gian (VD: 10m, 1h, 1d, tối đa 28d)", reason="Lý do")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = "Vi phạm quy định"):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return

        err = self.check_hierarchy(actor, member)
        if err:
            return await interaction.response.send_message(embed=make_embed("❌ Không Thể Thực Hiện", err, COLOR_ERROR), ephemeral=True)

        td = parse_duration(duration)
        if not td or td.total_seconds() <= 0 or td.total_seconds() > 28 * 86400:
            return await interaction.response.send_message(
                embed=make_embed("❌ Định Dạng Sai", "Vui lòng nhập định dạng hợp lệ (tối đa 28 ngày): `30s`, `10m`, `2h`, `7d`", COLOR_ERROR),
                ephemeral=True
            )

        try:
            await member.timeout(td, reason=f"{reason} (Bởi {interaction.user})")
            
            try:
                await member.send(embed=make_embed(
                    "⏳ Bạn Đã Bị Cách Ly (Timeout)",
                    f"Bạn đã bị cách ly tại **{interaction.guild.name}** trong `{duration}`.\n**Lý do:** {reason}",
                    COLOR_WARNING
                ))
            except discord.HTTPException:
                pass

            embed = make_embed(
                "⏳ Đã Cách Ly Thành Viên",
                f"Đã đưa **{member.mention}** vào trạng thái cách ly trong `{duration}`.\n**Lý do:** {reason}",
                COLOR_WARNING,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed)
            await self.log_mod_action(interaction.guild, embed)
        except Exception as e:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", f"Không thể timeout: {e}", COLOR_ERROR), ephemeral=True)

    # --- Lệnh UNTIMEOUT ---
    @app_commands.command(name="untimeout", description="Gỡ bỏ cách ly cho thành viên")
    @app_commands.describe(member="Thành viên cần gỡ cách ly", reason="Lý do")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "Gỡ cách ly sớm"):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return

        err = self.check_hierarchy(actor, member)
        if err:
            return await interaction.response.send_message(embed=make_embed("❌ Không Thể Thực Hiện", err, COLOR_ERROR), ephemeral=True)

        try:
            await member.timeout(None, reason=f"{reason} (Bởi {interaction.user})")
            embed = make_embed(
                "✅ Đã Gỡ Cách Ly",
                f"Đã gỡ cách ly cho **{member.mention}**.\n**Lý do:** {reason}",
                COLOR_SUCCESS,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed)
            await self.log_mod_action(interaction.guild, embed)
        except Exception as e:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", f"Không thể gỡ cách ly: {e}", COLOR_ERROR), ephemeral=True)

    # --- Hệ thống CẢNH CÁO (WARN) ---
    @app_commands.command(name="warn", description="Cảnh cáo thành viên vi phạm và lưu vào hồ sơ")
    @app_commands.describe(member="Thành viên bị cảnh cáo", reason="Lý do cảnh cáo")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return

        err = self.check_hierarchy(actor, member)
        if err:
            return await interaction.response.send_message(embed=make_embed("❌ Không Thể Thực Hiện", err, COLOR_ERROR), ephemeral=True)

        warn_id = await db.add_warning(interaction.guild_id, member.id, interaction.user.id, reason)
        warns = await db.get_warnings(interaction.guild_id, member.id)
        warn_count = len(warns)

        # Gửi DM cho user
        try:
            await member.send(embed=make_embed(
                "⚠️ Bạn Nhận Được Cảnh Cáo",
                f"Bạn bị cảnh cáo tại **{interaction.guild.name}**.\n**Lý do:** {reason}\n**Tổng số vi phạm:** {warn_count}",
                COLOR_WARNING
            ))
        except discord.HTTPException:
            pass

        extra_punish = ""
        # Tự động phạt nếu tích luỹ nhiều cảnh cáo:
        # 3 warns -> tự động timeout 1 giờ
        # 5 warns -> tự động kick
        if warn_count == 3:
            try:
                await member.timeout(datetime.timedelta(hours=1), reason="Tự động phạt: Đạt 3 lần cảnh cáo")
                extra_punish = "\n🚨 **Hình phạt bổ sung:** Đã tự động cách ly (Timeout) 1 giờ do đạt 3 lần cảnh cáo!"
            except discord.HTTPException:
                pass
        elif warn_count >= 5:
            try:
                await member.kick(reason="Tự động phạt: Đạt 5 lần cảnh cáo")
                extra_punish = "\n🚨 **Hình phạt bổ sung:** Đã tự động kick khỏi server do đạt 5 lần cảnh cáo!"
            except discord.HTTPException:
                pass

        embed = make_embed(
            "⚠️ Đã Cảnh Cáo Thành Viên",
            f"Đã cảnh cáo **{member.mention}** (Mã vi phạm: `#{warn_id}`).\n**Lý do:** {reason}\n**Tổng số cảnh cáo:** `{warn_count}`{extra_punish}",
            COLOR_WARNING,
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed)
        await self.log_mod_action(interaction.guild, embed)

    @app_commands.command(name="warnings", description="Xem danh sách cảnh cáo của một thành viên")
    @app_commands.describe(member="Thành viên cần kiểm tra")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await db.get_warnings(interaction.guild_id, member.id)
        if not warns:
            return await interaction.response.send_message(
                embed=make_embed("ℹ️ Hồ Sơ Trong Sạch", f"**{member.display_name}** chưa có lần cảnh cáo nào.", COLOR_INFO),
                ephemeral=True
            )

        desc = f"Hồ sơ vi phạm của **{member.mention}** (Tổng cộng: `{len(warns)}` lần):\n\n"
        for idx, w in enumerate(warns[:10], start=1):
            moderator = interaction.guild.get_member(w['moderator_id'])
            mod_name = moderator.display_name if moderator else f"ID: {w['moderator_id']}"
            desc += f"**#{w['id']}** | {w['created_at']}\n• **Lý do:** {w['reason']}\n• **Người phạt:** {mod_name}\n\n"

        if len(warns) > 10:
            desc += f"*Và còn {len(warns) - 10} cảnh cáo khác cũ hơn.*"

        embed = make_embed(f"📋 Danh Sách Cảnh Cáo - {member.display_name}", desc, COLOR_WARNING)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarns", description="Xóa sạch toàn bộ lịch sử cảnh cáo của thành viên")
    @app_commands.describe(member="Thành viên cần xóa cảnh cáo")
    @app_commands.default_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member):
        count = await db.clear_warnings(interaction.guild_id, member.id)
        embed = make_embed(
            "✅ Đã Xóa Lịch Sử Cảnh Cáo",
            f"Đã xóa toàn bộ `{count}` lần cảnh cáo của **{member.mention}**.",
            COLOR_SUCCESS,
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed)
        await self.log_mod_action(interaction.guild, embed)

    # --- Lệnh PURGE / CLEAR TIN NHẮN ---
    @app_commands.command(name="purge", description="Xóa hàng loạt tin nhắn trong kênh chat")
    @app_commands.describe(amount="Số lượng tin nhắn cần xóa (1 - 100)", member="Chỉ xóa tin nhắn của thành viên này (tùy chọn)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int, member: Optional[discord.Member] = None):
        if amount < 1 or amount > 100:
            return await interaction.response.send_message(
                embed=make_embed("❌ Số Lượng Sai", "Số lượng tin nhắn xóa mỗi lần phải từ 1 đến 100!", COLOR_ERROR),
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Lệnh này chỉ dùng được trong kênh văn bản!", ephemeral=True)

        def check_msg(msg: discord.Message):
            if member:
                return msg.author.id == member.id
            return True

        deleted = await channel.purge(limit=amount, check=check_msg)
        filter_str = f" của **{member.mention}**" if member else ""
        embed = make_embed("🧹 Dọn Dẹp Kênh", f"Đã xóa thành công `{len(deleted)}` tin nhắn{filter_str}.", COLOR_SUCCESS)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Lệnh SLOWMODE ---
    @app_commands.command(name="slowmode", description="Đặt thời gian chờ gửi tin nhắn cho kênh")
    @app_commands.describe(seconds="Thời gian chờ (0 để tắt, tối đa 21600s = 6h)", channel="Kênh cần chỉnh (mặc định kênh hiện tại)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            return await interaction.response.send_message("Kênh này không hỗ trợ slowmode!", ephemeral=True)

        if seconds < 0 or seconds > 21600:
            return await interaction.response.send_message(
                embed=make_embed("❌ Giới Hạn Sai", "Thời gian slowmode từ 0 đến 21600 giây (6 tiếng).", COLOR_ERROR),
                ephemeral=True
            )

        await target_channel.edit(slowmode_delay=seconds)
        status = f"đã được đặt là `{seconds}s`" if seconds > 0 else "đã được tắt"
        embed = make_embed("⏱️ Chế Độ Chậm (Slowmode)", f"Slowmode của kênh {target_channel.mention} {status}.", COLOR_INFO)
        await interaction.response.send_message(embed=embed)

    # --- Lệnh LOCK & UNLOCK ---
    @app_commands.command(name="lock", description="Khóa kênh chat ngăn thành viên gửi tin nhắn khẩn cấp")
    @app_commands.describe(channel="Kênh cần khóa (mặc định kênh hiện tại)", reason="Lý do khóa kênh")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, reason: Optional[str] = "Bảo trì / Kiểm duyệt"):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            return await interaction.response.send_message("Kênh này không hợp lệ!", ephemeral=True)

        overwrite = target_channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await target_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Khóa kênh: {reason}")

        embed = make_embed(
            "🔒 Kênh Đã Bị Khóa",
            f"Kênh {target_channel.mention} đã tạm thời bị khóa bởi Ban Quản Trị.\n**Lý do:** {reason}",
            COLOR_ERROR,
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unlock", description="Mở khóa kênh chat")
    @app_commands.describe(channel="Kênh cần mở khóa")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            return await interaction.response.send_message("Kênh này không hợp lệ!", ephemeral=True)

        overwrite = target_channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await target_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason="Mở khóa kênh")

        embed = make_embed(
            "🔓 Kênh Đã Được Mở",
            f"Kênh {target_channel.mention} đã được mở lại cho mọi người nhắn tin.",
            COLOR_SUCCESS,
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed)

    # --- Lệnh NICKNAME ---
    @app_commands.command(name="nick", description="Thay đổi biệt danh của thành viên")
    @app_commands.describe(member="Thành viên cần đổi tên", new_nickname="Biệt danh mới (để trống để xóa biệt danh)")
    @app_commands.default_permissions(manage_nicknames=True)
    async def nick(self, interaction: discord.Interaction, member: discord.Member, new_nickname: Optional[str] = None):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return

        err = self.check_hierarchy(actor, member)
        if err:
            return await interaction.response.send_message(embed=make_embed("❌ Không Thể Thực Hiện", err, COLOR_ERROR), ephemeral=True)

        old_nick = member.display_name
        try:
            await member.edit(nick=new_nickname)
            name_str = f"đã đổi thành `{new_nickname}`" if new_nickname else "đã được khôi phục tên mặc định"
            embed = make_embed("✏️ Đổi Biệt Danh", f"Biệt danh của **{old_nick}** {name_str}.", COLOR_SUCCESS)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(embed=make_embed("❌ Lỗi", f"Không thể đổi biệt danh: {e}", COLOR_ERROR), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
