import time
import asyncio
import aiosqlite
import logging
import re
from typing import Optional, List, Dict, Any

logger = logging.getLogger("DiscordBot.Database")
DB_FILE = "bot_custom_commands.db"



def has_nested_quantifiers(pattern: str) -> bool:
    """Detect catastrophic ReDoS nested quantifier structures like (a+)+, ((a+))+, (a+)*, ([0-9]+)+."""
    cleaned = ''
    i = 0
    while i < len(pattern):
        if pattern[i] == '\\':
            cleaned += '  '
            i += 2
        else:
            cleaned += pattern[i]
            i += 1

    masked = re.sub(r'\[[^\]]*\]', lambda m: '[' + ' ' * (len(m.group(0)) - 2) + ']', cleaned)

    stack = []
    for idx, ch in enumerate(masked):
        if ch == '(':
            stack.append(idx)
        elif ch == ')' and stack:
            open_idx = stack.pop()
            rest = masked[idx + 1:].lstrip()
            if rest and rest[0] in ('+', '*', '{'):
                inside = masked[open_idx + 1:idx]
                if any(q in inside for q in ('+', '*', '{')):
                    return True
    return False


class DatabaseManager:
    """Async SQLite manager with persistent connection and in-memory cache
    dedicated to Auto-Response custom commands and guild configurations.
    """

    CACHE_TTL_SECONDS = 30

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._connect_lock = asyncio.Lock()
        # guild_settings cache: server_id → (settings_dict, monotonic_timestamp)
        self._settings_cache: Dict[int, tuple[Dict[str, Any], float]] = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _get_db(self) -> aiosqlite.Connection:
        """Return the persistent connection, creating it if needed."""
        if self._db is not None:
            return self._db
        async with self._connect_lock:
            if self._db is not None:
                return self._db
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA busy_timeout = 5000;")
            self._db = db
            return self._db

    async def close(self) -> None:
        """Close the persistent connection. Call on bot shutdown."""
        if self._db is not None:
            try:
                await self._db.close()
            except Exception as exc:
                logger.warning(f"Error closing database: {exc}")
            finally:
                self._db = None
                self._settings_cache.clear()
            logger.info("Database connection closed.")

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_get(self, server_id: int) -> Optional[Dict[str, Any]]:
        entry = self._settings_cache.get(server_id)
        if entry is None:
            return None
        settings, ts = entry
        if time.monotonic() - ts > self.CACHE_TTL_SECONDS:
            del self._settings_cache[server_id]
            return None
        copy_settings = settings.copy()
        if "allowed_role_ids" in copy_settings and isinstance(copy_settings["allowed_role_ids"], list):
            copy_settings["allowed_role_ids"] = list(copy_settings["allowed_role_ids"])
        return copy_settings

    def _cache_set(self, server_id: int, settings: Dict[str, Any]) -> None:
        copy_settings = settings.copy()
        if "allowed_role_ids" in copy_settings and isinstance(copy_settings["allowed_role_ids"], list):
            copy_settings["allowed_role_ids"] = list(copy_settings["allowed_role_ids"])
        self._settings_cache[server_id] = (copy_settings, time.monotonic())

    def invalidate_cache(self, server_id: int) -> None:
        """Remove cached settings for a guild (call after any update)."""
        self._settings_cache.pop(server_id, None)

    # ------------------------------------------------------------------
    # Schema initialisation and migration
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        db = await self._get_db()

        # 1. Clean up obsolete trap tables and indexes if they exist
        await db.execute("DROP TABLE IF EXISTS trap_channels;")
        await db.execute("DROP TABLE IF EXISTS trap_whitelist_roles;")
        await db.execute("DROP INDEX IF EXISTS idx_trap_server;")
        await db.execute("DROP INDEX IF EXISTS idx_trap_channel_server;")

        # 2. Check guild_settings schema and purge legacy trap columns if present
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guild_settings'") as cursor:
            table_exists = await cursor.fetchone()

        if table_exists:
            async with db.execute("PRAGMA table_info(guild_settings)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
            if "trap_channel_id" in columns or "trap_alert_channel_id" in columns:
                logger.info("Purging legacy trap columns from guild_settings...")
                await db.execute("DROP TABLE IF EXISTS guild_settings_clean;")
                await db.execute("""
                CREATE TABLE guild_settings_clean (
                    server_id INTEGER PRIMARY KEY,
                    cmd_mode TEXT NOT NULL DEFAULT 'everyone',
                    allowed_role_id INTEGER DEFAULT NULL,
                    cmd_channel_id INTEGER DEFAULT NULL,
                    cooldown_seconds INTEGER NOT NULL DEFAULT 3,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );
                """)
                common_cols = [c for c in ["server_id", "cmd_mode", "allowed_role_id", "cmd_channel_id", "cooldown_seconds", "updated_at"] if c in columns]
                cols_str = ", ".join(common_cols)
                await db.execute(f"INSERT INTO guild_settings_clean ({cols_str}) SELECT {cols_str} FROM guild_settings;")
                await db.execute("DROP TABLE guild_settings;")
                await db.execute("ALTER TABLE guild_settings_clean RENAME TO guild_settings;")
                logger.info("guild_settings successfully purged of trap columns.")
            else:
                if "cooldown_seconds" not in columns:
                    await db.execute("ALTER TABLE guild_settings ADD COLUMN cooldown_seconds INTEGER NOT NULL DEFAULT 3;")
                if "updated_at" not in columns:
                    await db.execute("ALTER TABLE guild_settings ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'));")
        else:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                server_id INTEGER PRIMARY KEY,
                cmd_mode TEXT NOT NULL DEFAULT 'everyone',
                allowed_role_id INTEGER DEFAULT NULL,
                cmd_channel_id INTEGER DEFAULT NULL,
                cooldown_seconds INTEGER NOT NULL DEFAULT 3,
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """)

        # 3. Create guild_allowed_roles table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS guild_allowed_roles (
            server_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            added_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (server_id, role_id)
        );
        """)

        # 4. Create custom_commands table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS custom_commands (
            command_id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            trigger_word TEXT NOT NULL COLLATE NOCASE,
            response_text TEXT NOT NULL,
            match_type TEXT NOT NULL DEFAULT 'exact',
            response_type TEXT NOT NULL DEFAULT 'text',
            uses INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE(server_id, trigger_word COLLATE NOCASE)
        );
        """)

        # 5. Ensure match_type, response_type, and uses columns exist in custom_commands
        async with db.execute("PRAGMA table_info(custom_commands)") as cursor:
            cc_columns = [row[1] for row in await cursor.fetchall()]

        if "match_type" not in cc_columns:
            await db.execute("ALTER TABLE custom_commands ADD COLUMN match_type TEXT NOT NULL DEFAULT 'exact';")
        if "response_type" not in cc_columns:
            await db.execute("ALTER TABLE custom_commands ADD COLUMN response_type TEXT NOT NULL DEFAULT 'text';")
        if "uses" not in cc_columns:
            await db.execute("ALTER TABLE custom_commands ADD COLUMN uses INTEGER NOT NULL DEFAULT 0;")

        # 6. Create performance indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_trigger ON custom_commands (server_id, trigger_word COLLATE NOCASE);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_match ON custom_commands (server_id, match_type);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_user ON custom_commands (server_id, user_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_uses ON custom_commands (server_id, uses DESC);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_allowed_server ON guild_allowed_roles (server_id);")

        await db.commit()
        logger.info("Database initialized for Auto-Response.")

    # ------------------------------------------------------------------
    # Guild settings
    # ------------------------------------------------------------------

    async def get_guild_settings(self, server_id: int) -> Dict[str, Any]:
        cached = self._cache_get(server_id)
        if cached is not None:
            return cached

        db = await self._get_db()
        query = "SELECT server_id, cmd_mode, allowed_role_id, cmd_channel_id, cooldown_seconds FROM guild_settings WHERE server_id = ?"
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (server_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                settings = dict(row)
            else:
                await db.execute(
                    "INSERT OR IGNORE INTO guild_settings (server_id, cmd_mode, allowed_role_id, cmd_channel_id, cooldown_seconds) VALUES (?, 'everyone', NULL, NULL, 3)",
                    (server_id,),
                )
                await db.commit()
                settings = {
                    "server_id": server_id,
                    "cmd_mode": "everyone",
                    "allowed_role_id": None,
                    "cmd_channel_id": None,
                    "cooldown_seconds": 3,
                }
        async with db.execute("SELECT role_id FROM guild_allowed_roles WHERE server_id = ?", (server_id,)) as cursor:
            roles = await cursor.fetchall()
            allowed_roles = [r[0] for r in roles]
            if not allowed_roles and settings.get("allowed_role_id"):
                allowed_roles = [settings["allowed_role_id"]]
            settings["allowed_role_ids"] = allowed_roles

        self._cache_set(server_id, settings)
        return settings.copy()

    async def update_guild_mode(self, server_id: int, mode: str) -> None:
        query = "INSERT INTO guild_settings (server_id, cmd_mode) VALUES (?, ?) ON CONFLICT(server_id) DO UPDATE SET cmd_mode = excluded.cmd_mode, updated_at = datetime('now', 'localtime')"
        db = await self._get_db()
        await db.execute(query, (server_id, mode))
        await db.commit()
        self.invalidate_cache(server_id)

    async def set_guild_allowed_roles(self, server_id: int, role_ids: List[int]) -> None:
        first_role = role_ids[0] if role_ids else None
        db = await self._get_db()
        await db.execute("DELETE FROM guild_allowed_roles WHERE server_id = ?", (server_id,))
        for r_id in role_ids:
            await db.execute("INSERT OR IGNORE INTO guild_allowed_roles (server_id, role_id) VALUES (?, ?)", (server_id, r_id))
        query = "INSERT INTO guild_settings (server_id, allowed_role_id, cmd_mode) VALUES (?, ?, 'role_only') ON CONFLICT(server_id) DO UPDATE SET allowed_role_id = excluded.allowed_role_id, cmd_mode = 'role_only', updated_at = datetime('now', 'localtime')"
        await db.execute(query, (server_id, first_role))
        await db.commit()
        self.invalidate_cache(server_id)

    async def clear_guild_roles(self, server_id: int) -> None:
        db = await self._get_db()
        await db.execute("DELETE FROM guild_allowed_roles WHERE server_id = ?", (server_id,))
        query = "INSERT INTO guild_settings (server_id, allowed_role_id) VALUES (?, NULL) ON CONFLICT(server_id) DO UPDATE SET allowed_role_id = NULL, updated_at = datetime('now', 'localtime')"
        await db.execute(query, (server_id,))
        await db.commit()
        self.invalidate_cache(server_id)

    async def clear_guild_allowed_roles(self, server_id: int) -> None:
        await self.clear_guild_roles(server_id)

    async def update_guild_role(self, server_id: int, role_id: Optional[int]) -> None:
        if role_id is not None:
            await self.set_guild_allowed_roles(server_id, [role_id])
        else:
            await self.clear_guild_roles(server_id)

    async def update_guild_channel(self, server_id: int, channel_id: Optional[int]) -> None:
        query = "INSERT INTO guild_settings (server_id, cmd_channel_id) VALUES (?, ?) ON CONFLICT(server_id) DO UPDATE SET cmd_channel_id = excluded.cmd_channel_id, updated_at = datetime('now', 'localtime')"
        db = await self._get_db()
        await db.execute(query, (server_id, channel_id))
        await db.commit()
        self.invalidate_cache(server_id)

    async def is_role_command_allowed(self, server_id: int, role_ids: List[int]) -> bool:
        if not role_ids:
            return False
        placeholders = ",".join(["?"] * len(role_ids))
        query = f"SELECT 1 FROM guild_allowed_roles WHERE server_id = ? AND role_id IN ({placeholders}) LIMIT 1"
        db = await self._get_db()
        async with db.execute(query, [server_id, *role_ids]) as cursor:
            row = await cursor.fetchone()
            return row is not None

    # ------------------------------------------------------------------
    # Custom commands CRUD & Matching
    # ------------------------------------------------------------------

    async def add_command(
        self,
        server_id: int,
        user_id: int,
        trigger: str,
        response: str,
        match_type: str = "exact",
        response_type: str = "text",
    ) -> bool:
        """Register a new auto-response command."""
        valid_match_types = {"exact", "contains", "regex"}
        valid_response_types = {"text", "embed"}
        m_type = match_type.lower().strip() if match_type else "exact"
        r_type = response_type.lower().strip() if response_type else "text"
        if m_type not in valid_match_types:
            m_type = "exact"
        if r_type not in valid_response_types:
            r_type = "text"

        query = """
        INSERT INTO custom_commands (server_id, user_id, trigger_word, response_text, match_type, response_type, uses, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, datetime('now', 'localtime'))
        """
        try:
            db = await self._get_db()
            await db.execute(query, (server_id, user_id, trigger.strip(), response, m_type, r_type))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def edit_command(
        self,
        server_id: int,
        trigger: str,
        new_response: Optional[str] = None,
        match_type: Optional[str] = None,
        response_type: Optional[str] = None,
    ) -> bool:
        """Update an existing auto-response command's response and/or options."""
        db = await self._get_db()
        params: List[Any] = []
        set_clauses: List[str] = []

        if new_response is not None:
            set_clauses.append("response_text = ?")
            params.append(new_response)

        if match_type is not None:
            m_type = match_type.lower().strip()
            if m_type in {"exact", "contains", "regex"}:
                set_clauses.append("match_type = ?")
                params.append(m_type)

        if response_type is not None:
            r_type = response_type.lower().strip()
            if r_type in {"text", "embed"}:
                set_clauses.append("response_type = ?")
                params.append(r_type)

        if not set_clauses:
            return True

        params.extend([server_id, trigger.strip()])
        query = f"UPDATE custom_commands SET {', '.join(set_clauses)} WHERE server_id = ? AND trigger_word = ? COLLATE NOCASE"
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.rowcount > 0

    async def match_command_and_increment(self, server_id: int, message_content: str) -> Optional[Dict[str, Any]]:
        """Find the best matching custom command for message_content and increment its uses counter.

        Matching priority:
        1. Exact match (match_type = 'exact')
        2. Contains match (match_type = 'contains', longest trigger first)
        3. Regex match (match_type = 'regex')

        Returns dict of command fields or None if no match.
        """
        db = await self._get_db()
        db.row_factory = aiosqlite.Row
        content_clean = message_content.strip()
        if not content_clean:
            return None

        # 1. Exact match
        query_exact = """
        SELECT command_id, user_id, trigger_word, response_text, match_type, response_type, uses, created_at
        FROM custom_commands
        WHERE server_id = ? AND (match_type = 'exact' OR match_type IS NULL) AND trigger_word = ? COLLATE NOCASE
        LIMIT 1
        """
        async with db.execute(query_exact, (server_id, content_clean)) as cursor:
            row = await cursor.fetchone()
            if row:
                cmd = dict(row)
                await db.execute("UPDATE custom_commands SET uses = uses + 1 WHERE command_id = ?", (cmd["command_id"],))
                await db.commit()
                cmd["uses"] += 1
                return cmd

        # 2. Contains and Regex matches
        query_others = """
        SELECT command_id, user_id, trigger_word, response_text, match_type, response_type, uses, created_at
        FROM custom_commands
        WHERE server_id = ? AND match_type IN ('contains', 'regex')
        ORDER BY CASE WHEN match_type = 'contains' THEN LENGTH(trigger_word) ELSE 0 END DESC, command_id ASC
        """
        async with db.execute(query_others, (server_id,)) as cursor:
            rows = await cursor.fetchall()
            candidates = [dict(r) for r in rows]

        # Check contains first
        for cmd in candidates:
            if cmd["match_type"] == "contains":
                trigger_lower = cmd["trigger_word"].lower()
                if trigger_lower in content_clean.lower():
                    await db.execute("UPDATE custom_commands SET uses = uses + 1 WHERE command_id = ?", (cmd["command_id"],))
                    await db.commit()
                    cmd["uses"] += 1
                    return cmd

        # Check regex next
        for cmd in candidates:
            if cmd["match_type"] == "regex":
                trigger_pattern = cmd["trigger_word"]
                # Skip patterns with catastrophic ReDoS nested quantifiers
                if has_nested_quantifiers(trigger_pattern):
                    logger.warning(f"Skipping ReDoS-prone regex in cmd {cmd['command_id']} ('{trigger_pattern}')")
                    continue
                try:
                    pattern = re.compile(trigger_pattern, re.IGNORECASE)
                    if pattern.search(content_clean):
                        await db.execute("UPDATE custom_commands SET uses = uses + 1 WHERE command_id = ?", (cmd["command_id"],))
                        await db.commit()
                        cmd["uses"] += 1
                        return cmd
                except Exception as e:
                    logger.warning(f"Invalid regex trigger in cmd {cmd['command_id']} ('{trigger_pattern}'): {e}")
                    continue

        return None

    async def get_response_and_increment(self, server_id: int, trigger: str) -> Optional[str]:
        """Legacy helper: returns response_text of matching command (incrementing uses)."""
        matched = await self.match_command_and_increment(server_id, trigger)
        return matched["response_text"] if matched else None

    async def get_top_commands(self, server_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
        SELECT command_id, user_id, trigger_word, response_text, match_type, response_type, uses, created_at
        FROM custom_commands
        WHERE server_id = ?
        ORDER BY uses DESC, command_id DESC
        LIMIT ?
        """
        db = await self._get_db()
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (server_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_command_details(self, server_id: int, trigger: str) -> Optional[Dict[str, Any]]:
        query = """
        SELECT command_id, user_id, trigger_word, response_text, match_type, response_type, uses, created_at
        FROM custom_commands
        WHERE server_id = ? AND trigger_word = ? COLLATE NOCASE
        LIMIT 1
        """
        db = await self._get_db()
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (server_id, trigger.strip())) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_commands(self, server_id: int, user_id: int) -> List[Dict[str, Any]]:
        query = """
        SELECT command_id, trigger_word, response_text, match_type, response_type, uses, created_at
        FROM custom_commands
        WHERE server_id = ? AND user_id = ?
        ORDER BY command_id DESC
        """
        db = await self._get_db()
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (server_id, user_id)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete_command(self, server_id: int, trigger: str) -> bool:
        query = "DELETE FROM custom_commands WHERE server_id = ? AND trigger_word = ? COLLATE NOCASE"
        db = await self._get_db()
        cursor = await db.execute(query, (server_id, trigger.strip()))
        await db.commit()
        return cursor.rowcount > 0

    async def get_all_guild_commands(self, server_id: int) -> List[Dict[str, Any]]:
        """Fetch all custom commands registered in a guild, sorted by uses descending."""
        query = """
        SELECT command_id, user_id, trigger_word, response_text, match_type, response_type, uses, created_at
        FROM custom_commands
        WHERE server_id = ?
        ORDER BY uses DESC, command_id DESC
        """
        db = await self._get_db()
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (server_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_guild_command_count(self, server_id: int) -> int:
        """Count total custom commands in a guild."""
        query = "SELECT COUNT(*) FROM custom_commands WHERE server_id = ?"
        db = await self._get_db()
        async with db.execute(query, (server_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
