import discord
from discord.ext import commands
import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union, Tuple
from database import DatabaseManager, has_nested_quantifiers

logger = logging.getLogger("DiscordBot.CustomCmds")
MAX_TRIGGER_LENGTH = 100
MAX_RESPONSE_LENGTH = 1500

# Sentinel used to escape literal pipe characters in responses.
# Users write "||" to get a literal "|", while single "|" separates
# random-choice alternatives.
_PIPE_ESCAPE = "\x00PIPE\x00"

# ---------------------------------------------------------------------------
# Command syntax & guidance definitions
# ---------------------------------------------------------------------------
COMMAND_GUIDE: Dict[str, Dict[str, Any]] = {
    "addcmd": {
        "title": "➕ Lệnh Tạo Custom Command (!addcmd)",
        "syntax": "!addcmd [--contains|--regex|--exact] [--embed|--text] <từ_khóa> <nội_dung>",
        "desc": "Tạo câu trả lời tự động mới. Hỗ trợ so khớp chính xác, chứa từ khóa, regex, và định dạng văn bản hoặc Discord Embed.",
        "examples": [
            "!addcmd hi Xin chào bạn! Chúc một ngày tốt lành.",
            "!addcmd --contains discord Link tham gia Discord tại {channel}!",
            "!addcmd --regex ^(chao|hi|hello)$ Xin chào {user}!",
            "!addcmd --embed rule Quy tắc máy chủ: Tôn trọng mọi người!",
            "!addcmd 8ball Chắc chắn rồi! | Không bao giờ | Có thể đấy",
            "!addcmd coin Ngửa | Sấp",
        ],
    },
    "editcmd": {
        "title": "✏️ Lệnh Sửa Custom Command (!editcmd)",
        "syntax": "!editcmd [--contains|--regex|--exact] [--embed|--text] <từ_khóa> <nội_dung_mới>",
        "desc": "Chỉnh sửa câu trả lời hoặc tùy chọn của lệnh mà không đổi số lượt dùng (chỉ người tạo lệnh hoặc Admin).",
        "examples": [
            "!editcmd hi Xin chào {user.name}, rất vui được gặp bạn!",
            "!editcmd --embed hi Xin chào {user} qua Embed!",
        ],
    },
    "delcmd": {
        "title": "🗑️ Lệnh Xóa Custom Command (!delcmd)",
        "syntax": "!delcmd <từ_khóa>",
        "desc": "Xóa lệnh tùy chỉnh khỏi máy chủ (chỉ người tạo lệnh hoặc Admin).",
        "examples": [
            "!delcmd hi",
        ],
    },
    "cmdinfo": {
        "title": "🔍 Xem Chi Tiết Custom Command (!cmdinfo)",
        "syntax": "!cmdinfo <từ_khóa>",
        "desc": "Xem chi tiết kiểu so khớp, định dạng phản hồi, tác giả và lượt dùng của một lệnh.",
        "examples": [
            "!cmdinfo hi",
        ],
    },
    "mycmd": {
        "title": "📋 Xem Lệnh Của Bản Thân (!mycmd)",
        "syntax": "!mycmd",
        "desc": "Hiển thị danh sách tất cả các custom command do chính bạn tạo trong server này.",
        "examples": [
            "!mycmd",
        ],
    },
    "cmdlist": {
        "title": "📜 Xem Toàn Bộ Lệnh Server (!cmdlist)",
        "syntax": "!cmdlist",
        "desc": "Hiển thị toàn bộ các custom command có trong server kèm kiểu so khớp và lượt dùng.",
        "examples": [
            "!cmdlist",
        ],
    },
    "topcmds": {
        "title": "🏆 Bảng Xếp Hạng Lệnh Dùng Nhiều (!topcmds)",
        "syntax": "!topcmds",
        "desc": "Xem Top 10 câu lệnh được gọi nhiều nhất trên server.",
        "examples": [
            "!topcmds",
        ],
    },
    "cmdguide": {
        "title": "📖 Cuốn Cẩm Nang Tương Tác (!cmdguide)",
        "syntax": "!cmdguide",
        "desc": "Mở cẩm nang tương tác hướng dẫn sử dụng bot 6 chương qua Select Menu.",
        "examples": [
            "!cmdguide",
        ],
    },
    "setmode": {
        "title": "🔒 Cài Đặt Chế Độ Tạo Lệnh (!setmode)",
        "syntax": "!setmode <everyone | role | admin>",
        "desc": "Phân quyền ai có thể tạo custom command mới trong server.",
        "examples": [
            "!setmode everyone (Tất cả thành viên)",
            "!setmode role (Chỉ các role được chỉ định qua !setrole)",
            "!setmode admin (Chỉ Quản trị viên)",
        ],
    },
    "setrole": {
        "title": "🎭 Cài Đặt Role Được Tạo Lệnh (!setrole)",
        "syntax": "!setrole @Role1 [@Role2...] | !setrole clear",
        "desc": "Chỉ định một hoặc nhiều vai trò được phép tạo lệnh (chế độ role_only).",
        "examples": [
            "!setrole @Member @VIP @Staff",
            "!setrole clear (Xóa toàn bộ role đã gán)",
        ],
    },
    "setchannel": {
        "title": "💬 Giới Hạn Kênh Phản Hồi (!setchannel)",
        "syntax": "!setchannel <#kênh | none>",
        "desc": "Giới hạn bot chỉ phản hồi custom commands trong kênh chỉ định (hoặc mở cho tất cả các kênh).",
        "examples": [
            "!setchannel #bot-commands",
            "!setchannel none (Phản hồi ở mọi kênh)",
        ],
    },
    "setup": {
        "title": "⚙️ Bảng Điều Khiển Quản Trị (!setup)",
        "syntax": "!setup",
        "desc": "Hiển thị tổng quan toàn bộ tính năng Auto-Response, trạng thái hệ thống và danh sách lệnh điều chỉnh nhanh.",
        "examples": [
            "!setup",
        ],
    },
}

# ---------------------------------------------------------------------------
# Argument parser helper
# ---------------------------------------------------------------------------

def _peel_flags(
    text: str,
    current_match: Optional[str],
    current_response: Optional[str]
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Peel leading and trailing flag tokens from text.

    Returns:
        (cleaned_text, match_type, response_type, error_msg)
    """
    match_type = current_match
    response_type = current_response
    changed = True
    while changed and text:
        changed = False

        # --- Check prefix flags ---
        # --match=<val>
        m = re.match(r'^--match=(\S+)\s*', text, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            if val not in ("exact", "contains", "regex"):
                return text, "", "", f"Kiểu so khớp '{val}' không hợp lệ. Vui lòng chọn: exact, contains, regex."
            match_type = val
            text = text[len(m.group(0)):].strip()
            changed = True
            continue

        # --type=<val>
        m = re.match(r'^--type=(\S+)\s*', text, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            if val not in ("text", "embed"):
                return text, "", "", f"Định dạng phản hồi '{val}' không hợp lệ. Vui lòng chọn: text, embed."
            response_type = val
            text = text[len(m.group(0)):].strip()
            changed = True
            continue

        # --match <val>
        m = re.match(r'^--match\s+(\S+)\s*', text, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            if val not in ("exact", "contains", "regex"):
                return text, "", "", f"Kiểu so khớp '{val}' không hợp lệ. Vui lòng chọn: exact, contains, regex."
            match_type = val
            text = text[len(m.group(0)):].strip()
            changed = True
            continue

        # --type <val>
        m = re.match(r'^--type\s+(\S+)\s*', text, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            if val not in ("text", "embed"):
                return text, "", "", f"Định dạng phản hồi '{val}' không hợp lệ. Vui lòng chọn: text, embed."
            response_type = val
            text = text[len(m.group(0)):].strip()
            changed = True
            continue

        # Simple flag tokens at front
        m = re.match(r'^(--contains|--regex|--exact|--embed|--text)\b\s*', text, re.IGNORECASE)
        if m:
            flag = m.group(1).lower()
            if flag in ("--contains", "--regex", "--exact"):
                match_type = flag[2:]
            elif flag in ("--embed", "--text"):
                response_type = flag[2:]
            text = text[len(m.group(0)):].strip()
            changed = True
            continue

        # --- Check suffix flags ---
        m = re.search(r'\s+(--contains|--regex|--exact|--embed|--text)$', text, re.IGNORECASE)
        if m:
            flag = m.group(1).lower()
            if flag in ("--contains", "--regex", "--exact"):
                match_type = flag[2:]
            elif flag in ("--embed", "--text"):
                response_type = flag[2:]
            text = text[:m.start()].strip()
            changed = True
            continue

        m = re.search(r'\s+--(match|type)=(\S+)$', text, re.IGNORECASE)
        if m:
            kind = m.group(1).lower()
            val = m.group(2).lower()
            if kind == "match":
                if val not in ("exact", "contains", "regex"):
                    return text, "", "", f"Kiểu so khớp '{val}' không hợp lệ. Vui lòng chọn: exact, contains, regex."
                match_type = val
            else:
                if val not in ("text", "embed"):
                    return text, "", "", f"Định dạng phản hồi '{val}' không hợp lệ. Vui lòng chọn: text, embed."
                response_type = val
            text = text[:m.start()].strip()
            changed = True
            continue

        m = re.search(r'\s+--(match|type)\s+(\S+)$', text, re.IGNORECASE)
        if m:
            kind = m.group(1).lower()
            val = m.group(2).lower()
            if kind == "match":
                if val not in ("exact", "contains", "regex"):
                    return text, "", "", f"Kiểu so khớp '{val}' không hợp lệ. Vui lòng chọn: exact, contains, regex."
                match_type = val
            else:
                if val not in ("text", "embed"):
                    return text, "", "", f"Định dạng phản hồi '{val}' không hợp lệ. Vui lòng chọn: text, embed."
                response_type = val
            text = text[:m.start()].strip()
            changed = True
            continue

    return text, match_type, response_type, None


def parse_cmd_arguments(
    raw_text: str,
    default_match: Optional[str] = "exact",
    default_response: Optional[str] = "text"
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Parse user command input string to extract trigger, response, match_type, response_type.

    Supports flags at the beginning, between trigger and response, or at the end.

    Returns:
        (trigger, response, match_type, response_type, error_message)
    """
    text = raw_text.strip()
    if not text:
        return None, None, default_match, default_response, None

    text, match_type, response_type, err = _peel_flags(text, default_match, default_response)
    if err:
        return None, None, "", "", err
    if not text:
        return None, None, match_type, response_type, None

    # Extract trigger and remaining text
    if text[0] in ('"', "'"):
        quote_char = text[0]
        closing_idx = text.find(quote_char, 1)
        if closing_idx != -1:
            trigger = text[1:closing_idx].strip()
            rem = text[closing_idx + 1:].strip()
        else:
            parts = text.split(None, 1)
            trigger = parts[0]
            rem = parts[1] if len(parts) > 1 else ""
    else:
        parts = text.split(None, 1)
        trigger = parts[0]
        rem = parts[1] if len(parts) > 1 else ""

    # Peel any flags that were placed immediately after trigger (e.g. `trigger --embed Response`)
    if rem:
        rem, match_type, response_type, err = _peel_flags(rem, match_type, response_type)
        if err:
            return None, None, "", "", err

    response = rem if rem else None
    return trigger, response, match_type, response_type, None


# ---------------------------------------------------------------------------
# Placeholder resolution & Embed helper
# ---------------------------------------------------------------------------

def parse_placeholders(raw_text: str, message: discord.Message) -> str:
    """Handle random-choice pipe syntax and replace placeholder tokens in a single pass."""
    # 1. Random-choice pipe syntax on template first: "A | B | C" picks one branch.
    # Escaped "||" produces a literal "|".
    # Evaluating random choice BEFORE placeholders prevents external strings
    # (e.g. server names or user display names containing '|') from injecting unintended choices.
    temp = raw_text.replace("||", _PIPE_ESCAPE)
    if "|" in temp:
        choices = [c.strip() for c in temp.split("|") if c.strip()]
        if len(choices) > 1:
            chosen_template = random.choice(choices)
        elif choices:
            chosen_template = choices[0]
        else:
            chosen_template = temp
    else:
        chosen_template = temp

    # 2. Single-pass placeholder replacement on the chosen template
    member_count = str(message.guild.member_count) if message.guild else "1"
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%d/%m/%Y")
    replacements = {
        "{user.display_name}": message.author.display_name,
        "{user.name}": message.author.name,
        "{user}": message.author.mention,
        "{server.members}": member_count,
        "{server}": message.guild.name if message.guild else "Direct Message",
        "{channel}": message.channel.mention if hasattr(message.channel, "mention") else "",
        "{date}": now_str,
        "{time}": now.strftime("%H:%M:%S UTC"),
    }

    def token_replacer(match: re.Match) -> str:
        token = match.group(0)
        if token in replacements:
            return replacements[token]
        if token == "{random}":
            return str(random.randint(1, 100))
        # {random.X-Y}
        try:
            start = int(match.group(1))
            end = int(match.group(2))
            if start <= end:
                return str(random.randint(start, end))
        except Exception:
            pass
        return token

    # Single-pass substitution avoids cascading token injection from usernames/guild names
    fixed_keys = "|".join(re.escape(k) for k in replacements.keys())
    pattern = re.compile(rf"{fixed_keys}|\{{random\.(\d+)-(\d+)\}}|\{{random\}}")
    result = pattern.sub(token_replacer, chosen_template)

    # 3. Restore escaped literal pipes
    return result.replace(_PIPE_ESCAPE, "|")


def create_response_embed(text: str, message: discord.Message) -> discord.Embed:
    """Convert response text into a Discord Embed.

    Supports optional 'title: <Title>\n<Description>' syntax.
    Overflow beyond Discord's 256-character title limit is automatically
    preserved and directed into the description without data loss.
    """
    title = None
    description = text
    lines = text.split("\n", 1)
    first_line = lines[0].strip()

    if first_line.lower().startswith("title:") and len(lines) > 1:
        title = first_line[6:].strip()
        description = lines[1].strip()
    elif first_line.lower().startswith("title:"):
        title = first_line[6:].strip()
        description = ""

    if not title and not description:
        description = text

    # Handle overflow if title exceeds Discord's 256-character limit so no user text is lost
    if title and len(title) > 256:
        overflow = title[256:].strip()
        title = title[:256].strip()
        if overflow:
            description = (overflow + ("\n" + description if description else "")).strip()

    # Discord description limit is 4096 characters
    if description and len(description) > 4000:
        description = description[:3997] + "..."

    embed = discord.Embed(
        title=title if title else None,
        description=description if description else None,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    if message.guild:
        footer_text = message.guild.name[:2048] if message.guild.name else ""
        icon_url = message.guild.icon.url if message.guild.icon else None
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=icon_url)
    return embed


def is_safe_regex(pattern: str) -> tuple[bool, str]:
    """Validate that regex is syntactically valid and free from catastrophic ReDoS backtracking."""
    try:
        re.compile(pattern)
    except re.error as e:
        return False, f"Biểu thức chính quy (Regex) không hợp lệ: `{e}`"

    # Check for catastrophic backtracking: nested quantifiers like (a+)+, ((a+))+, (\w+)*, (a|b+)+, (.*)+, (x+){2,}
    if has_nested_quantifiers(pattern):
        return False, "Biểu thức chính quy (Regex) không an toàn (nguy cơ ReDoS do lặp lồng nhau như `(a+)+` hoặc `(\\w+)*`)."

    return True, ""


# ---------------------------------------------------------------------------
# Reusable interactive paginator view
# ---------------------------------------------------------------------------

class PaginatorView(discord.ui.View):
    """View with Next/Previous buttons for paging through list embeds."""

    def __init__(self, pages: List[discord.Embed], author_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        self.message: Optional[discord.Message] = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = (self.current_page == 0)
        self.next_btn.disabled = (self.current_page >= len(self.pages) - 1)
        self.page_indicator.label = f"Trang {self.current_page + 1}/{len(self.pages)}"

    @discord.ui.button(label="◀️ Trước", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên bảng phân trang của người khác!", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Trang 1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Sau ▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên bảng phân trang của người khác!", ephemeral=True)
            return
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# Interactive guide view
# ---------------------------------------------------------------------------

class GuideSelect(discord.ui.Select):
    def __init__(self, settings: dict):
        self.settings = settings
        options = [
            discord.SelectOption(label="Trang Bìa: Tổng Quan", description="Giới thiệu cẩm nang Auto-Response", emoji="📖", value="cover"),
            discord.SelectOption(label="Chương 1: Phân Quyền Server", description="Chế độ phân quyền và cài đặt server", emoji="🛡️", value="roles"),
            discord.SelectOption(label="Chương 2: Tạo Lệnh & Biến Động", description="Cú pháp tạo lệnh, {user}, {random}, |", emoji="➕", value="addcmd"),
            discord.SelectOption(label="Chương 3: So Khớp & Embed Nâng Cao", description="Exact, Contains, Regex và Discord Embed", emoji="⚡", value="advanced"),
            discord.SelectOption(label="Chương 4: Quản Lý & Bảng Xếp Hạng", description="!mycmd, !cmdlist, !topcmds, !cmdinfo", emoji="📊", value="stats"),
            discord.SelectOption(label="Chương 5: Sửa & Xóa Lệnh", description="!editcmd, !delcmd và quyền sở hữu", emoji="✏️", value="manage"),
            discord.SelectOption(label="Chương 6: Bảng Điều Khiển Quản Trị", description="Dành riêng cho Admin (!setup)", emoji="👑", value="admin"),
        ]
        super().__init__(placeholder="📚 Chọn chương bạn muốn đọc tại đây...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        mode = self.settings.get("cmd_mode", "everyone")
        role_ids = self.settings.get("allowed_role_ids", [])
        if selected == "cover":
            embed = discord.Embed(
                title="📖 CẨM NANG HƯỚNG DẪN: DISCORD AUTO-RESPONSE BOT",
                description="Chào mừng bạn đến với Cẩm Nang Hướng Dẫn Tương Tác!\n"
                            "Hệ thống cung cấp giải pháp Auto-Response thông minh với:\n"
                            "• Đa dạng kiểu so khớp: Khớp chính xác, Chứa từ khóa, và Biểu thức chính quy Regex.\n"
                            "• Định dạng phong phú: Tin nhắn văn bản hoặc Discord Embed.\n"
                            "• Biến động thông minh: `{user}`, `{server}`, `{channel}`, `{random}`, ngẫu nhiên `|`.\n\n"
                            "👉 Hãy chọn một chương từ Menu bên dưới để khám phá chi tiết!",
                color=discord.Color.blue()
            )
        elif selected == "roles":
            roles_text = ", ".join([f"<@&{r_id}>" for r_id in role_ids]) if role_ids else "*(Chưa cấu hình)*"
            mode_desc = {
                "everyone": "🟢 Mọi thành viên (Everyone): Ai cũng có thể tạo lệnh tự do.",
                "role_only": f"🟡 Chỉ Role quy định: Yêu cầu sở hữu một trong các vai trò: {roles_text} (hoặc Admin).",
                "admin_only": "🔴 Chỉ Quản trị viên (Admin Only): Chỉ Admin mới có quyền tạo lệnh."
            }.get(mode, "Chưa xác định")
            embed = discord.Embed(
                title="🛡️ CHƯƠNG 1: CẤU HÌNH PHÂN QUYỀN SERVER",
                description=f"Chế độ hiện tại: {mode_desc}\n\n"
                            f"Quy định hạn mức ký tự:\n"
                            f"• Từ khóa (Trigger): Tối đa {MAX_TRIGGER_LENGTH} ký tự.\n"
                            f"• Phản hồi (Response): Tối đa {MAX_RESPONSE_LENGTH} ký tự.\n"
                            f"• Không được bắt đầu bằng tiền tố lệnh bot ('!').",
                color=discord.Color.gold()
            )
        elif selected == "addcmd":
            embed = discord.Embed(
                title="➕ CHƯƠNG 2: TẠO LỆNH & BIẾN ĐỘNG THÔNG MINH",
                description="1. Cú pháp cơ bản:\n"
                            "> `!addcmd <từ_khóa> <nội_dung>`\n\n"
                            "2. Danh sách biến thay thế:\n"
                            "• `{user}` : Tag người gọi lệnh (@Alice)\n"
                            "• `{user.name}` : Tên tài khoản (Alice)\n"
                            "• `{server}` : Tên máy chủ\n"
                            "• `{server.members}` : Số lượng thành viên\n"
                            "• `{channel}` : Tag kênh kích hoạt\n"
                            "• `{random}` : Số ngẫu nhiên từ 1 đến 100\n"
                            "• `{random.1-50}` : Số ngẫu nhiên theo khoảng tùy chọn\n"
                            "• `{date}` / `{time}` : Ngày tháng / Giờ UTC hiện tại\n\n"
                            "3. Phản hồi ngẫu nhiên (Dấu '|'):\n"
                            "> `!addcmd 8ball Chắc chắn rồi! | Không bao giờ | Có thể đấy`\n\n"
                            "4. Dấu '|' nguyên văn (Dùng '||'):\n"
                            "> `!addcmd rules Gõ !help || !info để xem`",
                color=discord.Color.green()
            )
        elif selected == "advanced":
            embed = discord.Embed(
                title="⚡ CHƯƠNG 3: SO KHỚP KÍCH HOẠT & EMBED NÂNG CAO",
                description="Hệ thống hỗ trợ các cờ tùy chọn khi tạo hoặc sửa lệnh:\n\n"
                            "**🎯 1. Các kiểu so khớp (Match Types):**\n"
                            "• `--exact` (Mặc định): Khớp chính xác toàn bộ tin nhắn.\n"
                            "> `!addcmd ping Pong!`\n"
                            "• `--contains`: Kích hoạt khi tin nhắn chứa từ khóa ở bất kỳ vị trí nào.\n"
                            "> `!addcmd --contains discord Tham gia Discord tại {channel}`\n"
                            "• `--regex`: Kích hoạt theo biểu thức chính quy Regex.\n"
                            "> `!addcmd --regex \"^(hi|hello)\\b\" Xin chào {user}!`\n\n"
                            "**🎨 2. Định dạng phản hồi phong phú (Response Types):**\n"
                            "• `--text` (Mặc định): Tin nhắn văn bản thông thường.\n"
                            "• `--embed`: Phản hồi dưới dạng Discord Embed.\n"
                            "> `!addcmd --embed rule Quy tắc: Không spam tin nhắn!`\n"
                            "> `!addcmd --embed notice title: Thông Báo\\nNội dung chi tiết thông báo`",
                color=discord.Color.teal()
            )
        elif selected == "stats":
            embed = discord.Embed(
                title="📊 CHƯƠNG 4: QUẢN LÝ LỆNH & BẢNG XẾP HẠNG",
                description="• `!mycmd` : Xem danh sách các lệnh do chính bạn tạo trong server (có phân trang).\n"
                            "• `!cmdlist` : Xem toàn bộ danh sách lệnh có trong server.\n"
                            "• `!topcmds` : Bảng xếp hạng Top 10 câu lệnh được gọi nhiều nhất.\n"
                            "• `!cmdinfo <từ_khóa>` : Xem chi tiết thông số của một lệnh.",
                color=discord.Color.purple()
            )
        elif selected == "manage":
            embed = discord.Embed(
                title="✏️ CHƯƠNG 5: SỬA VÀ XÓA LỆNH",
                description="• `!editcmd <từ_khóa> <nội dung mới>` : Chỉnh sửa nội dung lệnh mà không mất lượt dùng.\n"
                            "• `!editcmd --embed <từ_khóa> <nội dung mới>` : Đổi định dạng sang Embed.\n"
                            "• `!delcmd <từ_khóa>` : Xóa lệnh khỏi server.\n\n"
                            "🔒 **Quy tắc sở hữu:** Bạn chỉ có thể sửa hoặc xóa lệnh do chính mình tạo ra. Quản trị viên (Admin) có quyền can thiệp vào mọi câu lệnh.",
                color=discord.Color.orange()
            )
        elif selected == "admin":
            embed = discord.Embed(
                title="👑 CHƯƠNG 6: BẢNG ĐIỀU KHIỂN & CÀI ĐẶT QUẢN TRỊ",
                description="Các lệnh cấu hình server dành riêng cho Quản trị viên:\n\n"
                            "• `!setup` : Mở bảng điều khiển tổng thể toàn bộ tính năng và cài đặt.\n"
                            "• `!setmode <everyone | role | admin>` : Thay đổi quyền ai được tạo lệnh.\n"
                            "• `!setrole @Role1 [@Role2...]` : Thiết lập danh sách role được tạo lệnh.\n"
                            "• `!setrole clear` : Xóa toàn bộ role đã cấp quyền.\n"
                            "• `!setchannel <#kênh | none>` : Giới hạn kênh bot phản hồi lệnh.",
                color=discord.Color.dark_red()
            )
        else:
            return
        await interaction.response.edit_message(embed=embed)


class GuideView(discord.ui.View):
    def __init__(self, author_id: int, settings: dict):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.message: Optional[discord.Message] = None
        self.add_item(GuideSelect(settings))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Bạn không thể thao tác trên cuốn sách của người khác! Hãy tự gõ '!cmdguide'.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# Main Cog
# ---------------------------------------------------------------------------

class CustomCommandsCog(commands.Cog, name="Custom Commands"):
    def __init__(self, bot: commands.Bot, db: DatabaseManager):
        self.bot = bot
        self.db = db
        # Per-user cooldown: 3 seconds between trigger activations
        self._trigger_cooldown: commands.CooldownMapping = commands.CooldownMapping.from_cooldown(
            1, 3.0, commands.BucketType.member
        )

    # ------------------------------------------------------------------
    # Command guidance helper
    # ------------------------------------------------------------------

    async def send_command_help(self, ctx: commands.Context, command_name: str) -> None:
        """Send an embed showing the command's exact syntax and usage examples."""
        info = COMMAND_GUIDE.get(command_name)
        prefix = ctx.prefix if isinstance(getattr(ctx, "prefix", None), str) else "!"
        if not info:
            cmd = self.bot.get_command(command_name)
            usage = f"{prefix}{command_name} {cmd.usage or ''}" if cmd else f"{prefix}{command_name}"
            await ctx.reply(f"💡 Cú pháp: `{usage.strip()}`", mention_author=False)
            return

        embed = discord.Embed(
            title=info["title"],
            description=info["desc"],
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="📌 Cú pháp chính xác:",
            value=f"`{info['syntax'].replace('!', prefix)}`",
            inline=False,
        )
        if info.get("examples"):
            examples_text = "\n".join([f"• `{ex.replace('!', prefix)}`" for ex in info["examples"]])
            embed.add_field(name="👉 Ví dụ mẫu:", value=examples_text, inline=False)
        embed.set_footer(text=f"Gõ {prefix}setup để mở bảng điều khiển • {prefix}cmdguide để xem cẩm nang!")
        await ctx.reply(embed=embed, mention_author=False)

    # ------------------------------------------------------------------
    # Global error handler for this cog
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if ctx.cog is not self:
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("⛔ Bạn không có quyền sử dụng lệnh này!", mention_author=False)
        elif isinstance(error, commands.UserInputError):
            cmd_name = ctx.command.name if ctx.command else ""
            if cmd_name in COMMAND_GUIDE:
                await self.send_command_help(ctx, cmd_name)
            else:
                prefix = ctx.prefix or "!"
                await ctx.reply(
                    f"⚠️ Cú pháp chưa chính xác: `{prefix}{ctx.command.qualified_name} {ctx.command.usage or ''}`",
                    mention_author=False,
                )
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.reply("❌ Lệnh này chỉ dùng được trong server!", mention_author=False)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"⏳ Vui lòng đợi {error.retry_after:.1f}s trước khi dùng lại lệnh này.",
                mention_author=False,
            )
        else:
            logger.error(f"Unhandled command error in {ctx.command}: {error}", exc_info=error)

    # ------------------------------------------------------------------
    # Channel resolver helper
    # ------------------------------------------------------------------

    async def _resolve_channel(self, ctx: commands.Context, text: str) -> Optional[Union[discord.TextChannel, discord.Thread]]:
        text_clean = text.strip()
        try:
            return await commands.TextChannelConverter().convert(ctx, text_clean)
        except Exception:
            clean_id = text_clean.replace("<#", "").replace(">", "").strip()
            if clean_id.isdigit():
                ch = ctx.guild.get_channel_or_thread(int(clean_id)) if hasattr(ctx.guild, "get_channel_or_thread") else ctx.guild.get_channel(int(clean_id))
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    return ch
            found = discord.utils.find(lambda c: c.name.lower() == text_clean.lower(), ctx.guild.text_channels)
            if found:
                return found
            if hasattr(ctx.guild, "threads"):
                return discord.utils.find(lambda t: t.name.lower() == text_clean.lower(), ctx.guild.threads)
            return None

    # ------------------------------------------------------------------
    # Permission check helper
    # ------------------------------------------------------------------

    async def check_user_permission(self, ctx: commands.Context) -> tuple[bool, str]:
        if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild:
            return True, ""
        settings = await self.db.get_guild_settings(ctx.guild.id)
        mode = settings.get("cmd_mode", "everyone")
        if mode == "everyone":
            return True, ""
        elif mode == "admin_only":
            return False, "Server này hiện chỉ cho phép Quản trị viên (Admin) tạo lệnh mới."
        elif mode == "role_only":
            allowed_role_ids = settings.get("allowed_role_ids", [])
            if not allowed_role_ids:
                return False, "Server đang ở chế độ 'role_only' nhưng chưa thiết lập vai trò nào được phép tạo lệnh. Vui lòng liên hệ Quản trị viên dùng '!setrole @Role'."
            user_role_ids = [r.id for r in ctx.author.roles]
            if not any(r_id in user_role_ids for r_id in allowed_role_ids):
                roles_text = ", ".join([f"<@&{r_id}>" for r_id in allowed_role_ids])
                return False, f"Server yêu cầu bạn phải sở hữu một trong các vai trò sau mới có thể tạo lệnh: {roles_text}."
        return True, ""

    # ------------------------------------------------------------------
    # Custom commands CRUD
    # ------------------------------------------------------------------

    @commands.command(name="addcmd", usage="[--contains|--regex|--exact] [--embed|--text] <từ_khóa> <nội dung>")
    @commands.guild_only()
    async def add_command(self, ctx: commands.Context, *, raw_args: Optional[str] = None):
        if not raw_args:
            await self.send_command_help(ctx, "addcmd")
            return

        trigger, response, match_type, response_type, error = parse_cmd_arguments(raw_args, default_match="exact", default_response="text")
        if error:
            await ctx.reply(f"❌ {error}", mention_author=False)
            return

        if not trigger or not response:
            await self.send_command_help(ctx, "addcmd")
            return

        allowed, reason = await self.check_user_permission(ctx)
        if not allowed:
            embed = discord.Embed(title="⛔ Không Đủ Quyền Hạn", description=reason, color=discord.Color.red())
            await ctx.reply(embed=embed, mention_author=False)
            return

        trigger_clean = trigger.strip().strip('"\'')
        response_clean = response.strip() if response else ""
        if not response_clean or not response_clean.strip('"\' '):
            await ctx.reply("⚠️ Nội dung phản hồi không được để trống.", mention_author=False)
            return
        if len(trigger_clean) > MAX_TRIGGER_LENGTH:
            await ctx.reply(f"⚠️ Từ khóa tối đa {MAX_TRIGGER_LENGTH} ký tự.", mention_author=False)
            return
        if len(response_clean) > MAX_RESPONSE_LENGTH:
            await ctx.reply(f"⚠️ Nội dung tối đa {MAX_RESPONSE_LENGTH} ký tự.", mention_author=False)
            return
        prefix = ctx.prefix if isinstance(ctx.prefix, (str, tuple)) else "!"
        if trigger_clean.startswith(prefix):
            await ctx.reply(f"⚠️ Từ khóa không được bắt đầu bằng prefix '{prefix}'.", mention_author=False)
            return

        # Validate regex syntax and safety if regex match type
        if match_type == "regex":
            is_safe, err_msg = is_safe_regex(trigger_clean)
            if not is_safe:
                await ctx.reply(f"❌ {err_msg}", mention_author=False)
                return

        success = await self.db.add_command(
            ctx.guild.id, ctx.author.id, trigger_clean, response_clean, match_type=match_type, response_type=response_type
        )
        if not success:
            await ctx.reply(f"❌ Từ khóa '{trigger_clean}' đã tồn tại trong server!", mention_author=False)
            return

        match_label = {
            "exact": "🎯 Khớp chính xác (Exact)",
            "contains": "🔍 Chứa từ khóa (Contains)",
            "regex": "⚡ Biểu thức Regex",
        }.get(match_type, match_type)

        response_label = {
            "text": "💬 Tin nhắn văn bản (Text)",
            "embed": "🎨 Discord Embed",
        }.get(response_type, response_type)

        embed = discord.Embed(
            title="✅ Tạo Custom Command Thành Công!",
            description=f"Bot sẽ tự động phản hồi khi phát hiện từ khóa '{trigger_clean}'.",
            color=discord.Color.green(),
        )
        embed.add_field(name="🔑 Từ khóa", value=f"`{trigger_clean}`", inline=True)
        embed.add_field(name="🎯 Cơ chế so khớp", value=match_label, inline=True)
        embed.add_field(name="📦 Định dạng phản hồi", value=response_label, inline=True)
        embed.add_field(name="👤 Người tạo", value=ctx.author.mention, inline=True)
        embed.add_field(name="💬 Nội dung phản hồi mẫu", value=response_clean[:200] + ("..." if len(response_clean) > 200 else ""), inline=False)
        embed.set_footer(text=f"Dùng {ctx.prefix}editcmd {trigger_clean} để sửa • {ctx.prefix}delcmd {trigger_clean} để xóa")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="editcmd", usage="[--contains|--regex|--exact] [--embed|--text] <từ_khóa> [nội dung mới]")
    @commands.guild_only()
    async def edit_command(self, ctx: commands.Context, *, raw_args: Optional[str] = None):
        if not raw_args:
            await self.send_command_help(ctx, "editcmd")
            return

        trigger, new_response, match_type, response_type, error = parse_cmd_arguments(
            raw_args, default_match=None, default_response=None
        )
        if error:
            await ctx.reply(f"❌ {error}", mention_author=False)
            return

        if not trigger:
            await self.send_command_help(ctx, "editcmd")
            return

        trigger_clean = trigger.strip().strip('"\'')
        cmd = await self.db.get_command_details(ctx.guild.id, trigger_clean)

        # Smart fallback: if command not found by first-word trigger, check if any existing
        # command has a multi-word trigger matching the prefix of the raw arguments
        if not cmd:
            all_cmds = await self.db.get_all_guild_commands(ctx.guild.id)
            cleaned_args, _, _, _ = _peel_flags(raw_args.strip(), match_type, response_type)
            for c in all_cmds:
                c_trig = c["trigger_word"]
                if cleaned_args.lower().startswith(c_trig.lower()):
                    after_trig = cleaned_args[len(c_trig):]
                    if not after_trig or after_trig[0].isspace():
                        cmd = c
                        trigger_clean = c_trig
                        rem_text = after_trig.strip()
                        if rem_text:
                            rem_text, match_type, response_type, err = _peel_flags(rem_text, match_type, response_type)
                            if err:
                                await ctx.reply(f"❌ {err}", mention_author=False)
                                return
                            new_response = rem_text if rem_text else None
                        else:
                            new_response = None
                        break

        if not cmd:
            await ctx.reply(f"🔍 Không tìm thấy lệnh '{trigger_clean}'.", mention_author=False)
            return

        # If user didn't specify a new response body, but did specify flags (e.g. `!editcmd --embed hi`),
        # keep the existing response text so format changes don't require retyping
        if not new_response:
            if match_type is not None or response_type is not None:
                new_response = cmd["response_text"]
            else:
                await self.send_command_help(ctx, "editcmd")
                return

        new_response_clean = new_response.strip()
        if not new_response_clean or not new_response_clean.strip('"\' '):
            await ctx.reply("⚠️ Nội dung phản hồi không được để trống.", mention_author=False)
            return

        is_owner = (cmd['user_id'] == ctx.author.id)
        is_admin = ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild
        if not (is_owner or is_admin):
            await ctx.reply("⛔ Bạn không thể sửa lệnh của thành viên khác!", mention_author=False)
            return

        if len(new_response_clean) > MAX_RESPONSE_LENGTH:
            await ctx.reply(f"⚠️ Nội dung tối đa {MAX_RESPONSE_LENGTH} ký tự.", mention_author=False)
            return

        effective_match = match_type if match_type is not None else (cmd.get("match_type") or "exact")
        if effective_match == "regex":
            is_safe, err_msg = is_safe_regex(trigger_clean)
            if not is_safe:
                await ctx.reply(f"❌ {err_msg}", mention_author=False)
                return

        updated = await self.db.edit_command(
            ctx.guild.id, trigger_clean, new_response_clean, match_type=match_type, response_type=response_type
        )
        if updated:
            effective_response_type = response_type if response_type is not None else (cmd.get("response_type") or "text")
            embed = discord.Embed(
                title="✏️ Đã Cập Nhật Lệnh Thành Công!",
                description=f"Từ khóa: `{trigger_clean}`\n"
                            f"Kiểu so khớp: **{effective_match}** | Định dạng: **{effective_response_type}**\n\n"
                            f"**Nội dung mới:**\n{new_response_clean}",
                color=discord.Color.blue(),
            )
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.reply(f"❌ Không thể cập nhật lệnh '{trigger_clean}'. Vui lòng thử lại sau.", mention_author=False)

    @commands.command(name="delcmd", usage="<từ_khóa>")
    @commands.guild_only()
    async def delete_command(self, ctx: commands.Context, *, trigger: Optional[str] = None):
        if not trigger:
            await self.send_command_help(ctx, "delcmd")
            return

        trigger_clean = trigger.strip().strip('"\'')
        cmd = await self.db.get_command_details(ctx.guild.id, trigger_clean)
        if not cmd:
            await ctx.reply(f"🔍 Không tìm thấy lệnh '{trigger_clean}'.", mention_author=False)
            return

        is_owner = (cmd['user_id'] == ctx.author.id)
        is_admin = ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild
        if not (is_owner or is_admin):
            await ctx.reply("⛔ Bạn không có quyền xóa lệnh này!", mention_author=False)
            return

        deleted = await self.db.delete_command(ctx.guild.id, trigger_clean)
        if deleted:
            role_note = "🛡️ *(Admin Override)*" if (is_admin and not is_owner) else "👤 *(Chính chủ xóa)*"
            await ctx.reply(f"🗑️ Đã xóa thành công lệnh '{trigger_clean}' {role_note}", mention_author=False)
        else:
            await ctx.reply(f"❌ Không thể xóa lệnh '{trigger_clean}'. Vui lòng thử lại sau.", mention_author=False)

    @commands.command(name="cmdinfo", aliases=["cmd", "commandinfo"], usage="<từ_khóa>")
    @commands.guild_only()
    async def command_info(self, ctx: commands.Context, *, trigger: Optional[str] = None):
        """View detailed information about a registered custom command."""
        if not trigger:
            await self.send_command_help(ctx, "cmdinfo")
            return

        trigger_clean = trigger.strip().strip('"\'')
        cmd = await self.db.get_command_details(ctx.guild.id, trigger_clean)
        if not cmd:
            await ctx.reply(f"🔍 Không tìm thấy thông tin lệnh '{trigger_clean}'.", mention_author=False)
            return

        match_label = {
            "exact": "🎯 Khớp chính xác (Exact)",
            "contains": "🔍 Chứa từ khóa (Contains)",
            "regex": "⚡ Biểu thức Regex",
        }.get(cmd.get("match_type") or "exact", "Exact")

        resp_label = {
            "text": "💬 Tin nhắn văn bản (Text)",
            "embed": "🎨 Discord Embed",
        }.get(cmd.get("response_type") or "text", "Text")

        embed = discord.Embed(
            title=f"🔍 Thông Tin Custom Command: '{cmd['trigger_word']}'",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🔑 Từ khóa kích hoạt", value=f"`{cmd['trigger_word']}`", inline=True)
        embed.add_field(name="🎯 Cơ chế so khớp", value=match_label, inline=True)
        embed.add_field(name="📦 Định dạng phản hồi", value=resp_label, inline=True)
        embed.add_field(name="👤 Người tạo", value=f"<@{cmd['user_id']}>", inline=True)
        embed.add_field(name="⚡ Số lượt sử dụng", value=f"**{cmd['uses']}** lần", inline=True)
        embed.add_field(name="📅 Ngày tạo", value=f"{cmd['created_at']}", inline=True)
        embed.add_field(name="💬 Nội dung phản hồi", value=f"```{cmd['response_text'][:1000]}```", inline=False)
        embed.set_footer(text=f"ID: {cmd['command_id']} • Dùng {ctx.prefix}editcmd để sửa")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="topcmds", aliases=["topcmd", "leaderboard"])
    @commands.guild_only()
    async def top_commands(self, ctx: commands.Context):
        top_list = await self.db.get_top_commands(ctx.guild.id, limit=10)
        if not top_list:
            await ctx.reply("📊 Server chưa có custom command nào được sử dụng!", mention_author=False)
            return

        embed = discord.Embed(
            title=f"🏆 Top Custom Commands Server: {ctx.guild.name}",
            description="Bảng xếp hạng những câu lệnh được sử dụng nhiều nhất:",
            color=discord.Color.gold(),
        )
        medals = ["🥇", "🥈", "🥉"]
        for idx, cmd in enumerate(top_list, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"#{idx}"
            response_preview = cmd['response_text'][:45]
            if len(cmd['response_text']) > 45:
                response_preview += "..."
            m_type = (cmd.get("match_type") or "exact").capitalize()
            r_type = (cmd.get("response_type") or "text").capitalize()
            embed.add_field(
                name=f"{rank} '{cmd['trigger_word']}' [{m_type} • {r_type}] — {cmd['uses']} lượt gọi",
                value=f"👤 Tạo bởi: <@{cmd['user_id']}>\n💬 {response_preview}",
                inline=False,
            )
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="mycmd", aliases=["mycmds", "mycommand"])
    @commands.guild_only()
    async def my_commands(self, ctx: commands.Context):
        """Display all custom commands created by the caller in this server."""
        cmds = await self.db.get_user_commands(ctx.guild.id, ctx.author.id)
        if not cmds:
            await ctx.reply(
                f"📋 Bạn chưa tạo custom command nào trong server này.\nDùng `{ctx.prefix}addcmd <từ_khóa> <nội_dung>` để tạo lệnh đầu tiên!",
                mention_author=False,
            )
            return

        chunk_size = 10
        chunks = [cmds[i:i + chunk_size] for i in range(0, len(cmds), chunk_size)]
        pages: List[discord.Embed] = []

        for page_idx, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"📋 Custom Commands Của {ctx.author.display_name}",
                description=f"Tổng số lệnh bạn đã tạo: **{len(cmds)}** lệnh.",
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            start_num = page_idx * chunk_size + 1
            for offset, cmd in enumerate(chunk):
                idx = start_num + offset
                response_preview = cmd['response_text'][:55]
                if len(cmd['response_text']) > 55:
                    response_preview += "..."
                m_type = (cmd.get("match_type") or "exact").capitalize()
                r_type = (cmd.get("response_type") or "text").capitalize()
                embed.add_field(
                    name=f"{idx}. '{cmd['trigger_word']}' [{m_type} • {r_type}] ({cmd['uses']} lượt dùng)",
                    value=f"💬 {response_preview}",
                    inline=False,
                )
            embed.set_footer(text=f"Trang {page_idx + 1}/{len(chunks)} • Dùng {ctx.prefix}editcmd để sửa, {ctx.prefix}delcmd để xóa")
            pages.append(embed)

        if len(pages) == 1:
            await ctx.reply(embed=pages[0], mention_author=False)
        else:
            view = PaginatorView(pages, ctx.author.id)
            msg = await ctx.reply(embed=pages[0], view=view, mention_author=False)
            view.message = msg

    @commands.command(name="cmdlist", aliases=["allcmds", "listcmds", "allcmd", "cmds"])
    @commands.guild_only()
    async def all_server_commands(self, ctx: commands.Context):
        """Display ALL custom commands registered in this server."""
        cmds = await self.db.get_all_guild_commands(ctx.guild.id)
        if not cmds:
            await ctx.reply(
                f"📜 Máy chủ **{ctx.guild.name}** chưa có câu lệnh tự động nào.\nDùng `{ctx.prefix}addcmd <từ_khóa> <nội_dung>` để tạo lệnh đầu tiên!",
                mention_author=False,
            )
            return

        chunk_size = 10
        chunks = [cmds[i:i + chunk_size] for i in range(0, len(cmds), chunk_size)]
        pages: List[discord.Embed] = []

        for page_idx, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"📜 Danh Sách Toàn Bộ Custom Commands: {ctx.guild.name}",
                description=f"Tổng cộng máy chủ có: **{len(cmds)}** câu lệnh tự động.",
                color=discord.Color.teal(),
            )
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
            start_num = page_idx * chunk_size + 1
            for offset, cmd in enumerate(chunk):
                idx = start_num + offset
                response_preview = cmd['response_text'][:50]
                if len(cmd['response_text']) > 50:
                    response_preview += "..."
                m_type = (cmd.get("match_type") or "exact").capitalize()
                r_type = (cmd.get("response_type") or "text").capitalize()
                embed.add_field(
                    name=f"#{idx}. '{cmd['trigger_word']}' [{m_type} • {r_type}] — ⚡ {cmd['uses']} lượt gọi",
                    value=f"👤 Tạo bởi: <@{cmd['user_id']}>\n💬 {response_preview}",
                    inline=False,
                )
            embed.set_footer(text=f"Trang {page_idx + 1}/{len(chunks)} • Gõ từ khóa để bot tự động phản hồi!")
            pages.append(embed)

        if len(pages) == 1:
            await ctx.reply(embed=pages[0], mention_author=False)
        else:
            view = PaginatorView(pages, ctx.author.id)
            msg = await ctx.reply(embed=pages[0], view=view, mention_author=False)
            view.message = msg

    @commands.command(name="cmdguide", aliases=["guide", "huongdan"])
    @commands.guild_only()
    async def cmd_guide(self, ctx: commands.Context):
        settings = await self.db.get_guild_settings(ctx.guild.id)
        embed = discord.Embed(
            title="📖 CẨM NANG HƯỚNG DẪN: DISCORD AUTO-RESPONSE BOT",
            description="Chào mừng bạn đến với Cẩm Nang Hướng Dẫn Tương Tác!\n"
                        "Hệ thống cho phép tạo lệnh tự động kèm biến `{user}`, `{server}`, `{random}`, ngẫu nhiên `|`, chế độ so khớp nâng cao và định dạng Embed.\n\n"
                        "👉 **Hãy chọn một chương từ Menu Dropdown bên dưới để bắt đầu:**",
            color=discord.Color.blue(),
        )
        view = GuideView(ctx.author.id, settings)
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

    # ------------------------------------------------------------------
    # Admin commands — Server configuration
    # ------------------------------------------------------------------

    @commands.command(name="setmode", usage="<everyone | role | admin>")
    @commands.has_permissions(administrator=True)
    async def set_mode(self, ctx: commands.Context, *, mode: Optional[str] = None):
        if not mode:
            await self.send_command_help(ctx, "setmode")
            return

        mode_clean = mode.lower().strip().replace(" ", "_").replace("-", "_")
        mapping = {
            "everyone": "everyone",
            "all": "everyone",
            "tat_ca": "everyone",
            "role": "role_only",
            "role_only": "role_only",
            "admin": "admin_only",
            "admin_only": "admin_only",
        }
        if mode_clean not in mapping:
            await self.send_command_help(ctx, "setmode")
            return

        db_mode = mapping[mode_clean]
        await self.db.update_guild_mode(ctx.guild.id, db_mode)
        mode_text = {
            "everyone": "🟢 Mọi người (Everyone) — Ai cũng có thể tạo lệnh",
            "role_only": "🟡 Chỉ Role chỉ định (Role Only) — Cần có role trong !setrole",
            "admin_only": "🔴 Chỉ Quản trị viên (Admin Only) — Chỉ Admin mới được tạo",
        }.get(db_mode, db_mode)
        await ctx.reply(f"✅ Đã đổi chế độ phân quyền server sang: **{mode_text}**!", mention_author=False)

    @commands.command(name="setrole", usage="<@Role1> [@Role2...] | clear")
    @commands.has_permissions(administrator=True)
    async def set_role(self, ctx: commands.Context, *args):
        if not args:
            await self.send_command_help(ctx, "setrole")
            return

        if args[0].lower() in ["clear", "none", "off", "reset", "xoa"]:
            await self.db.clear_guild_roles(ctx.guild.id)
            await ctx.reply("🗑️ Đã xóa toàn bộ vai trò được phép tạo lệnh (Chế độ hiện tại là `role_only` nhưng chưa gán role nào).", mention_author=False)
            return

        found_roles: List[discord.Role] = []
        seen_ids: set[int] = set()
        role_converter = commands.RoleConverter()
        for token in args:
            try:
                r = await role_converter.convert(ctx, token)
                if r.id not in seen_ids:
                    found_roles.append(r)
                    seen_ids.add(r.id)
            except Exception:
                clean_tok = token.replace("<@&", "").replace(">", "").strip()
                if clean_tok.isdigit():
                    r = ctx.guild.get_role(int(clean_tok))
                    if r and r.id not in seen_ids:
                        found_roles.append(r)
                        seen_ids.add(r.id)
                else:
                    r = discord.utils.find(lambda x: x.name.lower() == token.lower(), ctx.guild.roles)
                    if r and r.id not in seen_ids:
                        found_roles.append(r)
                        seen_ids.add(r.id)

        for r in ctx.message.role_mentions:
            if r.id not in seen_ids:
                found_roles.append(r)
                seen_ids.add(r.id)

        if not found_roles:
            await ctx.reply(
                "❌ Vui lòng tag hoặc cung cấp ít nhất một vai trò hợp lệ.\nVí dụ: `!setrole @Mod @Staff @VIP` hoặc `!setrole clear`",
                mention_author=False,
            )
            return

        role_ids = [r.id for r in found_roles]
        await self.db.set_guild_allowed_roles(ctx.guild.id, role_ids)
        roles_str = ", ".join([r.mention for r in found_roles])
        await ctx.reply(f"✅ Đã thiết lập các Role được phép tạo lệnh: {roles_str} (Chế độ tự động chuyển sang `role_only`)!", mention_author=False)

    @commands.command(name="setchannel", usage="<#channel | none>")
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx: commands.Context, *, channel: Optional[Union[discord.TextChannel, discord.Thread, str]] = None):
        if channel is None:
            await self.send_command_help(ctx, "setchannel")
            return

        if isinstance(channel, str) and channel.lower() in ("none", "off", "all", "tat", "clear", "reset"):
            await self.db.update_guild_channel(ctx.guild.id, None)
            await ctx.reply("✅ Đã gỡ giới hạn: Bot sẽ phản hồi trigger trong **tất cả các kênh**!", mention_author=False)
            return

        if isinstance(channel, str):
            resolved = await self._resolve_channel(ctx, channel)
            if not resolved:
                await ctx.reply(f"❌ Không tìm thấy kênh '{channel}'. Hãy tag kênh (ví dụ: '!setchannel #general') hoặc gõ '!setchannel none'.", mention_author=False)
                return
            channel = resolved

        await self.db.update_guild_channel(ctx.guild.id, channel.id)
        await ctx.reply(f"✅ Đã giới hạn: Bot chỉ phản hồi custom commands trong kênh **#{channel.name}**!", mention_author=False)

    # ------------------------------------------------------------------
    # Comprehensive Dashboard (!setup)
    # ------------------------------------------------------------------

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def server_setup(self, ctx: commands.Context):
        """Comprehensive management dashboard showing Auto-Response status and quick commands."""
        settings = await self.db.get_guild_settings(ctx.guild.id)
        cmd_count = await self.db.get_guild_command_count(ctx.guild.id)

        # Mode display
        mode = settings.get("cmd_mode", "everyone")
        mode_text = {
            "everyone": "🟢 Mọi người (Everyone)",
            "role_only": "🟡 Chỉ Role quy định (Role Only)",
            "admin_only": "🔴 Chỉ Quản trị viên (Admin Only)",
        }.get(mode, mode)

        # Allowed roles
        allowed_roles = settings.get("allowed_role_ids", [])
        if allowed_roles:
            role_mention = ", ".join([f"<@&{r_id}>" for r_id in allowed_roles])
        elif mode == "everyone":
            role_mention = "(Tất cả role)"
        else:
            role_mention = "*(Chưa đặt)*"

        # Channel mention
        ch_mention = f"<#{settings['cmd_channel_id']}>" if settings.get("cmd_channel_id") else "(Tất cả kênh)"

        embed = discord.Embed(
            title=f"⚙️ BẢNG ĐIỀU KHIỂN HỆ THỐNG AUTO-RESPONSE: {ctx.guild.name}",
            description="Tổng hợp trạng thái cấu hình tính năng Phản Hồi Tự Động (Auto-Response / Custom Commands):",
            color=discord.Color.purple(),
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        # Section 1: Core status
        embed.add_field(name="🔒 Quyền tạo lệnh (Mode)", value=mode_text, inline=True)
        embed.add_field(name="🎭 Role được tạo lệnh", value=role_mention, inline=True)
        embed.add_field(name="💬 Kênh Custom Cmds", value=ch_mention, inline=True)
        embed.add_field(name="📊 Tổng số lệnh server", value=f"**{cmd_count}** câu lệnh", inline=True)
        embed.add_field(name="⏱️ Cooldown kích hoạt", value="**3 giây** / thành viên", inline=True)
        embed.add_field(name="🛡️ Trạng thái an toàn", value="Hoạt động bình thường", inline=True)

        # Section 2: Quick action commands categorized
        p = ctx.prefix or "!"
        embed.add_field(
            name="💬 1. Lệnh Quản Lý Custom Commands:",
            value=f"`{p}addcmd <từ_khóa> <nội_dung>` : Tạo lệnh tự động mới\n"
                  f"`{p}editcmd <từ_khóa> <nội_dung>` : Sửa nội dung lệnh\n"
                  f"`{p}delcmd <từ_khóa>` : Xóa lệnh tùy chỉnh\n"
                  f"`{p}cmdinfo <từ_khóa>` : Xem chi tiết thông số lệnh\n"
                  f"`{p}mycmd` : Xem danh sách lệnh của chính bạn\n"
                  f"`{p}cmdlist` : Xem toàn bộ danh sách lệnh server\n"
                  f"`{p}topcmds` : Bảng xếp hạng Top 10 lệnh dùng nhiều nhất\n"
                  f"`{p}cmdguide` : Cuốn cẩm nang hướng dẫn chi tiết",
            inline=False,
        )
        embed.add_field(
            name="👑 2. Cài Đặt Server & Phân Quyền:",
            value=f"`{p}setmode <everyone|role|admin>` : Quyền ai được tạo lệnh\n"
                  f"`{p}setrole @Role1 [@Role2...]` : Đặt các role được phép tạo lệnh\n"
                  f"`{p}setrole clear` : Xóa toàn bộ role tạo lệnh\n"
                  f"`{p}setchannel <#kênh|none>` : Giới hạn kênh bot phản hồi lệnh",
            inline=False,
        )
        embed.add_field(
            name="⚡ 3. Cơ Chế So Khớp & Định Dạng Nâng Cao:",
            value=f"`--exact` : Khớp chính xác toàn bộ tin nhắn (Mặc định)\n"
                  f"`--contains` : Kích hoạt khi tin nhắn chứa từ khóa\n"
                  f"`--regex` : So khớp theo biểu thức chính quy Regex\n"
                  f"`--embed` : Phản hồi dưới dạng Discord Embed phong phú\n"
                  f"`--text` : Phản hồi dạng tin nhắn văn bản thông thường",
            inline=False,
        )
        embed.set_footer(text=f"Mẹo: Gõ trực tiếp tên lệnh (ví dụ '{p}addcmd') để nhận gợi ý cú pháp chi tiết!")
        await ctx.reply(embed=embed, mention_author=False)

    # ------------------------------------------------------------------
    # on_message — Auto-Response Custom Command Trigger
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Ignore messages starting with bot command prefix
        prefix = await self.bot.get_prefix(message)
        if isinstance(prefix, (list, tuple)):
            for p in prefix:
                if message.content.startswith(p):
                    return
        elif isinstance(prefix, str) and message.content.startswith(prefix):
            return

        content = message.content.strip()
        if not content:
            return

        settings = await self.db.get_guild_settings(message.guild.id)

        # Check channel restriction (including threads inside the channel)
        req_channel = settings.get("cmd_channel_id")
        if req_channel:
            parent_id = getattr(message.channel, "parent_id", None)
            if message.channel.id != req_channel and parent_id != req_channel:
                return

        # Check if user is currently on cooldown (without consuming tokens)
        bucket = self._trigger_cooldown.get_bucket(message)
        if bucket is not None and bucket.get_retry_after() > 0:
            return  # Silently ignore, user is on cooldown

        # Match command (supports exact, contains, regex)
        matched = await self.db.match_command_and_increment(message.guild.id, content)
        if matched:
            # Command matched: consume cooldown token now
            if bucket is not None:
                bucket.update_rate_limit()

            raw_response = matched["response_text"]
            response_type = matched.get("response_type") or "text"
            final_text = parse_placeholders(raw_response, message)
            if not final_text or not final_text.strip():
                return

            safe_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)

            try:
                if response_type == "embed":
                    embed = create_response_embed(final_text, message)
                    await message.channel.send(embed=embed, allowed_mentions=safe_mentions)
                else:
                    # Enforce Discord 2000-character plain text message boundary
                    if len(final_text) > 2000:
                        final_text = final_text[:1997] + "..."
                    await message.channel.send(final_text, allowed_mentions=safe_mentions)
            except discord.HTTPException as exc:
                logger.warning(f"Failed to send auto-response in {message.guild.id}/{message.channel.id}: {exc}")


async def setup(bot: commands.Bot):
    db: DatabaseManager = bot.db
    await bot.add_cog(CustomCommandsCog(bot, db))
    logger.info("Cog CustomCommandsCog loaded.")
