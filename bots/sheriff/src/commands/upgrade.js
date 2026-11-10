import { MessageFlags, SlashCommandBuilder } from 'discord.js';
import { ARMOR, STAR_MODIFIERS } from '../config.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('upgrade')
  .setDescription('Nâng cấp sao cho bộ giáp đang mặc (1, 2 hoặc 3 sao)')
  .addIntegerOption(option =>
    option
      .setName('stars')
      .setDescription('Cấp sao muốn nâng tới (1, 2 hoặc 3)')
      .setRequired(true)
      .addChoices(
        { name: '1 sao (*) - Kháng mòn 15%', value: 1 },
        { name: '2 sao (**) - Kháng mòn 30%', value: 2 },
        { name: '3 sao (***) - Kháng mòn 45%', value: 3 }
      )
  );

export async function execute(interaction) {
  const targetStars = interaction.options.getInteger('stars');
  const userId = interaction.user.id;
  const user = getUserData(userId);

  if (user.armor_tier === 0) {
    return interaction.reply({ content: 'Bạn chưa trang bị giáp. Dùng /buy để mua giáp trước.', flags: MessageFlags.Ephemeral });
  }

  const armorKey = `A${user.armor_tier}`;
  const armorConfig = ARMOR[armorKey];
  if (!armorConfig) {
    return interaction.reply({ content: 'Không tìm thấy dữ liệu giáp.', flags: MessageFlags.Ephemeral });
  }

  const currentStars = user.armor_stars;
  if (currentStars >= targetStars) {
    return interaction.reply({
      content: `Giáp hiện tại của bạn đã đạt ${currentStars} sao (không thể hạ cấp hoặc nâng trùng cấp).`,
      flags: MessageFlags.Ephemeral,
    });
  }

  // Calculate cumulative cost from currentStars to targetStars
  let totalCost = 0;
  for (let s = currentStars + 1; s <= targetStars; s++) {
    totalCost += armorConfig.upgradeCosts[s] || 0;
  }

  if (user.t_coin < totalCost) {
    return interaction.reply({
      content: `Không đủ T-Coin. Nâng cấp từ ${currentStars} sao lên ${targetStars} sao tốn ${totalCost.toLocaleString('en-US')} T-Coin (bạn có: ${user.t_coin.toLocaleString('en-US')} T-Coin).`,
      flags: MessageFlags.Ephemeral,
    });
  }

  queries.updateCoin.run(-totalCost, userId);
  queries.setArmorStars.run(targetStars, userId);

  const starSymbols = '*'.repeat(targetStars);
  const reductionPercent = Math.round((STAR_MODIFIERS[targetStars] || 0) * 100);

  return interaction.reply({
    content: `Nâng cấp Giáp T${user.armor_tier} lên [${starSymbols}]:\nKháng mòn: ${reductionPercent}%\nChi phí: ${totalCost.toLocaleString('en-US')} T-Coin.`,
  });
}
