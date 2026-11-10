import { ECONOMY } from '../config.js';
import { getUserData, queries } from '../database.js';

/**
 * Roll a weighted random coin drop
 */
function rollCoinDrop() {
  const rand = Math.random() * 100;
  let cumulative = 0;

  for (const tier of ECONOMY.DROP_RATES) {
    cumulative += tier.weight;
    if (rand < cumulative) {
      // Pick random integer between min and max
      return Math.floor(Math.random() * (tier.max - tier.min + 1)) + tier.min;
    }
  }

  return 1;
}

/**
 * Handle incoming message for chat-to-earn
 * Returns the amount earned, or 0 if not eligible
 */
export function handleChatMessage(message) {
  if (message.author.bot || !message.guild) return 0;

  // Check channel blacklist
  if (queries.isChannelBlacklisted.get(message.channel.id)) {
    return 0;
  }

  // Check minimum message length
  const content = message.content.trim();
  if (content.length < ECONOMY.MIN_MESSAGE_LENGTH) {
    return 0;
  }

  const now = Date.now();
  const user = getUserData(message.author.id);

  // Check reward cooldown (10s)
  if (now - user.last_chat_reward < ECONOMY.REWARD_COOLDOWN_MS) {
    return 0;
  }

  // Roll and add coins
  const coinsEarned = rollCoinDrop();
  queries.updateCoin.run(coinsEarned, message.author.id);
  queries.updateLastReward.run(now, message.author.id);

  return coinsEarned;
}
