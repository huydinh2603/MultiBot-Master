import aiosqlite
import datetime
from typing import Optional, List, Dict, Any
from config import DATABASE_PATH

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Khởi tạo các bảng cơ sở dữ liệu nếu chưa tồn tại"""
        async with aiosqlite.connect(self.db_path) as db:
            # Tối ưu hóa SQLite cho môi trường ít RAM
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")

            # Bảng cài đặt máy chủ
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER,
                    mod_log_channel_id INTEGER,
                    welcome_channel_id INTEGER,
                    welcome_message TEXT DEFAULT 'Chào mừng {user} đã đến với **{server}**! Bạn là thành viên thứ #{member_count}.',
                    leave_channel_id INTEGER,
                    leave_message TEXT DEFAULT '**{user}** vừa rời khỏi máy chủ.',
                    autorole_id INTEGER,
                    verification_role_id INTEGER,
                    ticket_category_id INTEGER,
                    automod_enabled INTEGER DEFAULT 1,
                    anti_invite INTEGER DEFAULT 1,
                    anti_spam INTEGER DEFAULT 1,
                    anti_mass_mention INTEGER DEFAULT 1,
                    bad_words TEXT DEFAULT ''
                )
            """)

            # Bảng lưu trữ lịch sử cảnh cáo (Warnings)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Bảng lưu trữ Ticket hỗ trợ
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        """Lấy toàn bộ cấu hình của một máy chủ"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
            row = await cursor.fetchone()
            if row:
                return dict(row)
            
            # Nếu chưa có, tạo cấu hình mặc định
            await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
            
            cursor = await db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
            row = await cursor.fetchone()
            return dict(row) if row else {}

    async def update_guild_setting(self, guild_id: int, key: str, value: Any):
        """Cập nhật một trường cài đặt của máy chủ"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
            await db.execute(f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id))
            await db.commit()

    # --- Quản lý Cảnh cáo (Warnings) ---
    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        """Thêm một lần cảnh cáo cho người dùng"""
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (guild_id, user_id, moderator_id, reason, now))
            await db.commit()
            return cursor.lastrowid or 0

    async def get_warnings(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Lấy danh sách cảnh cáo của một người dùng"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT id, moderator_id, reason, created_at 
                FROM warnings 
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
            """, (guild_id, user_id))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        """Xóa toàn bộ cảnh cáo của một người dùng"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM warnings WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id))
            await db.commit()
            return cursor.rowcount

    # --- Quản lý Ticket ---
    async def create_ticket(self, guild_id: int, channel_id: int, user_id: int) -> int:
        """Lưu một ticket mới mở"""
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO tickets (guild_id, channel_id, user_id, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
            """, (guild_id, channel_id, user_id, now))
            await db.commit()
            return cursor.lastrowid or 0

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Tìm ticket bằng ID kênh"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def close_ticket(self, channel_id: int):
        """Cập nhật trạng thái ticket sang closed"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (channel_id,))
            await db.commit()

# Instance toàn cục để các cog dùng chung
db = Database()
