import { MessageFlags, PermissionFlagsBits, SlashCommandBuilder } from 'discord.js';
import { AMMO, ARMOR } from '../config.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('give')
  .setDescription('Trao T-Coin hoặc trang bị cho người dùng (Chỉ Chủ Server)')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addUserOption(opt =>
    opt
      .setName('user')
      .setDescription('Người nhận')
      .setRequired(true)
  )
  .addStringOption(opt =>
    opt
      .setName('item')
      .setDescription('Vật phẩm hoặc coin')
      .setRequired(true)
      .addChoices(
        { name: 'T-Coin', value: 'coin' },
        { name: 'B1 (Đạn T1)', value: 'B1' },
        { name: 'B2 (Đạn T2)', value: 'B2' },
        { name: 'B3 (Đạn T3)', value: 'B3' },
        { name: 'B4 (Đạn T4)', value: 'B4' },
        { name: 'B5 (Đạn T5)', value: 'B5' },
        { name: 'B6 (Đạn T6)', value: 'B6' },
        { name: 'A1 (Giáp T1)', value: 'A1' },
        { name: 'A2 (Giáp T2)', value: 'A2' },
        { name: 'A3 (Giáp T3)', value: 'A3' },
        { name: 'A4 (Giáp T4)', value: 'A4' },
        { name: 'A5 (Giáp T5)', value: 'A5' },
        { name: 'A6 (Giáp T6)', value: 'A6' }
      )
  )
  .addIntegerOption(opt =>
    opt
      .setName('amount')
      .setDescription('Số lượng (coin hoặc số lượng đạn)')
      .setMinValue(1)
  )
  .addIntegerOption(opt =>
    opt
      .setName('stars')
      .setDescription('Cấp sao của giáp (0 - 3 sao, chỉ áp dụng cho giáp)')
      .setMinValue(0)
      .setMaxValue(3)
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
  const amount = interaction.options.getInteger('amount') || 1;
  const stars = interaction.options.getInteger('stars') || 0;

  // Ensure user exists in database
  getUserData(targetUser.id);

  // 1. Give T-Coin
  if (itemKey === 'coin') {
    queries.updateCoin.run(amount, targetUser.id);
    const updated = getUserData(targetUser.id);
    return interaction.reply({
      content: `Đã trao ${amount.toLocaleString('en-US')} T-Coin cho <@${targetUser.id}>. Số dư mới: ${updated.t_coin.toLocaleString('en-US')} T.`,
    });
  }

  // 2. Give Ammo (B1 - B6)
  if (itemKey.startsWith('B')) {
    const ammoConfig = AMMO[itemKey];
    if (!ammoConfig) {
      return interaction.reply({ content: 'Mã đạn không hợp lệ.', flags: MessageFlags.Ephemeral });
    }

    queries.addAmmo.run(targetUser.id, ammoConfig.tier, amount);
    const currentStock = queries.getAmmo.get(targetUser.id, ammoConfig.tier);
    const totalQty = currentStock ? currentStock.quantity : amount;

    return interaction.reply({
      content: `Đã trao x${amount} ${ammoConfig.name} cho <@${targetUser.id}>. Tổng hiện có trong kho: ${totalQty} viên.`,
    });
  }

  // 3. Give Armor (A1 - A6)
  if (itemKey.startsWith('A')) {
    const armorConfig = ARMOR[itemKey];
    if (!armorConfig) {
      return interaction.reply({ content: 'Mã giáp không hợp lệ.', flags: MessageFlags.Ephemeral });
    }

    queries.setArmor.run(
      armorConfig.tier,
      stars,
      armorConfig.maxDurability,
      armorConfig.maxDurability,
      targetUser.id
    );

    const starDisplay = stars > 0 ? ` [${'*'.repeat(stars)}]` : '';
    return interaction.reply({
      content: `Đã trang bị ${armorConfig.name}${starDisplay} (${armorConfig.maxDurability}/${armorConfig.maxDurability} HP) cho <@${targetUser.id}>.`,
    });
  }

  return interaction.reply({ content: 'Vật phẩm không hợp lệ.', flags: MessageFlags.Ephemeral });
}
