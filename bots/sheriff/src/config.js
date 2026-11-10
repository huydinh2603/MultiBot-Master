// Configuration and Game Balance Constants for Sheriff Bot

export const ECONOMY = {
  // Chat-to-earn settings
  REWARD_COOLDOWN_MS: 10 * 1000, // 10 seconds cooldown between chat rewards
  MIN_MESSAGE_LENGTH: 4, // Minimum characters to count as valid message

  // Weighted random drops for T-Coin
  DROP_RATES: [
    { weight: 75, min: 1, max: 3 },   // 75% Common: 1 - 3 T-Coin
    { weight: 18, min: 4, max: 8 },   // 18% Uncommon: 4 - 8 T-Coin
    { weight: 6, min: 10, max: 20 },  // 6% Rare: 10 - 20 T-Coin
    { weight: 1, min: 30, max: 50 },  // 1% Jackpot: 30 - 50 T-Coin
  ],
};

export const COMBAT = {
  IMMUNITY_DURATION_MS: 30 * 1000, // 30 seconds immunity after mute expires
  PENALTY_MAX_DURABILITY_PERCENT: 0.05, // 5% max HP penalty on repair
};

// Ammo Specifications (B1 - B6)
export const AMMO = {
  B1: {
    tier: 1,
    name: 'Đạn T1',
    muteDurationMs: 10 * 60 * 1000, // 10 minutes
    muteLabel: '10 phút',
    price: 1000,
    baseWearDamage: 15, // Damage dealt to higher tier armor on ricochet
  },
  B2: {
    tier: 2,
    name: 'Đạn T2',
    muteDurationMs: 30 * 60 * 1000, // 30 minutes
    muteLabel: '30 phút',
    price: 3500,
    baseWearDamage: 25,
  },
  B3: {
    tier: 3,
    name: 'Đạn T3',
    muteDurationMs: 90 * 60 * 1000, // 1.5 hours
    muteLabel: '1.5 giờ',
    price: 8000,
    baseWearDamage: 40,
  },
  B4: {
    tier: 4,
    name: 'Đạn T4',
    muteDurationMs: 4 * 60 * 60 * 1000, // 4 hours
    muteLabel: '4 giờ',
    price: 22000,
    baseWearDamage: 60,
  },
  B5: {
    tier: 5,
    name: 'Đạn T5',
    muteDurationMs: 10 * 60 * 60 * 1000, // 10 hours
    muteLabel: '10 giờ',
    price: 50000,
    baseWearDamage: 85,
  },
  B6: {
    tier: 6,
    name: 'Đạn T6',
    muteDurationMs: 24 * 60 * 60 * 1000, // 24 hours (1 day)
    muteLabel: '24 giờ',
    price: 80000,
    baseWearDamage: 120,
  },
};

// Armor Specifications (A1 - A6)
export const ARMOR = {
  A1: {
    tier: 1,
    name: 'Giáp T1',
    maxDurability: 60,
    basePrice: 1500,
    upgradeCosts: {
      1: 800,  // Cost to upgrade from 0 to 1 star
      2: 1700, // Cost to upgrade from 1 to 2 star
      3: 2500, // Cost to upgrade from 2 to 3 star
    },
  },
  A2: {
    tier: 2,
    name: 'Giáp T2',
    maxDurability: 100,
    basePrice: 5000,
    upgradeCosts: {
      1: 2500,
      2: 5500,
      3: 8000,
    },
  },
  A3: {
    tier: 3,
    name: 'Giáp T3',
    maxDurability: 150,
    basePrice: 12000,
    upgradeCosts: {
      1: 6000,
      2: 14000,
      3: 20000,
    },
  },
  A4: {
    tier: 4,
    name: 'Giáp T4',
    maxDurability: 210,
    basePrice: 30000,
    upgradeCosts: {
      1: 15000,
      2: 35000,
      3: 50000,
    },
  },
  A5: {
    tier: 5,
    name: 'Giáp T5',
    maxDurability: 280,
    basePrice: 70000,
    upgradeCosts: {
      1: 35000,
      2: 75000,
      3: 110000,
    },
  },
  A6: {
    tier: 6,
    name: 'Giáp T6',
    maxDurability: 360,
    basePrice: 150000,
    upgradeCosts: {
      1: 75000,
      2: 155000,
      3: 230000,
    },
  },
};

// Star Modifiers: Durability damage resistance when ricocheting bullets
export const STAR_MODIFIERS = {
  0: 0.00, // 0% reduction
  1: 0.15, // 15% reduction
  2: 0.30, // 30% reduction
  3: 0.45, // 45% reduction
};
