import os
import logging
from aiohttp import web
import discord

logger = logging.getLogger("KeepAlive")

async def handle_root(request):
    """Endpoint phản hồi ping giữ bot luôn thức (UptimeRobot)"""
    bot = request.app.get("bot")
    bot_status = "Online" if bot and bot.is_ready() else "Starting/Connecting"
    bot_name = str(bot.user) if bot and bot.user else "NexusGuard"
    guild_count = len(bot.guilds) if bot and bot.is_ready() else 0

    return web.json_response({
        "status": "healthy",
        "bot": bot_name,
        "state": bot_status,
        "servers": guild_count,
        "message": "NexusGuard is awake and protecting servers!"
    }, status=200)

async def handle_health(request):
    """Endpoint kiểm tra sức khỏe ngắn gọn"""
    return web.Response(text="OK", status=200)

async def start_web_server(bot: discord.Client):
    """Khởi động web server bất đồng bộ trên port do Render cấp"""
    if os.getenv("DISABLE_KEEP_ALIVE") or os.getenv("ORCHESTRATOR"):
        logger.info("Internal keepalive server disabled (managed by Multi-Bot Orchestrator).")
        return None

    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server giữ kết nối (Keep-Alive) đang lắng nghe tại cổng {port}")
    print(f"==> Web server listening on port {port} (0.0.0.0:{port})", flush=True)
    return runner
