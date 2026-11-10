import os
from dotenv import load_dotenv
import discord

try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

# Load biến môi trường từ file .env
load_dotenv()

# Discord Bot Token
DISCORD_TOKEN = os.getenv("MODERATOR_TOKEN") or os.getenv("DISCORD_TOKEN", "")

# Prefix cho lệnh legacy
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

# Bot Info
BOT_NAME = os.getenv("BOT_NAME", "NexusGuard")
BOT_VERSION = "2.0.0"

# Màu sắc chuẩn Discord Embed
COLOR_MAIN = 0x5865F2      # Blurple
COLOR_SUCCESS = 0x57F287   # Xanh lá
COLOR_WARNING = 0xFEE75C   # Vàng cảnh báo
COLOR_ERROR = 0xED4245     # Đỏ báo lỗi
COLOR_INFO = 0x3498DB      # Xanh biển
COLOR_MUTED = 0x747F8D     # Xám

# Đường dẫn Database SQLite
DATABASE_PATH = "bot_database.db"

def make_embed(
    title: str = "",
    description: str = "",
    color: int = COLOR_MAIN,
    footer: str = f"{BOT_NAME} • Quản trị hệ thống",
    author: discord.User | discord.Member | None = None
) -> discord.Embed:
    """Hàm tạo Discord Embed chuẩn giao diện"""
    embed = discord.Embed(title=title, description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    if author:
        avatar_url = author.display_avatar.url if author.display_avatar else None
        embed.set_author(name=author.display_name, icon_url=avatar_url)
    return embed
