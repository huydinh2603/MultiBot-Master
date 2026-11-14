import os
import sys
import gc
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Optional, List
from dotenv import load_dotenv

try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

import discord
from discord.ext import commands, tasks
import yt_dlp

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
connect_lock = asyncio.Lock()
is_first_ready = True
OPUS_SILENCE_FRAME = b'\xF8\xFF\xFE'

# ---------------------------------------------------------------------------
# Cấu hình yt-dlp & FFmpeg Music Engine
# ---------------------------------------------------------------------------
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0',
    'js_runtimes': {'node': {}},
    'remote_components': {'ejs:github'},
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web_embedded', 'tv']
        }
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

thread_pool = ThreadPoolExecutor(max_workers=2)
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class SongItem:
    def __init__(self, title: str, web_url: str, stream_url: str, duration: int, thumbnail: str, requester: str):
        self.title = title
        self.web_url = web_url
        self.stream_url = stream_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester

    def format_duration(self) -> str:
        if not self.duration:
            return "Trực tiếp / Không rõ"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


# Quản lý hàng đợi nhạc & âm lượng
music_queue: List[SongItem] = []
current_song: Optional[SongItem] = None
current_volume: float = 0.85


def sanitize_song_query(query: str) -> str:
    """Làm sạch liên kết bài hát, loại bỏ tham số playlist/mix của YouTube để trích xuất chính xác."""
    clean = query.strip()
    # Nếu là liên kết xem video YouTube có chứa video ID (v=...)
    if "youtube.com/watch" in clean or "youtu.be/" in clean or "music.youtube.com/watch" in clean:
        yt_match = re.search(r'(?:youtube\.com/watch\?.*v=|youtu\.be/|music\.youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})', clean)
        if yt_match:
            return f"https://www.youtube.com/watch?v={yt_match.group(1)}"

    # Nếu không phải URL (người dùng gõ tên bài hát), tự động chuyển thành từ khóa tìm kiếm
    if not clean.startswith(('http://', 'https://')):
        return f"ytsearch1:{clean}"

    return clean


def extract_song_info(query: str, requester: str = "Người dùng") -> Optional[SongItem]:
    """Trích xuất link stream bằng cơ chế 3 lớp (Android Client -> Default YTDL -> SoundCloud Fallback)."""
    clean_q = sanitize_song_query(query)
    lower_q = clean_q.lower()

    # 1. Hỗ trợ link trực tiếp file âm thanh (MP3, M4A, AAC, FLAC, OGG, WAV) hoặc đài radio stream
    if any(lower_q.endswith(ext) or ext + '?' in lower_q for ext in ['.mp3', '.m4a', '.aac', '.flac', '.ogg', '.wav']):
        raw_name = clean_q.split('/')[-1].split('?')[0] or "Direct Audio Stream"
        return SongItem(
            title=raw_name,
            web_url=clean_q,
            stream_url=clean_q,
            duration=0,
            thumbnail="https://cdn-icons-png.flaticon.com/512/3844/3844724.png",
            requester=requester
        )

    # 2. Lớp 1: Thử trích xuất với YouTube Android Client (không yêu cầu đăng nhập, né lỗi Please sign in)
    try:
        ydl_opts_android = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'source_address': '0.0.0.0',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android']
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts_android) as ydl:
            info = ydl.extract_info(clean_q, download=False)
            if info:
                if 'entries' in info:
                    entries = list(info['entries']) if info['entries'] else []
                    info = entries[0] if entries else None

                if info:
                    stream_url = info.get('url')
                    if not stream_url and 'formats' in info:
                        audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('url')]
                        if audio_formats:
                            audio_formats.sort(key=lambda f: f.get('abr') or f.get('tbr') or 0, reverse=True)
                            stream_url = audio_formats[0].get('url')

                    if stream_url:
                        return SongItem(
                            title=info.get('title', 'Bài hát không tên'),
                            web_url=info.get('webpage_url') or clean_q,
                            stream_url=stream_url,
                            duration=info.get('duration', 0),
                            thumbnail=info.get('thumbnail') or "https://cdn-icons-png.flaticon.com/512/3844/3844724.png",
                            requester=requester
                        )
    except Exception as e:
        logging.warning(f"[YTDL Android Client] Thử nghiệm không thành công cho '{clean_q}': {e}. Đang chuyển sang cơ chế dự phòng...")

    # 3. Lớp 2: Thử trích xuất với cấu hình mặc định của yt-dlp
    try:
        ydl_opts_default = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'source_address': '0.0.0.0',
        }
        with yt_dlp.YoutubeDL(ydl_opts_default) as ydl:
            info = ydl.extract_info(clean_q, download=False)
            if info:
                if 'entries' in info:
                    entries = list(info['entries']) if info['entries'] else []
                    info = entries[0] if entries else None

                if info:
                    stream_url = info.get('url')
                    if not stream_url and 'formats' in info:
                        audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('url')]
                        if audio_formats:
                            audio_formats.sort(key=lambda f: f.get('abr') or f.get('tbr') or 0, reverse=True)
                            stream_url = audio_formats[0].get('url')

                    if stream_url:
                        return SongItem(
                            title=info.get('title', 'Bài hát không tên'),
                            web_url=info.get('webpage_url') or clean_q,
                            stream_url=stream_url,
                            duration=info.get('duration', 0),
                            thumbnail=info.get('thumbnail') or "https://cdn-icons-png.flaticon.com/512/3844/3844724.png",
                            requester=requester
                        )
    except Exception as e:
        logging.warning(f"[YTDL Default Client] Không thành công cho '{clean_q}': {e}. Kích hoạt SoundCloud Fallback...")

    # 4. Lớp 3: Cơ chế SoundCloud Fallback cực mạnh (SoundCloud không bao giờ chặn Datacenter IP)
    search_query = query.strip()
    if "youtube.com" in search_query or "youtu.be" in search_query:
        try:
            import urllib.request, json
            oembed_url = f"https://www.youtube.com/oembed?url={search_query}&format=json"
            req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get('title'):
                    raw_title = data['title']
                    # Loại bỏ hashtag để tìm kiếm chính xác nhất trên SoundCloud
                    search_query = re.sub(r'#\S+', '', raw_title).strip()
                    logging.info(f"[oEmbed Metadata] Đã trích xuất tên bài hát: '{search_query}'")
        except Exception as oerr:
            logging.debug(f"[oEmbed Error]: {oerr}")

    try:
        ydl_opts_sc = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'source_address': '0.0.0.0',
            'default_search': 'scsearch1',
        }
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            sc_target = search_query if search_query.startswith(('http://', 'https://')) else f"scsearch1:{search_query}"
            info = ydl.extract_info(sc_target, download=False)
            if info:
                if 'entries' in info:
                    entries = list(info['entries']) if info['entries'] else []
                    info = entries[0] if entries else None

                if info and info.get('url'):
                    logging.info(f"[SoundCloud Fallback] Đã tìm thấy trên SoundCloud: '{info.get('title')}'")
                    return SongItem(
                        title=info.get('title', search_query),
                        web_url=info.get('webpage_url') or query,
                        stream_url=info.get('url'),
                        duration=info.get('duration', 0),
                        thumbnail=info.get('thumbnail') or "https://cdn-icons-png.flaticon.com/512/3844/3844724.png",
                        requester=requester
                    )
    except Exception as e:
        logging.error(f"[SoundCloud Fallback] Thất bại cho '{search_query}': {e}")

    return None


def after_play(error):
    """Callback kích hoạt khi một bài hát kết thúc hoặc gặp sự cố."""
    if error:
        logging.error(f"[Player Error]: {error}")
    # Đẩy tác vụ phát bài kế tiếp vào event loop của bot
    if bot.loop and not bot.loop.is_closed():
        asyncio.run_coroutine_threadsafe(play_next_song(), bot.loop)


async def play_next_song():
    """Lấy bài tiếp theo trong hàng đợi và phát vào voice channel."""
    global current_song, music_queue

    # Tìm voice client đang kết nối
    vc = None
    for client in bot.voice_clients:
        if client and client.is_connected():
            vc = client
            break

    if not vc or not vc.is_connected():
        current_song = None
        return

    if len(music_queue) > 0:
        current_song = music_queue.pop(0)
        try:
            source = discord.FFmpegPCMAudio(current_song.stream_url, **FFMPEG_OPTIONS)
            transformed = discord.PCMVolumeTransformer(source, volume=current_volume)
            vc.play(transformed, after=after_play)
            logging.info(f"[Player] Đang phát: '{current_song.title}'")
        except Exception as e:
            logging.error(f"[Player] Không thể phát '{current_song.title}': {e}")
            current_song = None
            await play_next_song()
    else:
        current_song = None
        logging.info("[Player] Hàng đợi đã phát xong. Tiếp tục chế độ giữ phòng im lặng (Silence Keepalive).")


# ---------------------------------------------------------------------------
# Quản lý Voice Channel & Keepalive
# ---------------------------------------------------------------------------
def is_bot_in_target_channel(guild: discord.Guild, target_id: int) -> bool:
    """Kiem tra xem bot co thuc su dang o trong phong voice muc tieu hay khong."""
    if not guild or not target_id:
        return False

    # 1. Kiem tra voice_client dang hoat dong
    vc = guild.voice_client
    if vc and vc.is_connected() and vc.channel and vc.channel.id == target_id:
        return True

    # 2. Kiem tra VoiceState tren may chu Discord
    if guild.me and guild.me.voice and guild.me.voice.channel:
        if guild.me.voice.channel.id == target_id:
            return True

    return False


async def connect_to_voice(channel: discord.VoiceChannel):
    """Ket noi hoac di chuyen bot den Voice Channel muc tieu an toan, chong giat/kick."""
    async with connect_lock:
        guild = channel.guild

        try:
            # 1. Neu bot DA O DUNG PHONG roi, TUYET DOI KHONG lam gi va KHONG disconnect
            if is_bot_in_target_channel(guild, channel.id):
                return

            vc = guild.voice_client

            # 2. Neu bot dang o mot phong voice khac trong server (vi du: bi keo hoac chuyen sang AFK)
            if guild.me and guild.me.voice and guild.me.voice.channel:
                if guild.me.voice.channel.id != channel.id:
                    logging.info(f"Bot dang o phong '{guild.me.voice.channel.name}', dang chuyen ve phong '{channel.name}'...")
                    if vc and vc.is_connected():
                        await vc.move_to(channel)
                        return
                    else:
                        await guild.me.move_to(channel)
                        return

            # 3. Neu voice_client dang ket noi vao dung phong nay roi
            if vc and vc.is_connected():
                if vc.channel and vc.channel.id == channel.id:
                    return
                else:
                    await vc.move_to(channel)
                    return

            # 4. Neu co voice_client cu nhung bi mat ket noi (zombie), don dep an toan
            if vc is not None:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

            # 5. Tien hanh ket noi moi
            logging.info(f"Dang ket noi vao voice room: {channel.name} (ID: {channel.id})...")
            await channel.connect(reconnect=True, timeout=30.0, self_deaf=True)
            logging.info(f"Da ket noi thanh cong vao: {channel.name}")

        except Exception as e:
            logging.error(f"Loi khi ket noi vao voice room '{channel.name}': {e}")


@tasks.loop(seconds=15)
async def voice_keepalive():
    """Gui frame silence (Opus RFC 6716) dinh ky 15 giay qua UDP khi KHONG CO NHAC DANG PHAT.
    Ngan chan Discord RTC server ngat ket noi do khong co du lieu am thanh (inactivity/idle timeout).
    Ton 0% CPU va chi ton 3 bytes bang thong moi 15 giay."""
    for vc in bot.voice_clients:
        try:
            if vc and vc.is_connected() and not vc.is_playing() and not vc.is_paused():
                vc.send_audio_packet(OPUS_SILENCE_FRAME, encode=False)
        except Exception as e:
            logging.debug(f"[KeepAlive] Loi gui packet: {e}")


@voice_keepalive.before_loop
async def before_voice_keepalive():
    await bot.wait_until_ready()


@tasks.loop(seconds=45)
async def voice_watchdog():
    """Tac vu kiem tra moi 45 giay: Chi ket noi lai neu bot THUC SU khong o trong phong."""
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
        # Neu bot DA O DUNG PHONG, hoan toan giu nguyen ket noi
        if is_bot_in_target_channel(channel.guild, channel.id):
            return

        logging.warning(f"[Watchdog] Phat hien bot khong o trong phong '{channel.name}'. Tien hanh ket noi...")
        await connect_to_voice(channel)


@voice_watchdog.before_loop
async def before_voice_watchdog():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    global is_first_ready, target_channel_id
    logging.info(f"Bot da online voi ten: {bot.user} (ID: {bot.user.id})")

    # Chi dong bo slash commands 1 lan duy nhat khi vua khoi dong
    if is_first_ready:
        try:
            synced = await bot.tree.sync()
            logging.info(f"Da dong bo {len(synced)} lenh slash.")
        except Exception as e:
            logging.error(f"Khong the dong bo slash command: {e}")

    # Khoi dong cac vong lap giu ket noi neu chua chay
    if not voice_keepalive.is_running():
        voice_keepalive.start()
    if not voice_watchdog.is_running():
        voice_watchdog.start()

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
            if not is_bot_in_target_channel(channel.guild, channel.id):
                await connect_to_voice(channel)
            else:
                logging.info(f"Bot da o san trong phong voice '{channel.name}', giu nguyen ket noi.")
        else:
            logging.warning(f"ID {target_channel_id} khong phai la Voice Channel hop le!")

    is_first_ready = False


@bot.event
async def on_voice_state_update(member, before, after):
    """Xu ly khi co su kien thay doi voice cua chinh bot."""
    global target_channel_id
    if member.id == bot.user.id and target_channel_id:
        # Neu kenh khong thay doi (vi du: cap nhat mute/deaf), bo qua
        if before.channel == after.channel:
            return

        logging.info(f"[VoiceState] Bot voice state thay doi: '{before.channel}' -> '{after.channel}'")

        # Truong hop 1: Bot bi ngat ket noi (after.channel is None)
        if after.channel is None:
            logging.warning("Bot bi ngat ket noi khoi voice room. Cho 2 giay kiem tra trang thai...")
            await asyncio.sleep(2)
            channel = bot.get_channel(target_channel_id)
            if not channel:
                try:
                    channel = await bot.fetch_channel(target_channel_id)
                except Exception:
                    channel = None
            if channel and isinstance(channel, discord.VoiceChannel):
                if not is_bot_in_target_channel(channel.guild, target_channel_id):
                    logging.info(f"Tien hanh ket noi lai vao '{channel.name}'...")
                    await connect_to_voice(channel)

        # Truong hop 2: Bot bi ai do keo hoac he thong chuyen sang phong khac (vi du kenh AFK)
        elif after.channel.id != target_channel_id:
            logging.warning(f"Bot bi chuyen sang '{after.channel.name}'. Se chuyen lai phong chinh sau 2 giay...")
            await asyncio.sleep(2)
            channel = bot.get_channel(target_channel_id)
            if not channel:
                try:
                    channel = await bot.fetch_channel(target_channel_id)
                except Exception:
                    channel = None
            if channel and isinstance(channel, discord.VoiceChannel):
                await connect_to_voice(channel)


# ==============================================================================
# SLASH COMMANDS (ÂM NHẠC & GIỮ PHÒNG)
# ==============================================================================

@bot.tree.command(name="play", description="Phát bài hát từ link YouTube, SoundCloud, MP3 trực tiếp hoặc tìm kiếm tên bài.")
@discord.app_commands.describe(link="Link bài hát (YouTube, SoundCloud, MP3) hoặc tên bài hát cần phát")
async def play_command(interaction: discord.Interaction, link: str):
    global target_channel_id, music_queue

    # 1. Đảm bảo bot đang hoặc sẽ vào đúng phòng voice
    user_vc = interaction.user.voice.channel if (interaction.user.voice and interaction.user.voice.channel) else None
    bot_vc = interaction.guild.voice_client if interaction.guild else None

    if not bot_vc or not bot_vc.is_connected():
        if user_vc:
            target_channel_id = user_vc.id
            await connect_to_voice(user_vc)
            bot_vc = interaction.guild.voice_client
        elif target_channel_id:
            ch = bot.get_channel(target_channel_id)
            if ch and isinstance(ch, discord.VoiceChannel):
                await connect_to_voice(ch)
                bot_vc = interaction.guild.voice_client
        else:
            return await interaction.response.send_message(
                "❌ Bạn cần ở trong một phòng Voice hoặc dùng `/join` trước để bot tham gia!",
                ephemeral=True
            )

    await interaction.response.defer(ephemeral=False)

    # 2. Trích xuất thông tin bài hát trong ThreadPool để không làm đơ bot
    loop = asyncio.get_running_loop()
    song = await loop.run_in_executor(
        thread_pool,
        lambda: extract_song_info(link, interaction.user.display_name)
    )

    if not song or not song.stream_url:
        return await interaction.followup.send(
            f"❌ Không thể tìm thấy hoặc trích xuất âm thanh từ liên kết: `{link}`\n"
            "*Vui lòng kiểm tra lại liên kết hoặc thử dán link YouTube/SoundCloud công khai khác.*"
        )

    # 3. Thêm vào hàng đợi & xử lý phát
    music_queue.append(song)
    bot_vc = interaction.guild.voice_client

    if bot_vc and (bot_vc.is_playing() or bot_vc.is_paused()):
        embed = discord.Embed(
            title="📥 Đã Thêm Vào Hàng Đợi",
            description=f"**[{song.title}]({song.web_url})**",
            color=discord.Color.blue()
        )
        embed.add_field(name="Vị trí trong hàng đợi", value=f"`#{len(music_queue)}`", inline=True)
        embed.add_field(name="Thời lượng", value=f"`{song.format_duration()}`", inline=True)
        embed.add_field(name="Yêu cầu bởi", value=f"`{song.requester}`", inline=True)
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        await interaction.followup.send(embed=embed)
    else:
        await play_next_song()
        embed = discord.Embed(
            title="🎶 Đang Phát Bài Hát",
            description=f"**[{song.title}]({song.web_url})**",
            color=discord.Color.green()
        )
        embed.add_field(name="Thời lượng", value=f"`{song.format_duration()}`", inline=True)
        embed.add_field(name="Yêu cầu bởi", value=f"`{song.requester}`", inline=True)
        embed.add_field(name="Kênh Voice", value=f"`{bot_vc.channel.name if bot_vc and bot_vc.channel else 'Voice Channel'}`", inline=True)
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="skip", description="Bỏ qua bài hát đang phát và chuyển sang bài kế tiếp.")
async def skip_command(interaction: discord.Interaction):
    global current_song
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_connected():
        return await interaction.response.send_message("❌ Bot hiện không ở trong phòng voice!", ephemeral=True)

    if not vc.is_playing() and not vc.is_paused():
        return await interaction.response.send_message("❌ Hiện tại không có bài hát nào đang phát để bỏ qua!", ephemeral=True)

    skipped = current_song.title if current_song else "Bài hát hiện tại"
    vc.stop()
    await interaction.response.send_message(f"⏭️ Đã bỏ qua: **{skipped}**")


@bot.tree.command(name="stop", description="Dừng phát nhạc và xóa toàn bộ bài hát trong hàng đợi.")
async def stop_command(interaction: discord.Interaction):
    global music_queue, current_song
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_connected():
        return await interaction.response.send_message("❌ Bot hiện không ở trong phòng voice!", ephemeral=True)

    music_queue.clear()
    current_song = None
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    await interaction.response.send_message("⏹️ Đã dừng phát nhạc và xóa toàn bộ danh sách chờ.")


@bot.tree.command(name="pause", description="Tạm dừng bài hát đang phát.")
async def pause_command(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_playing():
        return await interaction.response.send_message("❌ Không có bài hát nào đang phát để tạm dừng!", ephemeral=True)
    vc.pause()
    await interaction.response.send_message("⏸️ Đã tạm dừng phát nhạc.")


@bot.tree.command(name="resume", description="Tiếp tục phát bài hát đang tạm dừng.")
async def resume_command(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_paused():
        return await interaction.response.send_message("❌ Bài hát không ở trạng thái tạm dừng!", ephemeral=True)
    vc.resume()
    await interaction.response.send_message("▶️ Đã tiếp tục phát nhạc.")


@bot.tree.command(name="queue", description="Xem danh sách các bài hát đang chờ phát.")
async def queue_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Danh Sách Hàng Đợi Âm Nhạc", color=discord.Color.purple())
    if current_song:
        embed.add_field(
            name="▶️ Đang phát:",
            value=f"**[{current_song.title}]({current_song.web_url})** | `{current_song.format_duration()}` (Bởi: `{current_song.requester}`)",
            inline=False
        )
    else:
        embed.add_field(name="▶️ Đang phát:", value="*Không có bài hát nào đang phát.*", inline=False)

    if len(music_queue) > 0:
        lines = []
        for i, s in enumerate(music_queue[:10]):
            lines.append(f"`#{i+1}.` [{s.title}]({s.web_url}) | `{s.format_duration()}` (Bởi: `{s.requester}`)")
        q_str = "\n".join(lines)
        if len(music_queue) > 10:
            q_str += f"\n*...và còn {len(music_queue) - 10} bài khác nữa.*"
        embed.add_field(name="⏳ Bài hát tiếp theo:", value=q_str, inline=False)
    else:
        embed.add_field(name="⏳ Hàng đợi:", value="*Hàng đợi đang trống. Dùng `/play <link>` để thêm bài hát!*", inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="nowplaying", description="Xem thông tin chi tiết bài hát đang phát.")
async def np_command(interaction: discord.Interaction):
    if not current_song:
        return await interaction.response.send_message("❌ Hiện tại không có bài hát nào đang phát!", ephemeral=True)

    embed = discord.Embed(
        title="🎵 Đang Phát Hiện Tại",
        description=f"**[{current_song.title}]({current_song.web_url})**",
        color=discord.Color.green()
    )
    embed.add_field(name="Thời lượng", value=f"`{current_song.format_duration()}`", inline=True)
    embed.add_field(name="Yêu cầu bởi", value=f"`{current_song.requester}`", inline=True)
    if current_song.thumbnail:
        embed.set_thumbnail(url=current_song.thumbnail)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="volume", description="Điều chỉnh âm lượng phát nhạc (1 - 100%).")
@discord.app_commands.describe(percent="Mức âm lượng từ 1 đến 100")
async def volume_command(interaction: discord.Interaction, percent: int):
    global current_volume
    if percent < 1 or percent > 100:
        return await interaction.response.send_message("❌ Âm lượng phải từ 1 đến 100%!", ephemeral=True)

    current_volume = percent / 100.0
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.source:
        try:
            vc.source.volume = current_volume
        except Exception:
            pass
    await interaction.response.send_message(f"🔊 Đã điều chỉnh âm lượng thành: **{percent}%**")


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
    global target_channel_id, music_queue, current_song
    guild = interaction.guild
    voice_client = guild.voice_client

    music_queue.clear()
    current_song = None
    target_channel_id = None  # Huy muc tieu giu phong de watchdog khong vao lai
    if voice_client:
        await voice_client.disconnect(force=True)
        await interaction.response.send_message("👋 Da roi khoi Voice Room va tat che do giu phong 24/7.")
    elif guild.me.voice and guild.me.voice.channel:
        await guild.me.move_to(None)
        await interaction.response.send_message("👋 Da roi khoi Voice Room va tat che do giu phong 24/7.")
    else:
        await interaction.response.send_message("❌ Hien tai bot khong o trong phong voice nao.", ephemeral=True)


@bot.tree.command(name="status", description="Xem trang thai hien tai cua bot giu phong va phat nhac.")
async def status_command(interaction: discord.Interaction):
    guild = interaction.guild
    bot_voice = guild.me.voice if guild.me else None
    current_ch = bot_voice.channel.name if bot_voice and bot_voice.channel else "Khong co"
    target_ch = bot.get_channel(target_channel_id).name if target_channel_id and bot.get_channel(target_channel_id) else (str(target_channel_id) if target_channel_id else "Chua cau hinh")
    latency = round(bot.latency * 1000)
    is_in_room = bot_voice and bot_voice.channel and bot_voice.channel.id == target_channel_id

    embed = discord.Embed(
        title="🤖 Trang Thai VoiceGuard 24/7 & Music Player",
        color=discord.Color.green() if is_in_room else discord.Color.red()
    )
    embed.add_field(name="Phong dang o", value=f"`{current_ch}`", inline=True)
    embed.add_field(name="Phong muc tieu (24/7)", value=f"`{target_ch}`", inline=True)
    embed.add_field(name="Ping Bot", value=f"`{latency}ms`", inline=True)
    embed.add_field(
        name="Trang thai phat nhac",
        value=f"Đang phát: **{current_song.title}**" if current_song else "Chế độ giữ phòng im lặng (Silence Keepalive) ✅",
        inline=False
    )
    embed.add_field(
        name="So bai trong hang doi",
        value=f"`{len(music_queue)} bài`",
        inline=True
    )
    embed.set_footer(text="Hoạt động ổn định 24/7 • Hỗ trợ /play YouTube, SoundCloud, MP3")

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
