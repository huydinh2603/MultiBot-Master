import { MessageFlags, PermissionFlagsBits, SlashCommandBuilder } from 'discord.js';
import { getUserData, queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('coin')
  .setDescription('Quản lý cộng hoặc trừ T-Coin thành viên (Chỉ Admin / Chủ Server)')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addSubcommand(sub =>
    sub
      .setName('add')
      .setDescription('Cộng T-Coin cho người dùng')
      .addUserOption(opt =>
        opt
          .setName('user')
          .setDescription('Người dùng được cộng')
          .setRequired(true)
      )
      .addIntegerOption(opt =>
        opt
          .setName('amount')
          .setDescription('Số lượng T-Coin')
          .setRequired(true)
          .setMinValue(1)
      )
  )
  .addSubcommand(sub =>
    sub
      .setName('remove')
      .setDescription('Trừ T-Coin của người dùng')
      .addUserOption(opt =>
        opt
          .setName('user')
          .setDescription('Người dùng bị trừ')
          .setRequired(true)
      )
      .addIntegerOption(opt =>
        opt
          .setName('amount')
          .setDescription('Số lượng T-Coin')
          .setRequired(true)
          .setMinValue(1)
      )
  );

export async function execute(interaction) {
  // Kiểm tra quyền Admin hoặc Chủ Server
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
  const targetUser = interaction.options.getUser('user');
  const amount = interaction.options.getInteger('amount');

  // Ensure user exists in DB
  getUserData(targetUser.id);

  if (subcommand === 'add') {
    queries.updateCoin.run(amount, targetUser.id);
    const updated = getUserData(targetUser.id);
    return interaction.reply({
      content: `Đã cộng ${amount.toLocaleString('en-US')} T-Coin cho <@${targetUser.id}>. Số dư mới: ${updated.t_coin.toLocaleString('en-US')} T-Coin.`,
      flags: MessageFlags.Ephemeral,
    });
  }

  if (subcommand === 'remove') {
    queries.updateCoin.run(-amount, targetUser.id);
    const updated = getUserData(targetUser.id);
    return interaction.reply({
      content: `Đã trừ ${amount.toLocaleString('en-US')} T-Coin của <@${targetUser.id}>. Số dư mới: ${updated.t_coin.toLocaleString('en-US')} T-Coin.`,
      flags: MessageFlags.Ephemeral,
    });
  }
}
