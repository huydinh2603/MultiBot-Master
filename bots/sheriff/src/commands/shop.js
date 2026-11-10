import { MessageFlags, SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('shop')
  .setDescription('Xem bảng giá đạn và giáp');

export async function execute(interaction) {
  const content = [
    '**CỬA HÀNG T-COIN**',
    '• **Đạn (B):** B1 (10m): 1,000 | B2 (30m): 3,500 | B3 (1.5h): 8,000 | B4 (4h): 22,000 | B5 (10h): 50,000 | B6 (24h): 80,000',
    '• **Giáp (A):** A1 (60 HP): 1,500 | A2 (100 HP): 5,000 | A3 (150 HP): 12,000 | A4 (210 HP): 30,000 | A5 (280 HP): 70,000 | A6 (360 HP): 150,000',
    '',
    '*Dùng /buy [mã] [số lượng] để mua. Ví dụ: /buy B1 5 hoặc /buy A3*',
  ].join('\n');

  return interaction.reply({ content, flags: MessageFlags.Ephemeral });
}
