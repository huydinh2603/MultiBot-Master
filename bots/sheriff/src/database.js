import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Ensure data directory exists
const dataDir = path.join(__dirname, '..', 'data');
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const dbPath = path.join(dataDir, 'sheriff.db');
const db = new Database(dbPath);

// Enable WAL mode for better concurrency
db.pragma('journal_mode = WAL');

// Initialize schema
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    t_coin INTEGER DEFAULT 0,
    armor_tier INTEGER DEFAULT 0,
    armor_stars INTEGER DEFAULT 0,
    armor_durability INTEGER DEFAULT 0,
    armor_max_durability INTEGER DEFAULT 0,
    last_chat_reward INTEGER DEFAULT 0,
    immunity_until INTEGER DEFAULT 0,
    total_mute_given_seconds INTEGER DEFAULT 0,
    total_mute_received_seconds INTEGER DEFAULT 0,
    total_shots_fired INTEGER DEFAULT 0,
    total_shots_hit INTEGER DEFAULT 0,
    total_ricochets INTEGER DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS ammo_inventory (
    user_id TEXT,
    ammo_tier INTEGER,
    quantity INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, ammo_tier)
  );

  CREATE TABLE IF NOT EXISTS blacklisted_channels (
    channel_id TEXT PRIMARY KEY,
    guild_id TEXT,
    created_at INTEGER
  );
`);

// Prepared statement helpers
export const queries = {
  getUser: db.prepare(`SELECT * FROM users WHERE user_id = ?`),
  createUser: db.prepare(`INSERT OR IGNORE INTO users (user_id) VALUES (?)`),
  
  updateCoin: db.prepare(`UPDATE users SET t_coin = t_coin + ? WHERE user_id = ?`),
  setCoin: db.prepare(`UPDATE users SET t_coin = ? WHERE user_id = ?`),
  
  updateLastReward: db.prepare(`UPDATE users SET last_chat_reward = ? WHERE user_id = ?`),
  
  setArmor: db.prepare(`
    UPDATE users 
    SET armor_tier = ?, armor_stars = ?, armor_durability = ?, armor_max_durability = ? 
    WHERE user_id = ?
  `),
  
  updateArmorDurability: db.prepare(`
    UPDATE users 
    SET armor_durability = ? 
    WHERE user_id = ?
  `),

  repairArmor: db.prepare(`
    UPDATE users 
    SET armor_durability = ?, armor_max_durability = ? 
    WHERE user_id = ?
  `),

  setArmorStars: db.prepare(`
    UPDATE users 
    SET armor_stars = ? 
    WHERE user_id = ?
  `),

  setImmunity: db.prepare(`UPDATE users SET immunity_until = ? WHERE user_id = ?`),

  // Ammo inventory
  getAmmo: db.prepare(`SELECT ammo_tier, quantity FROM ammo_inventory WHERE user_id = ? AND ammo_tier = ?`),
  getAllAmmo: db.prepare(`SELECT ammo_tier, quantity FROM ammo_inventory WHERE user_id = ? ORDER BY ammo_tier ASC`),
  addAmmo: db.prepare(`
    INSERT INTO ammo_inventory (user_id, ammo_tier, quantity) 
    VALUES (?, ?, ?) 
    ON CONFLICT(user_id, ammo_tier) DO UPDATE SET quantity = quantity + excluded.quantity
  `),
  consumeAmmo: db.prepare(`
    UPDATE ammo_inventory 
    SET quantity = quantity - 1 
    WHERE user_id = ? AND ammo_tier = ? AND quantity > 0
  `),
  removeAmmo: db.prepare(`
    UPDATE ammo_inventory 
    SET quantity = MAX(0, quantity - ?) 
    WHERE user_id = ? AND ammo_tier = ?
  `),
  clearUserAmmo: db.prepare(`
    DELETE FROM ammo_inventory WHERE user_id = ?
  `),

  // Stats tracking
  recordShot: db.prepare(`
    UPDATE users 
    SET total_shots_fired = total_shots_fired + 1 
    WHERE user_id = ?
  `),
  recordHitGiven: db.prepare(`
    UPDATE users 
    SET total_shots_hit = total_shots_hit + 1, 
        total_mute_given_seconds = total_mute_given_seconds + ? 
    WHERE user_id = ?
  `),
  recordHitReceived: db.prepare(`
    UPDATE users 
    SET total_mute_received_seconds = total_mute_received_seconds + ? 
    WHERE user_id = ?
  `),
  recordRicochet: db.prepare(`
    UPDATE users 
    SET total_ricochets = total_ricochets + 1 
    WHERE user_id = ?
  `),

  // Leaderboard
  getTopCoins: db.prepare(`SELECT user_id, t_coin FROM users ORDER BY t_coin DESC LIMIT 10`),
  getTopDictators: db.prepare(`SELECT user_id, total_mute_given_seconds FROM users ORDER BY total_mute_given_seconds DESC LIMIT 10`),
  getTopVictims: db.prepare(`SELECT user_id, total_mute_received_seconds FROM users ORDER BY total_mute_received_seconds DESC LIMIT 10`),

  // Blacklist
  isChannelBlacklisted: db.prepare(`SELECT 1 FROM blacklisted_channels WHERE channel_id = ?`),
  addBlacklistChannel: db.prepare(`INSERT OR IGNORE INTO blacklisted_channels (channel_id, guild_id, created_at) VALUES (?, ?, ?)`),
  removeBlacklistChannel: db.prepare(`DELETE FROM blacklisted_channels WHERE channel_id = ?`),
  listBlacklistedChannels: db.prepare(`SELECT channel_id FROM blacklisted_channels WHERE guild_id = ?`),
};

/**
 * Get or create user record
 */
export function getUserData(userId) {
  let user = queries.getUser.get(userId);
  if (!user) {
    queries.createUser.run(userId);
    user = queries.getUser.get(userId);
  }
  return user;
}

export default db;
