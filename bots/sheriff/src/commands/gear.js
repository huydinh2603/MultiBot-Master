import { MessageFlags, SlashCommandBuilder } from 'discord.js';
import { STAR_MODIFIERS } from '../config.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('gear')
  .setDescription('Xem thông tin tài sản, giáp và kho đạn');

export async function execute(interaction) {
  const userId = interaction.user.id;
  const user = getUserData(userId);

  // Format armor info
  let armorText = 'Chưa trang bị giáp';
  if (user.armor_tier > 0) {
    const starCount = user.armor_stars;
    const starDisplay = starCount > 0 ? ` [${'*'.repeat(starCount)}]` : '';
    const reductionPercent = Math.round((STAR_MODIFIERS[starCount] || 0) * 100);
    armorText = `Tier ${user.armor_tier}${starDisplay} — ${user.armor_durability}/${user.armor_max_durability} HP (Kháng mòn ${reductionPercent}%)`;
  }

  // Format ammo inventory
  const ammoList = queries.getAllAmmo.all(userId);
  const ammoMap = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 };
  for (const item of ammoList) {
    ammoMap[item.ammo_tier] = item.quantity;
  }
  const ammoText = `T1: ${ammoMap[1]} | T2: ${ammoMap[2]} | T3: ${ammoMap[3]} | T4: ${ammoMap[4]} | T5: ${ammoMap[5]} | T6: ${ammoMap[6]}`;

  const responseText = [
    `**Trang bị — @${interaction.user.username}**`,
    `T-Coin: ${user.t_coin.toLocaleString('en-US')}`,
    `Giáp: ${armorText}`,
    `Kho đạn: ${ammoText}`,
  ].join('\n');

  return interaction.reply({ content: responseText, flags: MessageFlags.Ephemeral });
}
