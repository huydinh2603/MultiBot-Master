import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
import collections
from typing import Dict, List, Optional

from database import db
from config import make_embed, COLOR_WARNING, COLOR_ERROR, COLOR_SUCCESS, COLOR_INFO

# Regex tìm kiếm link mời Discord
DISCORD_INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9\-]+",
    re.IGNORECASE
)

class AutoMod(commands.Cog):
    """Module Tự động Bảo vệ & Giám sát Hệ thống (Auto-Moderation)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Bộ đệm để theo dõi tốc độ gửi tin nhắn (User ID -> List các timestamp)
        self.message_buckets: Dict[int, List[float]] = collections.defaultdict(list)

    async def log_automod_action(self, guild: discord.Guild, embed: discord.Embed):
        """Gửi thông báo vi phạm AutoMod tới kênh Mod Log"""
        settings = await db.get_guild_settings(guild.id)
        mod_log_id = settings.get("mod_log_channel_id") or settings.get("log_channel_id")
        if mod_log_id:
            channel = guild.get_channel(mod_log_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bỏ qua tin nhắn từ Bot, tin nhắn riêng tư (DM), hoặc webhook
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        # Bỏ qua nếu người gửi có quyền Quản lý tin nhắn hoặc Quản trị viên
        if message.author.guild_permissions.manage_messages or message.author.guild_permissions.administrator:
            return

        settings = await db.get_guild_settings(message.guild.id)
        if not settings.get("automod_enabled", 1):
            return

        content = message.content

        # 1. KIỂM TRA LINK MỜI DISCORD (ANTI-INVITE)
        if settings.get("anti_invite", 1):
            if DISCORD_INVITE_REGEX.search(content):
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                embed = make_embed(
                    "🛡️ AutoMod: Chặn Link Mời",
                    f"Người dùng **{message.author.mention}** đã gửi liên kết mời Discord tại {message.channel.mention}.\nTin nhắn đã bị thu hồi.",
                    COLOR_WARNING,
                    author=message.author
                )
                await self.log_automod_action(message.guild, embed)

                # Cảnh báo user
                try:
                    await message.channel.send(
                        f"⚠️ {message.author.mention}, gửi link mời máy chủ khác bị nghiêm cấm tại đây!",
                        delete_after=6
                    )
                except discord.HTTPException:
                    pass
                return

        # 2. KIỂM TRA MASS MENTION (SPAM TAG)
        if settings.get("anti_mass_mention", 1):
            # Nếu tag hơn 4 người hoặc tag @everyone / @here khi không có quyền
            mention_count = len(message.mentions)
            has_everyone = message.mention_everyone

            if mention_count >= 5 or has_everyone:
                try:
                    await message.delete()
                    # Phạt timeout 15 phút
                    await message.author.timeout(datetime.timedelta(minutes=15), reason="AutoMod: Spam Mass Mention")
                except discord.HTTPException:
                    pass

                embed = make_embed(
                    "🛡️ AutoMod: Phát Hiện Spam Mention",
                    f"**{message.author.mention}** đã gửi tin nhắn chứa quá nhiều lượt nhắc tên (`{mention_count}` mentions).\nĐã xóa tin nhắn và tạm khóa chat 15 phút.",
                    COLOR_ERROR,
                    author=message.author
                )
                await self.log_automod_action(message.guild, embed)
                return

        # 3. KIỂM TRA TỪ CẤM (BLACKLIST WORDS)
        bad_words_raw = settings.get("bad_words", "")
        if bad_words_raw:
            bad_words = [w.strip().lower() for w in bad_words_raw.split(",") if w.strip()]
            lowered_content = content.lower()
            for bad_word in bad_words:
                pattern = r"\b" + re.escape(bad_word) + r"\b"
                if re.search(pattern, lowered_content) or bad_word in lowered_content:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass

                    embed = make_embed(
                        "🛡️ AutoMod: Phát Hiện Từ Cấm",
                        f"Tin nhắn của **{message.author.mention}** trong {message.channel.mention} chứa từ ngữ bị cấm (`{bad_word}`).\nTin nhắn đã bị thu hồi.",
                        COLOR_WARNING,
                        author=message.author
                    )
                    await self.log_automod_action(message.guild, embed)
                    try:
                        await message.channel.send(
                            f"⚠️ {message.author.mention}, vui lòng giữ gìn văn hóa ngôn từ và không dùng từ cấm!",
                            delete_after=6
                        )
                    except discord.HTTPException:
                        pass
                    return

        # 4. KIỂM TRA SPAM NHANH (ANTI-SPAM RATE LIMIT)
        if settings.get("anti_spam", 1):
            now = datetime.datetime.now().timestamp()
            user_id = message.author.id
            timestamps = self.message_buckets[user_id]
            # Chỉ giữ các tin nhắn trong vòng 4 giây gần nhất
            self.message_buckets[user_id] = [t for t in timestamps if now - t < 4.0]
            self.message_buckets[user_id].append(now)

            # Nếu gửi hơn 5 tin nhắn trong vòng 4 giây
            if len(self.message_buckets[user_id]) >= 5:
                self.message_buckets[user_id] = []
                try:
                    await message.delete()
                    # Phạt timeout 5 phút vì spam
                    await message.author.timeout(datetime.timedelta(minutes=5), reason="AutoMod: Gửi tin nhắn quá nhanh (Spamming)")
                except discord.HTTPException:
                    pass

                embed = make_embed(
                    "🛡️ AutoMod: Chặn Spam Tốc Độ Cao",
                    f"**{message.author.mention}** đã bị cách ly 5 phút do gửi tin nhắn liên tục quá nhanh.",
                    COLOR_ERROR,
                    author=message.author
                )
                await self.log_automod_action(message.guild, embed)
                try:
                    await message.channel.send(
                        f"🛑 {message.author.mention} đã bị cách ly 5 phút do spam tin nhắn!",
                        delete_after=8
                    )
                except discord.HTTPException:
                    pass
                return

    # --- LỆNH SLASH QUẢN TRỊ AUTOMOD ---
    automod_group = app_commands.Group(name="automod", description="Cài đặt hệ thống bảo vệ tự động AutoMod")

    @automod_group.command(name="status", description="Xem trạng thái cấu hình hiện tại của AutoMod")
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        settings = await db.get_guild_settings(interaction.guild_id)
        
        def status_str(val):
            return "🟢 Đang Bật" if val else "🔴 Đang Tắt"

        embed = make_embed("🛡️ Trạng Thái Cấu Hình AutoMod", "", COLOR_INFO)
        embed.add_field(name="Hệ Thống Tổng", value=status_str(settings.get("automod_enabled", 1)), inline=True)
        embed.add_field(name="Chặn Link Mời (Anti-Invite)", value=status_str(settings.get("anti_invite", 1)), inline=True)
        embed.add_field(name="Chặn Tin Nhắn Spam (Anti-Spam)", value=status_str(settings.get("anti_spam", 1)), inline=True)
        embed.add_field(name="Chống Mass Mention", value=status_str(settings.get("anti_mass_mention", 1)), inline=True)

        bad_words = settings.get("bad_words", "")
        count = len([w for w in bad_words.split(",") if w.strip()]) if bad_words else 0
        embed.add_field(name="Danh Sách Từ Cấm", value=f"`{count}` từ đang bị chặn", inline=True)

        await interaction.response.send_message(embed=embed)

    @automod_group.command(name="toggle", description="Bật/Tắt các tính năng của AutoMod")
    @app_commands.describe(feature="Tính năng muốn bật/tắt", enabled="Bật (True) hoặc Tắt (False)")
    @app_commands.choices(feature=[
        app_commands.Choice(name="Toàn bộ AutoMod (Master Switch)", value="automod_enabled"),
        app_commands.Choice(name="Chặn link mời (Anti-Invite)", value="anti_invite"),
        app_commands.Choice(name="Chặn spam nhanh (Anti-Spam)", value="anti_spam"),
        app_commands.Choice(name="Chặn spam tag (Anti-Mass Mention)", value="anti_mass_mention")
    ])
    @app_commands.default_permissions(administrator=True)
    async def toggle(self, interaction: discord.Interaction, feature: app_commands.Choice[str], enabled: bool):
        val = 1 if enabled else 0
        await db.update_guild_setting(interaction.guild_id, feature.value, val)
        status_text = "bật" if enabled else "tắt"
        embed = make_embed(
            "⚙️ Cập Nhật Cấu Hình",
            f"Tính năng **{feature.name}** đã được **{status_text}** thành công.",
            COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @automod_group.command(name="add_word", description="Thêm từ vào danh sách cấm")
    @app_commands.describe(word="Từ hoặc cụm từ cần cấm")
    @app_commands.default_permissions(administrator=True)
    async def add_word(self, interaction: discord.Interaction, word: str):
        cleaned = word.strip().lower()
        if not cleaned:
            return await interaction.response.send_message("Từ không được để trống!", ephemeral=True)

        settings = await db.get_guild_settings(interaction.guild_id)
        current = settings.get("bad_words", "")
        word_list = [w.strip() for w in current.split(",") if w.strip()]

        if cleaned in word_list:
            return await interaction.response.send_message(f"Từ `{cleaned}` đã có sẵn trong danh sách cấm!", ephemeral=True)

        word_list.append(cleaned)
        new_val = ",".join(word_list)
        await db.update_guild_setting(interaction.guild_id, "bad_words", new_val)

        embed = make_embed("✅ Đã Thêm Từ Cấm", f"Đã thêm từ `{cleaned}` vào danh sách kiểm duyệt tự động.", COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed)

    @automod_group.command(name="remove_word", description="Xóa từ khỏi danh sách cấm")
    @app_commands.describe(word="Từ cần xóa")
    @app_commands.default_permissions(administrator=True)
    async def remove_word(self, interaction: discord.Interaction, word: str):
        cleaned = word.strip().lower()
        settings = await db.get_guild_settings(interaction.guild_id)
        current = settings.get("bad_words", "")
        word_list = [w.strip() for w in current.split(",") if w.strip()]

        if cleaned not in word_list:
            return await interaction.response.send_message(f"Từ `{cleaned}` không nằm trong danh sách cấm!", ephemeral=True)

        word_list.remove(cleaned)
        new_val = ",".join(word_list)
        await db.update_guild_setting(interaction.guild_id, "bad_words", new_val)

        embed = make_embed("✅ Đã Xóa Từ Cấm", f"Đã xóa từ `{cleaned}` khỏi danh sách cấm.", COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed)

    @automod_group.command(name="list_words", description="Xem toàn bộ danh sách từ cấm hiện tại")
    @app_commands.default_permissions(administrator=True)
    async def list_words(self, interaction: discord.Interaction):
        settings = await db.get_guild_settings(interaction.guild_id)
        current = settings.get("bad_words", "")
        word_list = [w.strip() for w in current.split(",") if w.strip()]

        if not word_list:
            return await interaction.response.send_message(
                embed=make_embed("ℹ️ Danh Sách Trống", "Chưa có từ ngữ nào được thêm vào danh sách cấm.", COLOR_INFO),
                ephemeral=True
            )

        words_display = ", ".join(f"`{w}`" for w in word_list)
        embed = make_embed("🚫 Danh Sách Từ Ngữ Bị Cấm", words_display, COLOR_WARNING)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
