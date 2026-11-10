import os
import sys
import gc
import logging
import asyncio

try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

import discord
from discord.ext import commands, tasks
from discord import app_commands

from config import DISCORD_TOKEN, COMMAND_PREFIX, BOT_NAME, BOT_VERSION, make_embed, COLOR_ERROR
from database import db
from keep_alive import start_web_server

# Thiết lập hệ thống ghi log trên console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Moderator] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ModeratorBot")

class GuardianBot(commands.Bot):
    def __init__(self):
        # Yêu cầu Intents cần thiết, tối ưu bộ nhớ
        intents = discord.Intents.all()

        super().__init__(
            command_prefix=commands.when_mentioned_or(COMMAND_PREFIX),
            intents=intents,
            max_messages=50,
            chunk_guilds_at_startup=False,
            help_command=None
        )

    async def setup_hook(self):
        """Khởi tạo tài nguyên trước khi bot kết nối Discord Gateway"""
        # 1. Khởi động Web Server (Keep-Alive) nếu không chạy trong Orchestrator
        try:
            await start_web_server(self)
        except Exception as e:
            logger.error(f"Lỗi khi khởi động Web Server: {e}")

        logger.info("Đang khởi tạo cơ sở dữ liệu SQLite...")
        await db.init_db()
        logger.info("Cơ sở dữ liệu đã sẵn sàng!")

        # Tự động nạp toàn bộ các cogs trong thư mục cogs/
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    cog_name = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(cog_name)
                        logger.info(f"Đã nạp module: {cog_name}")
                    except Exception as e:
                        logger.error(f"Lỗi khi nạp module {cog_name}: {e}", exc_info=True)

        # Đồng bộ lệnh Slash Command (/) toàn cầu
        try:
            logger.info("Đang đồng bộ các lệnh Slash Command...")
            synced = await self.tree.sync()
            logger.info(f"Đã đồng bộ thành công {len(synced)} lệnh Slash Command!")
        except Exception as e:
            logger.error(f"Lỗi khi đồng bộ Slash Command: {e}")

    async def on_ready(self):
        """Sự kiện kích hoạt khi bot sẵn sàng nhận lệnh"""
        logger.info("=" * 50)
        logger.info(f" Bot đã đăng nhập thành công với tên: {self.user.name}#{self.user.discriminator}")
        logger.info(f" Bot ID: {self.user.id}")
        logger.info(f" Đang phục vụ {len(self.guilds)} máy chủ với tổng cộng {sum(g.member_count or 0 for g in self.guilds)} thành viên.")
        logger.info(f" Phiên bản Bot: {BOT_VERSION}")
        logger.info("=" * 50)

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"bảo vệ {len(self.guilds)} servers | /help"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

        if not memory_watchdog.is_running():
            memory_watchdog.start()

    async def on_guild_join(self, guild: discord.Guild):
        """Khởi tạo cài đặt mặc định khi được mời vào server mới"""
        logger.info(f"Đã tham gia server mới: {guild.name} (ID: {guild.id})")
        await db.get_guild_settings(guild.id)
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"bảo vệ {len(self.guilds)} servers | /help"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

@tasks.loop(minutes=15)
async def memory_watchdog():
    """Giai phong RAM dinh ky de ngan ngua tran bo nho 512MB tren Render."""
    try:
        gc.collect()
    except Exception:
        pass

# Khởi tạo instance bot
bot = GuardianBot()

# --- XỬ LÝ LỖI TOÀN CỤC CHO SLASH COMMANDS ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        missing = [f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions]
        desc = f"Bạn không có quyền cần thiết để thực hiện lệnh này!\nQuyền còn thiếu: {', '.join(missing)}"
        embed = make_embed("⛔ Thiếu Quyền Truy Cập", desc, COLOR_ERROR)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    elif isinstance(error, app_commands.BotMissingPermissions):
        missing = [f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions]
        desc = f"Bot không có đủ quyền hạn trên server để thực thi lệnh này!\nVui lòng cấp thêm quyền: {', '.join(missing)}"
        embed = make_embed("⚠️ Bot Thiếu Quyền Hạn", desc, COLOR_ERROR)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = make_embed(
            "⏳ Lệnh Đang Trong Thời Gian Chờ",
            f"Vui lòng đợi `{error.retry_after:.1f}` giây trước khi dùng lại lệnh này.",
            COLOR_ERROR
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    else:
        logger.error(f"Lỗi không xử lý được tại lệnh /{interaction.command.name if interaction.command else 'Unknown'}: {error}", exc_info=True)
        embed = make_embed(
            "❌ Có Lỗi Xảy Ra",
            f"Đã xảy ra sự cố kỹ thuật trong quá trình xử lý lệnh: `{str(error)}`",
            COLOR_ERROR
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass

# --- LỆNH QUẢN TRỊ TRỰC TIẾP ĐỒNG BỘ SLASH COMMANDS ---
@bot.command(name="sync")
@commands.is_owner()
async def sync_prefix_command(ctx: commands.Context):
    """Lệnh quản trị để ép buộc đồng bộ lại Slash Commands nếu cần"""
    msg = await ctx.send("Đang đồng bộ các lệnh Slash Command...")
    synced = await bot.tree.sync()
    await msg.edit(content=f"✅ Đã đồng bộ thành công `{len(synced)}` lệnh Slash Command toàn cầu!")

def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_bot_token_here":
        logger.warning("[Moderator] Chưa cấu hình MODERATOR_TOKEN hoặc DISCORD_TOKEN.")
        logger.warning("[Moderator] Bot đang chuyển sang chế độ chờ (standby mode)...")
        import time
        while True:
            time.sleep(3600)

    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("\n[!] LỖI: Token Discord không hợp lệ! Vui lòng kiểm tra lại token trong file .env.\n")
    except Exception as e:
        print(f"\n[!] Lỗi khi chạy bot: {e}\n")

if __name__ == "__main__":
    main()
