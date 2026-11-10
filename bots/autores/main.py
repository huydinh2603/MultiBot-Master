import os
import sys
import gc
import signal
import asyncio
import logging
from logging.handlers import RotatingFileHandler

import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from aiohttp import web
from database import DatabaseManager

# ---------------------------------------------------------------------------
# Logging — RotatingFileHandler prevents unbounded log growth on VPS
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            "bot.log",
            encoding="utf-8",
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=3,              # keep 3 rotated copies
        ),
    ],
)
logger = logging.getLogger("DiscordBot.Main")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("AUTORES_TOKEN") or os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
PORT = int(os.getenv("PORT", "8080"))


class CustomCommandsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            max_messages=100,
            chunk_guilds_at_startup=False,
            help_command=commands.DefaultHelpCommand(dm_help=False),
            # Global AllowedMentions — block @everyone/@here/role pings
            # from ALL bot messages. Per-message overrides still work.
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                roles=False,
                users=True,
                replied_user=True,
            ),
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{COMMAND_PREFIX}setup | {COMMAND_PREFIX}addcmd",
            ),
            status=discord.Status.online,
        )
        self.db = DatabaseManager()

    async def setup_hook(self) -> None:
        await self.db.initialize()
        await self.load_extension("cogs.custom_cmds")
        logger.info("Extension cogs.custom_cmds loaded.")

    async def on_ready(self):
        logger.info(
            f"Bot online: {self.user} (ID: {self.user.id}) "
            f"| Guilds: {len(self.guilds)} | Port: {PORT}"
        )
        if not memory_watchdog.is_running():
            memory_watchdog.start()

    async def on_guild_join(self, guild: discord.Guild):
        await self.db.get_guild_settings(guild.id)
        target_channel = guild.system_channel
        if not target_channel or not target_channel.permissions_for(guild.me).send_messages:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break
        if target_channel:
            embed = discord.Embed(
                title=f"👋 Xin Chào {guild.name}! Cảm Ơn Đã Thêm Bot",
                description=(
                    "Hệ thống **Auto-Response & Custom Commands** đã sẵn sàng hoạt động!\n\n"
                    "**⚙️ Cài đặt cơ bản:**\n"
                    f"• Gõ '{COMMAND_PREFIX}setup' : Xem bảng điều khiển cấu hình server.\n"
                    f"• Gõ '{COMMAND_PREFIX}setmode <everyone | role | admin>' : Chọn ai được quyền tạo lệnh.\n"
                    f"• Gõ '{COMMAND_PREFIX}setrole @Role1 [@Role2...]' : Cài đặt một hoặc nhiều vai trò được phép tạo lệnh.\n"
                    f"• Gõ '{COMMAND_PREFIX}addcmd <từ_khóa> <nội_dung>' : Tạo phản hồi tự động đầu tiên.\n\n"
                    f"📖 Gõ '{COMMAND_PREFIX}cmdguide' để mở cuốn cẩm nang hướng dẫn chi tiết!"
                ),
                color=discord.Color.brand_green(),
            )
            embed.set_footer(text="Multi-Tenant SQLite • discord.py 2.x")
            try:
                await target_channel.send(embed=embed)
            except Exception as e:
                logger.warning(f"Cannot send welcome embed: {e}")


@tasks.loop(minutes=15)
async def memory_watchdog():
    """Giải phóng RAM định kỳ để ngăn ngừa tràn bộ nhớ 512MB trên Render."""
    try:
        gc.collect()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Keepalive Web Server — supports GET + HEAD for Render / UptimeRobot
# ---------------------------------------------------------------------------
async def create_keepalive_web_server(bot_instance: CustomCommandsBot) -> web.AppRunner:
    """Create and start the health-check web server. Returns the runner for cleanup."""
    app = web.Application()

    async def handle_health_check(request: web.Request) -> web.Response:
        bot_tag = str(bot_instance.user) if bot_instance.user else "Starting..."
        return web.json_response(
            {
                "status": "healthy",
                "bot": bot_tag,
                "servers_count": len(bot_instance.guilds) if bot_instance.user else 0,
                "message": "Discord Bot running 24/7",
            }
        )

    # Register GET routes on / and /health.
    # Note: aiohttp add_get automatically handles HEAD requests by default,
    # responding with HTTP 200 without a body (adding a separate HEAD route
    # raises RuntimeError: Added route will never be executed).
    for path in ("/", "/health"):
        app.router.add_get(path, handle_health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Keepalive web server listening on 0.0.0.0:{PORT}")
    return runner


# ---------------------------------------------------------------------------
# Main entry-point with graceful shutdown
# ---------------------------------------------------------------------------
async def main():
    if not BOT_TOKEN:
        logger.critical("Missing DISCORD_BOT_TOKEN environment variable!")
        sys.exit(1)

    bot = CustomCommandsBot()
    web_runner: web.AppRunner | None = None

    async def graceful_shutdown() -> None:
        """Cleanup routine triggered by SIGTERM/SIGINT."""
        logger.info("🛑 Shutdown signal received — stopping bot...")
        if memory_watchdog.is_running():
            memory_watchdog.stop()
        if not bot.is_closed():
            await bot.close()

    # Register OS signal handlers (SIGTERM from Render, SIGINT from Ctrl+C)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(graceful_shutdown()),
            )
        except NotImplementedError:
            # Windows does not support add_signal_handler on ProactorEventLoop
            pass

    try:
        async with bot:
            if not os.getenv("DISABLE_KEEP_ALIVE") and not os.getenv("ORCHESTRATOR"):
                web_runner = await create_keepalive_web_server(bot)
            else:
                logger.info("Internal keepalive server disabled (managed by Multi-Bot Orchestrator).")
            await bot.start(BOT_TOKEN)
    finally:
        if web_runner is not None:
            await web_runner.cleanup()
            logger.info("Web server stopped.")
        await bot.db.close()
        logger.info("✅ Cleanup complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped via KeyboardInterrupt.")

