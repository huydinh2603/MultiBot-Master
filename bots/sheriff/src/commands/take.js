import { MessageFlags, PermissionFlagsBits, SlashCommandBuilder } from 'discord.js';
import { AMMO } from '../config.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('take')
  .setDescription('Tước bỏ T-Coin, đạn hoặc giáp của người dùng (Chỉ Chủ Server)')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addUserOption(opt =>
    opt
      .setName('user')
      .setDescription('Người bị tước bỏ')
      .setRequired(true)
  )
  .addStringOption(opt =>
    opt
      .setName('item')
      .setDescription('Mục tiêu tước bỏ')
      .setRequired(true)
      .addChoices(
        { name: 'T-Coin', value: 'coin' },
        { name: 'Giáp đang mặc (Lột giáp)', value: 'armor' },
        { name: 'B1 (Đạn T1)', value: 'B1' },
        { name: 'B2 (Đạn T2)', value: 'B2' },
        { name: 'B3 (Đạn T3)', value: 'B3' },
        { name: 'B4 (Đạn T4)', value: 'B4' },
        { name: 'B5 (Đạn T5)', value: 'B5' },
        { name: 'B6 (Đạn T6)', value: 'B6' },
        { name: 'Toàn bộ tài sản (Reset)', value: 'all' }
      )
  )
  .addIntegerOption(opt =>
    opt
      .setName('amount')
      .setDescription('Số lượng (coin hoặc đạn, để trống để tước hết loại đó)')
      .setMinValue(1)
  );

export async function execute(interaction) {
  // Kiểm tra nghiêm ngặt quyền Chủ Server
  const ownerId = interaction.guild?.ownerId || (await interaction.guild?.fetchOwner().catch(() => null))?.id;
  if (!ownerId || interaction.user.id !== ownerId) {
    return interaction.reply({
      content: 'Chỉ Chủ Server (Server Owner) mới có quyền sử dụng lệnh này.',
      flags: MessageFlags.Ephemeral,
    });
  }

  const targetUser = interaction.options.getUser('user');
  const itemKey = interaction.options.getString('item');
  const amount = interaction.options.getInteger('amount');

  const user = getUserData(targetUser.id);

  // 1. Take T-Coin
  if (itemKey === 'coin') {
    const deductAmount = amount || user.t_coin;
    queries.updateCoin.run(-deductAmount, targetUser.id);
    const updated = getUserData(targetUser.id);
    return interaction.reply({
      content: `Đã tước bỏ ${deductAmount.toLocaleString('en-US')} T-Coin của <@${targetUser.id}>. Số dư còn lại: ${updated.t_coin.toLocaleString('en-US')} T.`,
    });
  }

  // 2. Strip Armor
  if (itemKey === 'armor') {
    if (user.armor_tier === 0) {
      return interaction.reply({
        content: `<@${targetUser.id}> hiện không mặc giáp.`,
        flags: MessageFlags.Ephemeral,
      });
    }

    const oldTier = user.armor_tier;
    queries.setArmor.run(0, 0, 0, 0, targetUser.id);
    return interaction.reply({
      content: `Đã tước bỏ Giáp Tier ${oldTier} của <@${targetUser.id}>.`,
    });
  }

  // 3. Take Ammo (B1 - B6)
  if (itemKey.startsWith('B')) {
    const ammoConfig = AMMO[itemKey];
    if (!ammoConfig) {
      return interaction.reply({ content: 'Mã đạn không hợp lệ.', flags: MessageFlags.Ephemeral });
    }

    const currentStock = queries.getAmmo.get(targetUser.id, ammoConfig.tier);
    const currentQty = currentStock ? currentStock.quantity : 0;
    const deductQty = amount || currentQty;

    queries.removeAmmo.run(deductQty, targetUser.id, ammoConfig.tier);
    return interaction.reply({
      content: `Đã tước bỏ x${deductQty} ${ammoConfig.name} của <@${targetUser.id}>.`,
    });
  }

  // 4. Wipe All (Reset user inventory & coin)
  if (itemKey === 'all') {
    queries.setCoin.run(0, targetUser.id);
    queries.setArmor.run(0, 0, 0, 0, targetUser.id);
    queries.clearUserAmmo.run(targetUser.id);

    return interaction.reply({
      content: `Đã tước toàn bộ tài sản, đạn và giáp của <@${targetUser.id}>.`,
    });
  }

  return interaction.reply({ content: 'Lựa chọn không hợp lệ.', flags: MessageFlags.Ephemeral });
}
