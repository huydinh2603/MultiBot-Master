import { MessageFlags, SlashCommandBuilder } from 'discord.js';
import { AMMO, ARMOR } from '../config.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('buy')
  .setDescription('Mua nhanh đạn hoặc giáp')
  .addStringOption(option =>
    option
      .setName('item')
      .setDescription('Mã vật phẩm (B1 - B6 hoặc A1 - A6)')
      .setRequired(true)
      .addChoices(
        { name: 'B1 (Đạn T1 - 1,000 T)', value: 'B1' },
        { name: 'B2 (Đạn T2 - 3,500 T)', value: 'B2' },
        { name: 'B3 (Đạn T3 - 8,000 T)', value: 'B3' },
        { name: 'B4 (Đạn T4 - 22,000 T)', value: 'B4' },
        { name: 'B5 (Đạn T5 - 50,000 T)', value: 'B5' },
        { name: 'B6 (Đạn T6 - 80,000 T)', value: 'B6' },
        { name: 'A1 (Giáp T1 - 1,500 T)', value: 'A1' },
        { name: 'A2 (Giáp T2 - 5,000 T)', value: 'A2' },
        { name: 'A3 (Giáp T3 - 12,000 T)', value: 'A3' },
        { name: 'A4 (Giáp T4 - 30,000 T)', value: 'A4' },
        { name: 'A5 (Giáp T5 - 70,000 T)', value: 'A5' },
        { name: 'A6 (Giáp T6 - 150,000 T)', value: 'A6' }
      )
  )
  .addIntegerOption(option =>
    option
      .setName('amount')
      .setDescription('Số lượng (mặc định là 1, giáp luôn là 1)')
      .setMinValue(1)
      .setMaxValue(100)
  );

export async function execute(interaction) {
  const itemKey = interaction.options.getString('item').toUpperCase();
  const amount = interaction.options.getInteger('amount') || 1;
  const userId = interaction.user.id;
  const user = getUserData(userId);

  // Handle Ammo purchase (B1 - B6)
  if (itemKey.startsWith('B')) {
    const ammoConfig = AMMO[itemKey];
    if (!ammoConfig) {
      return interaction.reply({ content: 'Mã đạn không hợp lệ.', flags: MessageFlags.Ephemeral });
    }

    const totalCost = ammoConfig.price * amount;
    if (user.t_coin < totalCost) {
      return interaction.reply({
        content: `Không đủ T-Coin. Bạn cần ${totalCost.toLocaleString('en-US')} T-Coin nhưng hiện chỉ có ${user.t_coin.toLocaleString('en-US')} T-Coin.`,
        flags: MessageFlags.Ephemeral,
      });
    }

    queries.updateCoin.run(-totalCost, userId);
    queries.addAmmo.run(userId, ammoConfig.tier, amount);

    return interaction.reply({
      content: `Đã mua thành công x${amount} ${ammoConfig.name} với giá ${totalCost.toLocaleString('en-US')} T-Coin.`,
      flags: MessageFlags.Ephemeral,
    });
  }

  // Handle Armor purchase (A1 - A6)
  if (itemKey.startsWith('A')) {
    const armorConfig = ARMOR[itemKey];
    if (!armorConfig) {
      return interaction.reply({ content: 'Mã giáp không hợp lệ.', flags: MessageFlags.Ephemeral });
    }

    if (amount > 1) {
      return interaction.reply({ content: 'Mỗi lần chỉ có thể trang bị 1 bộ giáp.', flags: MessageFlags.Ephemeral });
    }

    const totalCost = armorConfig.basePrice;
    if (user.t_coin < totalCost) {
      return interaction.reply({
        content: `Không đủ T-Coin. Bạn cần ${totalCost.toLocaleString('en-US')} T-Coin nhưng hiện chỉ có ${user.t_coin.toLocaleString('en-US')} T-Coin.`,
        flags: MessageFlags.Ephemeral,
      });
    }

    queries.updateCoin.run(-totalCost, userId);
    // Equip new armor with 0 stars and full durability
    queries.setArmor.run(
      armorConfig.tier,
      0, // 0 stars initially
      armorConfig.maxDurability,
      armorConfig.maxDurability,
      userId
    );

    return interaction.reply({
      content: `Đã mua và trang bị ${armorConfig.name} (${armorConfig.maxDurability} HP) với giá ${totalCost.toLocaleString('en-US')} T-Coin.`,
      flags: MessageFlags.Ephemeral,
    });
  }

  return interaction.reply({ content: 'Mã vật phẩm không hợp lệ.', flags: MessageFlags.Ephemeral });
}
