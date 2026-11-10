import { ActionRowBuilder, ButtonBuilder, ButtonStyle, ComponentType, MessageFlags, SlashCommandBuilder } from 'discord.js';
import { ARMOR, COMBAT } from '../config.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('repair')
  .setDescription('Sửa chữa và hồi phục độ bền cho giáp đang mặc');

export async function execute(interaction) {
  const userId = interaction.user.id;
  const user = getUserData(userId);

  if (user.armor_tier === 0) {
    return interaction.reply({ content: 'Bạn chưa trang bị giáp.', flags: MessageFlags.Ephemeral });
  }

  const armorKey = `A${user.armor_tier}`;
  const armorConfig = ARMOR[armorKey];
  if (!armorConfig) {
    return interaction.reply({ content: 'Không tìm thấy dữ liệu giáp.', flags: MessageFlags.Ephemeral });
  }

  const currentHp = user.armor_durability;
  const maxHp = user.armor_max_durability;

  if (currentHp >= maxHp) {
    return interaction.reply({ content: `Giáp của bạn đang ở trạng thái hoàn hảo (${currentHp}/${maxHp} HP). Không cần sửa.`, flags: MessageFlags.Ephemeral });
  }

  const missingHp = maxHp - currentHp;
  const damagePercent = Math.round((missingHp / maxHp) * 100);

  // Repair cost is proportional to missing HP (base ~35% of armor base price for full repair)
  const fullRepairCost = Math.round(armorConfig.basePrice * 0.35);
  const repairCost = Math.max(100, Math.round((missingHp / maxHp) * fullRepairCost));

  // 5% max HP penalty
  const newMaxHp = Math.max(10, Math.floor(maxHp * (1 - COMBAT.PENALTY_MAX_DURABILITY_PERCENT)));
  const restoredHp = newMaxHp - currentHp;

  const content = [
    `**Sửa chữa giáp Tier ${user.armor_tier}**`,
    `Tình trạng: ${currentHp}/${maxHp} HP (Hỏng ${damagePercent}%)`,
    `Phục hồi: +${restoredHp} HP`,
    `Khấu hao tối đa (5%): ${maxHp} HP -> ${newMaxHp} HP`,
    `Chi phí: ${repairCost.toLocaleString('en-US')} T-Coin`,
  ].join('\n');

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId('confirm_repair')
      .setLabel('Xác nhận')
      .setStyle(ButtonStyle.Success),
    new ButtonBuilder()
      .setCustomId('cancel_repair')
      .setLabel('Hủy')
      .setStyle(ButtonStyle.Secondary)
  );

  const response = await interaction.reply({
    content,
    components: [row],
    flags: MessageFlags.Ephemeral,
  });

  const collector = response.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 30000,
  });

  collector.on('collect', async i => {
    if (i.user.id !== userId) {
      return i.reply({ content: 'Nút này không dành cho bạn.', flags: MessageFlags.Ephemeral });
    }

    if (i.customId === 'cancel_repair') {
      await i.update({ content: 'Đã hủy sửa giáp.', components: [] });
      return;
    }

    if (i.customId === 'confirm_repair') {
      // Re-fetch latest user data
      const latestUser = getUserData(userId);
      if (latestUser.t_coin < repairCost) {
        await i.update({
          content: `Không đủ T-Coin. Bạn cần ${repairCost.toLocaleString('en-US')} T-Coin (hiện có: ${latestUser.t_coin.toLocaleString('en-US')}).`,
          components: [],
        });
        return;
      }

      queries.updateCoin.run(-repairCost, userId);
      queries.repairArmor.run(newMaxHp, newMaxHp, userId);

      await i.update({
        content: `Đã sửa thành công Giáp Tier ${user.armor_tier}! Độ bền hiện tại: ${newMaxHp}/${newMaxHp} HP. Đã trừ ${repairCost.toLocaleString('en-US')} T-Coin.`,
        components: [],
      });
    }
  });

  collector.on('end', async (_, reason) => {
    if (reason === 'time') {
      await interaction.editReply({ components: [] }).catch(() => null);
    }
  });
}
