import dns from 'node:dns';
try {
  dns.setDefaultResultOrder('ipv4first');
} catch (e) {
  // Ignored if older node
}

import { Client, Collection, Events, GatewayIntentBits, MessageFlags, Options } from 'discord.js';
import dotenv from 'dotenv';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { handleChatMessage } from './services/economy.js';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Biến lưu trạng thái chẩn đoán hệ thống
let currentBotStatus = 'INITIALIZING';
let lastLoginError = null;
let activeClient = null;

// Xử lý và làm sạch Token tránh lỗi người dùng copy dính khoảng trắng hoặc dấu ngoặc kép
let token = process.env.SHERIFF_TOKEN || process.env.DISCORD_TOKEN;
if (!token) {
  console.log('[Sheriff] Chưa cấu hình SHERIFF_TOKEN hoặc DISCORD_TOKEN trong biến môi trường.');
  console.log('[Sheriff] Bot đang ở chế độ chờ (standby mode)...');
  currentBotStatus = 'WAITING_FOR_TOKEN';
} else {
  token = token.trim().replace(/^["'`]|["'`]$/g, '');
  if (token.startsWith('DISCORD_TOKEN=')) {
    token = token.replace('DISCORD_TOKEN=', '').trim();
  }
  if (token.startsWith('Bot ')) {
    token = token.replace(/^Bot\s+/i, '').trim();
  }
  token = token.replace(/^["'`]|["'`]$/g, '').trim();
}

// 1. Khởi động Web Server nếu không chạy dưới Orchestrator
const PORT = process.env.PORT || 3000;
const isOrchestrator = process.env.ORCHESTRATOR || process.env.DISABLE_KEEP_ALIVE;
const server = http.createServer(async (req, res) => {
  if (req.url === '/status') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    return res.end(JSON.stringify({
      botStatus: currentBotStatus,
      isOnline: activeClient ? activeClient.isReady() : false,
      botUser: activeClient?.user ? `${activeClient.user.tag} (ID: ${activeClient.user.id})` : null,
      serverCount: activeClient?.guilds ? activeClient.guilds.cache.size : 0,
      serverList: activeClient?.guilds ? activeClient.guilds.cache.map(g => g.name) : [],
      lastError: lastLoginError ? `${lastLoginError.name || 'Error'}: ${lastLoginError.message}` : null,
      tokenLength: token ? token.length : 0,
    }, null, 2));
  }

  // Endpoint test kết nối trực tiếp tới Discord API
  if (req.url === '/test-discord') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    const start = Date.now();
    try {
      const resGateway = await fetch('https://discord.com/api/v10/gateway/bot', {
        headers: { Authorization: `Bot ${token}` },
      });
      const body = await resGateway.text();
      return res.end(JSON.stringify({
        durationMs: Date.now() - start,
        status: resGateway.status,
        statusText: resGateway.statusText,
        body: body.length > 500 ? body.slice(0, 500) + '...' : body,
      }, null, 2));
    } catch (err) {
      return res.end(JSON.stringify({
        durationMs: Date.now() - start,
        error: err.message,
        code: err.code,
      }, null, 2));
    }
  }

  // Endpoint yêu cầu bot kết nối lại ngay lập tức
  if (req.url === '/reconnect') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    if (activeClient && activeClient.isReady()) {
      return res.end(JSON.stringify({ message: 'Bot is already ONLINE!', isOnline: true }, null, 2));
    }
    console.log('[Web Reconnect] Nhận yêu cầu kết nối lại...');
    initBot([GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent]);
    return res.end(JSON.stringify({
      message: 'Reconnection attempt initiated. Check /status in 15 seconds.',
      botStatus: currentBotStatus,
    }, null, 2));
  }

  res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end(`Sheriff Bot Web Server is running! Status: ${currentBotStatus}. (Visit /status or /test-discord)`);
});

if (!isOrchestrator) {
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`[Web Server] Đang lắng nghe tại cổng: ${PORT}`);
  });
} else {
  console.log('[Web Server] Standalone web server disabled (managed by Multi-Bot Orchestrator).');
}

// Dọn dẹp RAM định kỳ ngăn ngừa tràn 512MB RAM của Render (ngăn lỗi exit code 134)
setInterval(() => {
  if (global.gc) {
    try { global.gc(); } catch (e) {}
  }
  const mem = process.memoryUsage();
  if (mem.rss > 320 * 1024 * 1024) {
    console.warn(`[Cảnh báo RAM] Bộ nhớ đạt ${(mem.rss / 1024 / 1024).toFixed(1)}MB. Đang giải phóng cache...`);
    if (activeClient && activeClient.channels) {
      activeClient.channels.cache.forEach(ch => {
        if (ch.messages && ch.messages.cache) ch.messages.cache.clear();
      });
    }
  }
}, 10 * 60 * 1000).unref();

// Bắt các lỗi toàn cục
process.on('unhandledRejection', (reason) => {
  console.error('[Unhandled Rejection]:', reason);
});
process.on('uncaughtException', (err) => {
  console.error('[Uncaught Exception]:', err);
});

// Nạp các lệnh Slash từ thư mục commands
const commands = new Collection();
const commandsPath = path.join(__dirname, 'commands');
const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));

console.log(`[Khởi động] Đang nạp ${commandFiles.length} file lệnh...`);
for (const file of commandFiles) {
  const filePath = path.join(commandsPath, file);
  try {
    const fileUrl = pathToFileURL(filePath).href;
    const command = await import(fileUrl);
    if ('data' in command && 'execute' in command) {
      commands.set(command.data.name, command);
      console.log(` -> Đã nạp lệnh: /${command.data.name}`);
    } else {
      console.warn(`[CẢNH BÁO] Lệnh tại ${filePath} thiếu thuộc tính "data" hoặc "execute".`);
    }
  } catch (err) {
    console.error(`[Lỗi nạp lệnh ${file}]:`, err);
  }
}

/**
 * Quản lý trạng thái kết nối và tự động thử lại
 */
let isConnecting = false;
let reconnectTimer = null;

function scheduleReconnect(intents, isFallback = false) {
  if (reconnectTimer) return;
  console.log('[Discord] Sẽ tự động thử kết nối lại sau 30 giây...');
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (!activeClient || !activeClient.isReady()) {
      console.log('[Discord] Bắt đầu tự động kết nối lại...');
      initBot(intents, isFallback);
    }
  }, 30000);
}

/**
 * Hàm khởi tạo và kết nối Client với cơ chế Fallback thông minh
 */
async function initBot(intents, isFallback = false) {
  if (isConnecting) {
    console.log('[Discord] Đang có một tiến trình kết nối đang chạy...');
    return;
  }
  if (activeClient && activeClient.isReady()) {
    console.log('[Discord] Bot đã ở trạng thái Ready.');
    return;
  }

  isConnecting = true;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  if (activeClient) {
    try {
      activeClient.removeAllListeners();
      activeClient.destroy();
    } catch (e) {
      // Ignored
    }
  }

  const client = new Client({
    intents,
    makeCache: Options.cacheWithLimits({
      MessageManager: 25,
      StageInstanceManager: 0,
      ThreadMemberManager: 0,
      PresenceManager: 0,
      VoiceStateManager: 0,
      ReactionManager: 0,
    }),
    sweepers: {
      ...Options.DefaultSweeperSettings,
      messages: {
        interval: 1800,
        lifetime: 900,
      },
    },
    rest: {
      timeout: 15000,
      retries: 2,
    },
  });
  activeClient = client;
  client.commands = commands;

  client.rest.on('rateLimited', info => {
    console.warn(`[Discord REST RateLimit] Rate limited: reset in ${info.timeToReset}ms, global: ${info.global}`);
  });

  client.on('error', err => {
    console.error('[Discord Client Error]:', err);
  });
  client.on('shardError', (err, shardId) => {
    console.error(`[Discord Shard ${shardId} Error]:`, err);
  });
  client.on('shardDisconnect', (event, shardId) => {
    console.warn(`[Discord Shard ${shardId}] Mất kết nối Gateway:`, event);
    currentBotStatus = 'DISCONNECTED';
    scheduleReconnect(intents, isFallback);
  });
  client.on('shardResume', (shardId, replayedEvents) => {
    console.log(`[Discord Shard ${shardId}] Đã khôi phục kết nối thành công! (${replayedEvents} sự kiện)`);
    currentBotStatus = 'ONLINE';
  });

  client.on('debug', info => {
    if (info.includes('Heartbeat') || info.includes('heartbeat')) return;
    console.log(`[Discord WS Debug] ${info}`);
  });

  // Ready event
  client.once(Events.ClientReady, async () => {
    isConnecting = false;
    currentBotStatus = 'ONLINE';
    lastLoginError = null;
    console.log(`=============================================`);
    console.log(`Sheriff Bot đã ONLINE thành công!`);
    console.log(`Tên Bot: ${client.user.tag} (ID: ${client.user.id})`);
    console.log(`Số lượng Server tham gia: ${client.guilds.cache.size}`);

    if (client.guilds.cache.size === 0) {
      console.warn(`[CẢNH BÁO] Bot chưa có mặt trong server nào! Hãy dùng link OAuth2 để mời bot vào server.`);
    } else {
      client.guilds.cache.forEach(guild => {
        console.log(` - Server: ${guild.name} (ID: ${guild.id})`);
      });
    }
    console.log(`=============================================`);

    // Tự động đồng bộ Slash Commands
    try {
      const commandsData = client.commands.map(cmd => cmd.data.toJSON());
      const guildId = process.env.GUILD_ID?.trim();

      if (guildId) {
        const guild = client.guilds.cache.get(guildId);
        if (guild) {
          await guild.commands.set(commandsData);
          console.log(`[Slash Commands] Đã đồng bộ ${commandsData.length} lệnh tới Guild: ${guild.name}`);
        } else {
          await client.application.commands.set(commandsData);
          console.log(`[Slash Commands] Đã đồng bộ ${commandsData.length} lệnh toàn cầu (Global)`);
        }
      } else {
        await client.application.commands.set(commandsData);
        console.log(`[Slash Commands] Đã đồng bộ ${commandsData.length} lệnh toàn cầu (Global)`);
      }
    } catch (error) {
      console.error('[Slash Commands] Lỗi khi tự động đồng bộ lệnh:', error);
    }
  });

  // Message event for Chat-to-Earn
  client.on('messageCreate', async message => {
    try {
      handleChatMessage(message);
    } catch (error) {
      console.error('Lỗi trong xử lý chat-to-earn:', error);
    }
  });

  // Interaction event for Slash Commands
  client.on('interactionCreate', async interaction => {
    if (!interaction.isChatInputCommand()) return;

    const command = client.commands.get(interaction.commandName);
    if (!command) {
      console.error(`Không tìm thấy lệnh: ${interaction.commandName}`);
      return;
    }

    try {
      await command.execute(interaction);
    } catch (error) {
      console.error(`Lỗi khi thực thi lệnh /${interaction.commandName}:`, error);
      const replyContent = { content: 'Đã có lỗi xảy ra khi thực thi lệnh này.', flags: MessageFlags.Ephemeral };
      if (interaction.replied || interaction.deferred) {
        await interaction.followUp(replyContent).catch(() => null);
      } else {
        await interaction.reply(replyContent).catch(() => null);
      }
    }
  });

  // Kiểm tra trước kết nối tới Discord API để phát hiện lỗi Cloudflare 429 Rate Limit
  try {
    const preCheck = await fetch('https://discord.com/api/v10/gateway', { signal: AbortSignal.timeout(4000) });
    if (preCheck.status === 429) {
      console.error('================================================================');
      console.error('[CẢNH BÁO RATE LIMIT 429]: IP của máy chủ Render đang bị Discord Cloudflare chặn!');
      console.error('Bot KHÔNG THỂ kết nối Discord Gateway từ dải IP này.');
      console.error('GIẢI PHÁP: Tạo Web Service mới trên Render và chọn Region: Singapore hoặc Frankfurt.');
      console.error('================================================================');
      currentBotStatus = 'BLOCKED_BY_CLOUDFLARE_429';
    }
  } catch (e) {
    // Bỏ qua lỗi timeout kiểm tra
  }

  // Kết nối tới Gateway với Timeout bảo vệ
  console.log(`[Discord] Đang kết nối tới Discord Gateway (Chế độ: ${isFallback ? 'Cơ bản' : 'Đầy đủ'})...`);
  try {
    const loginPromise = client.login(token);
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Discord Gateway không phản hồi sau 15 giây (Có thể do mạng hoặc Cloudflare rate limit)')), 15000)
    );

    await Promise.race([loginPromise, timeoutPromise]);
    console.log('[Discord] Đã gửi thông tin đăng nhập thành công!');
  } catch (err) {
    isConnecting = false;
    lastLoginError = err;
    currentBotStatus = `LOGIN_FAILED: ${err.message}`;
    console.error('[Discord Lỗi Đăng Nhập]:', err.message);

    // Nếu lỗi do Privileged Intents chưa bật trên Discord Developer Portal
    if (err.message && (err.message.includes('disallowed intents') || err.code === 'DisallowedIntents')) {
      if (!isFallback) {
        console.warn('==> Phát hiện thiếu quyền Message Content Intent trên Discord Developer Portal.');
        console.log('==> Đang tự động kết nối lại ở chế độ cơ bản để Bot Online ngay lập tức...');
        return initBot([GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages], true);
      }
    }

    if (err.code === 'TokenInvalid' || err.message?.includes('401')) {
      console.error('==> NGUYÊN NHÂN: Token Discord không chính xác hoặc đã bị Reset trên Discord Developer Portal!');
      console.error('==> HÃY VÀO THẺ BOT TRÊN DISCORD DEV PORTAL, BẤM RESET TOKEN VÀ CẬP NHẬT LẠI TRÊN RENDER.');
      return;
    }

    // Tự động lên lịch thử kết nối lại sau 30 giây
    scheduleReconnect(intents, isFallback);
  }
}

// Bắt đầu kết nối
if (token) {
  initBot([
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ]);
}