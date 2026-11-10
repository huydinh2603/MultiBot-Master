import { MessageFlags, PermissionFlagsBits, SlashCommandBuilder } from 'discord.js';
import { queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('unshield')
  .setDescription('Gỡ bỏ thời gian bảo hộ 30 giây của người dùng ngay lập tức (Chỉ Admin / Chủ Server)')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addUserOption(opt =>
    opt
      .setName('user')
      .setDescription('Người dùng cần gỡ bảo hộ')
      .setRequired(true)
  );

export async function execute(interaction) {
  const ownerId = interaction.guild?.ownerId || (await interaction.guild?.fetchOwner().catch(() => null))?.id;
  const isOwner = ownerId && interaction.user.id === ownerId;
  const isAdmin = interaction.memberPermissions?.has(PermissionFlagsBits.Administrator);

  if (!isOwner && !isAdmin) {
    return interaction.reply({
      content: 'Chỉ Quản trị viên (Admin) hoặc Chủ Server mới có quyền sử dụng lệnh này.',
      flags: MessageFlags.Ephemeral,
    });
  }

  const targetUser = interaction.options.getUser('user');

  queries.setImmunity.run(0, targetUser.id);

  return interaction.reply({
    content: `Đã gỡ bỏ khiên bảo hộ của <@${targetUser.id}>.`,
    flags: MessageFlags.Ephemeral,
  });
}
