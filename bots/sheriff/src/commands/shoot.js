import { MessageFlags, SlashCommandBuilder } from 'discord.js';
import { executeShoot } from '../services/combat.js';

export const data = new SlashCommandBuilder()
  .setName('shoot')
  .setDescription('Bắn mục tiêu bằng đạn câm lặng')
  .addUserOption(option =>
    option
      .setName('user')
      .setDescription('Người dùng muốn bắn')
      .setRequired(true)
  )
  .addStringOption(option =>
    option
      .setName('ammo')
      .setDescription('Loại đạn (B1 - B6)')
      .setRequired(true)
      .addChoices(
        { name: 'B1 (Đạn T1 - Mute 10p)', value: 'B1' },
        { name: 'B2 (Đạn T2 - Mute 30p)', value: 'B2' },
        { name: 'B3 (Đạn T3 - Mute 1.5h)', value: 'B3' },
        { name: 'B4 (Đạn T4 - Mute 4h)', value: 'B4' },
        { name: 'B5 (Đạn T5 - Mute 10h)', value: 'B5' },
        { name: 'B6 (Đạn T6 - Mute 24h)', value: 'B6' }
      )
  );

export async function execute(interaction) {
  const targetUser = interaction.options.getUser('user');
  const ammoKey = interaction.options.getString('ammo');

  const targetMember = await interaction.guild.members.fetch(targetUser.id).catch(() => null);
  if (!targetMember) {
    return interaction.reply({ content: 'Không tìm thấy người dùng trong server.', flags: MessageFlags.Ephemeral });
  }

  const result = await executeShoot(interaction.user, targetMember, ammoKey);
  
  if (!result.success) {
    return interaction.reply({ content: result.message, flags: MessageFlags.Ephemeral });
  }

  return interaction.reply({ content: result.message });
}
