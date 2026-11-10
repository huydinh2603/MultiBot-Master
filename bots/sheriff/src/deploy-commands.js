import { REST, Routes } from 'discord.js';
import dotenv from 'dotenv';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const token = process.env.SHERIFF_TOKEN || process.env.DISCORD_TOKEN;
const clientId = process.env.SHERIFF_CLIENT_ID || process.env.CLIENT_ID;
const guildId = process.env.GUILD_ID;

if (!token || !clientId) {
  console.error('Lỗi: Vui lòng cấu hình SHERIFF_TOKEN (hoặc DISCORD_TOKEN) và CLIENT_ID trong biến môi trường');
  process.exit(1);
}

const commands = [];
const commandsPath = path.join(__dirname, 'commands');
const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = path.join(commandsPath, file);
  const command = await import(`file://${filePath}`);
  if ('data' in command && 'execute' in command) {
    commands.push(command.data.toJSON());
  } else {
    console.warn(`[CẢNH BÁO] Lệnh tại ${filePath} thiếu thuộc tính "data" hoặc "execute".`);
  }
}

const rest = new REST({ version: '10' }).setToken(token);

try {
  console.log(`Đang tải lên ${commands.length} lệnh slash...`);

  if (guildId) {
    const data = await rest.put(
      Routes.applicationGuildCommands(clientId, guildId),
      { body: commands }
    );
    console.log(`Đã triển khai thành công ${data.length} lệnh slash tới Guild ID: ${guildId}!`);
  } else {
    const data = await rest.put(
      Routes.applicationCommands(clientId),
      { body: commands }
    );
    console.log(`Đã triển khai thành công ${data.length} lệnh slash trên toàn cầu (Global)!`);
  }
} catch (error) {
  console.error('Lỗi khi triển khai lệnh:', error);
} finally {
  process.exit(0);
}
