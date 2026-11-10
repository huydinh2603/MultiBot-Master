import os
import sys
import gc
import asyncio
import logging
from dotenv import load_dotenv

try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

import discord
from discord.ext import commands, tasks

from keep_alive import start_keep_alive

# Load bien moi truong tu file .env neu co
load_dotenv()

TOKEN = os.getenv("VOICEGUARD_TOKEN") or os.getenv("VOICE_GUARD_TOKEN") or os.getenv("DISCORD_TOKEN")
VOICE_CHANNEL_ID = os.getenv("VOICEGUARD_CHANNEL_ID") or os.getenv("VOICE_CHANNEL_ID")

# Cau hinh logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [VoiceGuard] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Thiet lap Intents
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.message_content = True

# Gioi han RAM de tranh bi Render kill voi Exit Status 134 (cgroup 512MB limit)
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    max_messages=50,
    chunk_guilds_at_startup=False,
)

# Bien luu ID channel can giu 24/7
target_channel_id = int(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID and str(VOICE_CHANNEL_ID).isdigit() else None


def is_bot_in_target_channel(guild: discord.Guild, target_id: int) -> bool:
    """Kiem tra xem bot co thuc su dang o trong phong voice muc tieu hay khong dua theo VoiceState cua Discord."""
    if not guild or not guild.me or not guild.me.voice:
        return False
    return guild.me.voice.channel is not None and guild.me.voice.channel.id == target_id


async def connect_to_voice(channel: discord.VoiceChannel):
    """Ket noi hoac di chuyen bot den Voice Channel muc tieu."""
    guild = channel.guild

    try:
        # 1. Neu bot da o dung phong voice muc tieu roi, TUYET DOI KHONG disconnect
        if is_bot_in_target_channel(guild, channel.id):
            return

        # 2. Neu bot dang o mot phong voice khac trong server (vi du bi keo sang phong khac hoac AFK)
        if guild.me.voice and guild.me.voice.channel:
            if guild.me.voice.channel.id != channel.id:
                logging.info(f"Bot dang o phong '{guild.me.voice.channel.name}', dang chuyen ve phong '{channel.name}'...")
                if guild.voice_client:
                    await guild.voice_client.move_to(channel)
                else:
                    await guild.me.move_to(channel)
                return

        # 3. Neu bot chua o trong bat ky phong voice nao (guild.me.voice is None)
        # Neu co voice_client treo cu (zombie) thi don dep
        if guild.voice_client is not None:
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(1)

        logging.info(f"Dang ket noi vao voice room: {channel.name} (ID: {channel.id})...")
        await channel.connect(reconnect=True, self_deaf=True)
        logging.info(f"Da ket noi thanh cong vao: {channel.name}")

    except Exception as e:
        logging.error(f"Loi khi ket noi vao voice room: {e}")


@tasks.loop(seconds=60)
async def voice_watchdog():
    """Tac vu kiem tra moi 60 giay: Chi ket noi lai neu bot THUC SU khong o trong phong."""
    global target_channel_id

    # Don dep bo nho dinh ky giup giai phong RAM tren Render Free Tier 512MB
    try:
        gc.collect()
    except Exception:
        pass

    if not target_channel_id:
        return

    channel = bot.get_channel(target_channel_id)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        try:
            channel = await bot.fetch_channel(target_channel_id)
        except Exception:
            return

    if channel and isinstance(channel, discord.VoiceChannel):
        guild = channel.guild

        # Neu bot DA O DUNG PHONG, hoan toan khong lam gi ca (giu nguyen)
        if is_bot_in_target_channel(guild, channel.id):
            return

        logging.warning(f"Watchdog phat hien bot khong o trong phong '{channel.name}'. Tien hanh ket noi...")
        await connect_to_voice(channel)


@bot.event
async def on_ready():
    logging.info(f"Bot da online voi ten: {bot.user} (ID: {bot.user.id})")

    # Dong bo slash commands
    try:
        synced = await bot.tree.sync()
        logging.info(f"Da dong bo {len(synced)} lenh slash.")
    except Exception as e:
        logging.error(f"Khong the dong bo slash command: {e}")

    # Tu dong vao phong voice neu da cau hinh VOICE_CHANNEL_ID
    if target_channel_id:
        channel = bot.get_channel(target_channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(target_channel_id)
            except Exception as e:
                logging.error(f"Khong the tim thay Voice Channel ID {target_channel_id}: {e}")
                channel = None

        if channel and isinstance(channel, discord.VoiceChannel):
            await connect_to_voice(channel)
        else:
            logging.warning(f"ID {target_channel_id} khong phai la Voice Channel hop le!")

    # Khoi dong watchdog
    if not voice_watchdog.is_running():
        voice_watchdog.start()


@bot.event
async def on_voice_state_update(member, before, after):
    """Xu ly khi co su kien thay doi voice cua chinh bot."""
    global target_channel_id
    if member.id == bot.user.id and target_channel_id:
        logging.info(f"[VoiceState] Bot voice state thay doi: '{before.channel}' -> '{after.channel}'")

        # Truong hop 1: Bot bi ngat ket noi (after.channel is None)
        if after.channel is None:
            logging.warning("Bot bi ngat ket noi khoi voice room. Se kiem tra va ket noi lai sau 5 giay...")
            await asyncio.sleep(5)
            channel = bot.get_channel(target_channel_id)
            if channel and isinstance(channel, discord.VoiceChannel):
                if not is_bot_in_target_channel(channel.guild, target_channel_id):
                    await connect_to_voice(channel)

        # Truong hop 2: Bot bi ai do keo hoac he thong chuyen sang phong khac (vi du kenh AFK)
        elif after.channel.id != target_channel_id:
            logging.warning(f"Bot bi chuyen sang '{after.channel.name}'. Se chuyen lai phong chinh sau 3 giay...")
            await asyncio.sleep(3)
            channel = bot.get_channel(target_channel_id)
            if channel and isinstance(channel, discord.VoiceChannel):
                await connect_to_voice(channel)


# --- SLASH COMMANDS ---

@bot.tree.command(name="join", description="Yeu cau bot vao mot Voice Room va giu phong 24/7.")
@discord.app_commands.describe(channel="Voice room muon bot tham gia (de trong neu muon bot vao phong ban dang ngoi)")
async def join_command(interaction: discord.Interaction, channel: discord.VoiceChannel = None):
    global target_channel_id

    # Neu khong truyen channel, lay phong cua nguoi goi lenh
    if channel is None:
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
        else:
            await interaction.response.send_message(
                "❌ Ban can o trong mot Voice Channel hoac chon mot channel cu the!",
                ephemeral=True
            )
            return

    await interaction.response.defer(ephemeral=False)
    target_channel_id = channel.id
    await connect_to_voice(channel)
    await interaction.followup.send(f"✅ Da tham gia va se giu phong 24/7 tai: **{channel.name}**")


@bot.tree.command(name="leave", description="Yeu cau bot roi khoi Voice Room va tam dung giu phong.")
async def leave_command(interaction: discord.Interaction):
    global target_channel_id
    guild = interaction.guild
    voice_client = guild.voice_client

    target_channel_id = None  # Huy muc tieu giu phong de watchdog khong vao lai
    if voice_client:
        await voice_client.disconnect(force=True)
        await interaction.response.send_message("👋 Da roi khoi Voice Room va tat che do giu phong 24/7.")
    elif guild.me.voice and guild.me.voice.channel:
        # Neu co voice state ma khong co voice_client
        await guild.me.move_to(None)
        await interaction.response.send_message("👋 Da roi khoi Voice Room va tat che do giu phong 24/7.")
    else:
        await interaction.response.send_message("❌ Hien tai bot khong o trong phong voice nao.", ephemeral=True)


@bot.tree.command(name="status", description="Xem trang thai hien tai cua bot giu phong.")
async def status_command(interaction: discord.Interaction):
    guild = interaction.guild
    bot_voice = guild.me.voice if guild.me else None
    current_ch = bot_voice.channel.name if bot_voice and bot_voice.channel else "Khong co"
    target_ch = bot.get_channel(target_channel_id).name if target_channel_id and bot.get_channel(target_channel_id) else (str(target_channel_id) if target_channel_id else "Chua cau hinh")
    latency = round(bot.latency * 1000)
    is_in_room = bot_voice and bot_voice.channel and bot_voice.channel.id == target_channel_id

    embed = discord.Embed(
        title="🤖 Trang Thai Bot Giu Voice 24/7",
        color=discord.Color.green() if is_in_room else discord.Color.red()
    )
    embed.add_field(name="Phong dang o", value=f"`{current_ch}`", inline=True)
    embed.add_field(name="Phong muc tieu (24/7)", value=f"`{target_ch}`", inline=True)
    embed.add_field(name="Ping Bot", value=f"`{latency}ms`", inline=True)
    embed.add_field(name="Trang thai giu phong", value="`Dang giu phong on dinh ✅`" if is_in_room else "`Chua vao phong ❌`", inline=False)
    embed.set_footer(text="Bot hoat dong on dinh 24/7")

    await interaction.response.send_message(embed=embed)


def main():
    global bot
    if not TOKEN:
        logging.warning("[VoiceGuard] Chưa cấu hình VOICEGUARD_TOKEN hoặc DISCORD_TOKEN.")
        logging.warning("[VoiceGuard] Bot đang chuyển sang chế độ chờ (standby mode)...")
        import time
        while True:
            time.sleep(3600)

    # Khoi dong Web Server mini de Render / Koyeb / UptimeRobot giu ket noi
    start_keep_alive()

    # Khoi chay Bot
    try:
        bot.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        logging.warning("⚠️ Message Content Intent chua duoc bat tren Discord Developer Portal. Tu dong fallback de bot van hoat dong...")
        intents.message_content = False
        bot = commands.Bot(
            command_prefix="!",
            intents=intents,
            max_messages=50,
            chunk_guilds_at_startup=False,
        )
        bot.run(TOKEN)


if __name__ == "__main__":
    main()
