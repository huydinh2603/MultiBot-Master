import { MessageFlags, PermissionFlagsBits, SlashCommandBuilder } from 'discord.js';
import { queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('blacklist')
  .setDescription('Quản lý danh sách kênh cấm nhận T-Coin (Chỉ Admin / Chủ Server)')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addSubcommand(sub =>
    sub
      .setName('add')
      .setDescription('Chặn kênh không cho rơi T-Coin')
      .addChannelOption(opt =>
        opt
          .setName('channel')
          .setDescription('Kênh cần chặn')
          .setRequired(true)
      )
  )
  .addSubcommand(sub =>
    sub
      .setName('remove')
      .setDescription('Mở lại khả năng rơi T-Coin cho kênh')
      .addChannelOption(opt =>
        opt
          .setName('channel')
          .setDescription('Kênh cần bỏ chặn')
          .setRequired(true)
      )
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

  const subcommand = interaction.options.getSubcommand();
  const channel = interaction.options.getChannel('channel');

  if (subcommand === 'add') {
    queries.addBlacklistChannel.run(channel.id, interaction.guild.id, Date.now());
    return interaction.reply({
      content: `Đã thêm <#${channel.id}> vào danh sách cấm rơi T-Coin.`,
      flags: MessageFlags.Ephemeral,
    });
  }

  if (subcommand === 'remove') {
    queries.removeBlacklistChannel.run(channel.id);
    return interaction.reply({
      content: `Đã bỏ <#${channel.id}> khỏi danh sách cấm rơi T-Coin.`,
      flags: MessageFlags.Ephemeral,
    });
  }
}
