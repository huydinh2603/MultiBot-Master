import { MessageFlags, SlashCommandBuilder } from 'discord.js';
import { queries } from '../database.js';

export const data = new SlashCommandBuilder()
  .setName('top')
  .setDescription('Xem bảng xếp hạng server')
  .addStringOption(option =>
    option
      .setName('category')
      .setDescription('Hạng mục bảng xếp hạng')
      .setRequired(true)
      .addChoices(
        { name: 'T-Coin (Đại gia)', value: 't_coin' },
        { name: 'Kẻ Độc Tài (Gây nhiều mute nhất)', value: 'dictator' },
        { name: 'Nạn Nhân (Bị mute nhiều nhất)', value: 'victim' }
      )
  );

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phút`;
  const hours = (seconds / 3600).toFixed(1);
  return `${hours} giờ`;
}

export async function execute(interaction) {
  const category = interaction.options.getString('category');

  if (category === 't_coin') {
    const rows = queries.getTopCoins.all();
    if (rows.length === 0) {
      return interaction.reply({ content: 'Chưa có dữ liệu bảng xếp hạng.', flags: MessageFlags.Ephemeral });
    }

    const lines = ['**Top T-Coin**'];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      lines.push(`${i + 1}. <@${row.user_id}> — ${row.t_coin.toLocaleString('en-US')} T`);
    }

    return interaction.reply({ content: lines.join('\n') });
  }

  if (category === 'dictator') {
    const rows = queries.getTopDictators.all();
    if (rows.length === 0) {
      return interaction.reply({ content: 'Chưa có dữ liệu bảng xếp hạng.', flags: MessageFlags.Ephemeral });
    }

    const lines = ['**Top Kẻ Độc Tài**'];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      lines.push(`${i + 1}. <@${row.user_id}> — ${formatDuration(row.total_mute_given_seconds)} mute`);
    }

    return interaction.reply({ content: lines.join('\n') });
  }

  if (category === 'victim') {
    const rows = queries.getTopVictims.all();
    if (rows.length === 0) {
      return interaction.reply({ content: 'Chưa có dữ liệu bảng xếp hạng.', flags: MessageFlags.Ephemeral });
    }

    const lines = ['**Top Nạn Nhân**'];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      lines.push(`${i + 1}. <@${row.user_id}> — ${formatDuration(row.total_mute_received_seconds)} bị mute`);
    }

    return interaction.reply({ content: lines.join('\n') });
  }

  return interaction.reply({ content: 'Hạng mục không hợp lệ.', flags: MessageFlags.Ephemeral });
}
