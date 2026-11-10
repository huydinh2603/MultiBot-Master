const { Client, RichPresence, Options } = require('discord.js-selfbot-v13');
const WebSocketShard = require('discord.js-selfbot-v13/src/client/websocket/WebSocketShard');
const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.WIDGET_PORT || (process.env.ORCHESTRATOR ? 3005 : (process.env.PORT || 3000));
const SYNC_KEY = process.env.SYNC_KEY || 'LamiaSync2026';

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Cho phép CORS
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-sync-key');
  if (req.method === 'OPTIONS') return res.sendStatus(200);
  next();
});

// Cấu hình Widget & Bộ đồng bộ Cloud vĩnh viễn (chống reset về Lamia khi Render restart)
const CONFIG_FILE = path.join(__dirname, 'widget-config.json');
const CLOUD_SYNC_URL = 'https://api.restful-api.dev/objects/ff808181a09d98f701a1b40f1cfd58cc';

const defaultRpcConfig = {
  applicationId: '1538109455907033128',
  type: 'LISTENING',
  name: 'Gray Raven OST - Revelation (GhostFinal feat Kinoko)',
  details: 'GhostFinal - Revelation feat Kinoko (Punishing)',
  state: 'YouTube Music',
  showTimestamp: true,
  startTimestamp: Date.now(),
  largeImage: 'youtube:1W6B60hoa_Y',
  largeText: 'Gray Raven OST - Revelation',
  smallImage: '',
  smallText: '',
  button1Label: 'Nghe trên YouTube',
  button1Url: 'https://www.youtube.com/watch?v=1W6B60hoa_Y',
  button2Label: '',
  button2Url: '',
  previewImage: 'https://i.ytimg.com/vi/1W6B60hoa_Y/hqdefault.jpg'
};

let rpcConfig = { ...defaultRpcConfig };
if (fs.existsSync(CONFIG_FILE)) {
  try {
    const saved = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
    rpcConfig = { ...defaultRpcConfig, ...saved };
  } catch (e) {}
}

async function syncConfigFromCloud() {
  try {
    const res = await fetch(CLOUD_SYNC_URL, { headers: { 'Accept': 'application/json' } });
    if (res.ok) {
      const json = await res.json();
      if (json && json.data && json.data.name) {
        rpcConfig = { ...defaultRpcConfig, ...json.data };
        try {
          fs.writeFileSync(CONFIG_FILE, JSON.stringify(rpcConfig, null, 2));
        } catch (e) {}
        addLog(`[Cloud Sync] Đã nạp bài hát lưu trên Cloud: "${rpcConfig.name}"`);
        if (currentClient && currentClient.user) {
          applyRPC(currentClient);
        }
      }
    }
  } catch (e) {
    addLog(`[Cloud Sync] Không thể kết nối Cloud Storage: ${e.message}`);
  }
}

function saveRpcConfig(newCfg) {
  rpcConfig = { ...rpcConfig, ...newCfg };
  try {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(rpcConfig, null, 2));
  } catch (e) {}

  fetch(CLOUD_SYNC_URL, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'discord_widget_config', data: rpcConfig })
  }).then(r => r.json()).then(() => {
    addLog('[Cloud Sync] Đã sao lưu bài hát mới lên Cloud vĩnh viễn');
  }).catch(err => {
    console.error('[Cloud Sync Error]:', err.message);
  });
}

const botStatus = {
  startedAt: new Date().toISOString(),
  tokenConfigured: false,
  tokenLength: 0,
  tokenPrefix: null,
  isLoggedIn: false,
  userTag: null,
  lastError: null,
  debugMessages: []
};

function addLog(msg) {
  console.log(msg);
  botStatus.debugMessages.push(`[${new Date().toLocaleTimeString('vi-VN')}] ${msg}`);
  if (botStatus.debugMessages.length > 50) botStatus.debugMessages.shift();
}

let currentClient = null;
let activeToken = null;
const TOKEN_FILE = path.join(__dirname, 'widget-token.json');

function saveWorkingToken(tk) {
  try {
    fs.writeFileSync(TOKEN_FILE, JSON.stringify({ token: tk }), 'utf8');
  } catch (e) {}
}

function loadWorkingToken() {
  try {
    if (fs.existsSync(TOKEN_FILE)) {
      const data = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf8'));
      if (data && data.token && typeof data.token === 'string') return data.token.trim();
    }
  } catch (e) {}
  return null;
}

function safelyDestroyClient(clientInstance) {
  if (!clientInstance) return;
  try {
    clientInstance.removeAllListeners();
    if (clientInstance.ws) {
      clientInstance.ws.removeAllListeners();
      if (clientInstance.ws.shards) {
        for (const shard of clientInstance.ws.shards.values()) {
          shard.removeAllListeners();
          if (shard.connection) {
            try {
              if (typeof shard.connection.terminate === 'function') {
                shard.connection.terminate();
              } else if (typeof shard.connection.close === 'function') {
                shard.connection.close(1000);
              }
            } catch (e) {}
          }
          try {
            shard.destroy({ reset: true, emit: false, log: false });
          } catch (e) {}
        }
        clientInstance.ws.shards.clear();
      }
      if (clientInstance.ws.shardQueue) {
        clientInstance.ws.shardQueue.clear();
      }
    }
    clientInstance.destroy();
  } catch (e) {
    console.error('[Cleanup Error]:', e);
  }
}

function applyRPC(client) {
  if (!client || !client.user) return;
  try {
    const rpc = new RichPresence(client)
      .setApplicationId(rpcConfig.applicationId || '1538109455907033128')
      .setType(rpcConfig.type || 'LISTENING')
      .setName(rpcConfig.name || 'Music');

    if (rpcConfig.details && rpcConfig.details.trim()) {
      rpc.setDetails(rpcConfig.details.trim());
    }
    if (rpcConfig.state && rpcConfig.state.trim()) {
      rpc.setState(rpcConfig.state.trim());
    }

    if (rpcConfig.showTimestamp) {
      rpc.setStartTimestamp(rpcConfig.startTimestamp || Date.now());
    }

    if (rpcConfig.largeImage && rpcConfig.largeImage.trim()) {
      try {
        rpc.setAssetsLargeImage(rpcConfig.largeImage.trim());
        if (rpcConfig.largeText && rpcConfig.largeText.trim()) {
          rpc.setAssetsLargeText(rpcConfig.largeText.trim());
        }
      } catch (imgErr) {
        addLog(`[Cảnh báo Large Image]: ${imgErr.message}`);
      }
    }

    if (rpcConfig.smallImage && rpcConfig.smallImage.trim()) {
      try {
        rpc.setAssetsSmallImage(rpcConfig.smallImage.trim());
        if (rpcConfig.smallText && rpcConfig.smallText.trim()) {
          rpc.setAssetsSmallText(rpcConfig.smallText.trim());
        }
      } catch (smErr) {
        addLog(`[Cảnh báo Small Image]: ${smErr.message}`);
      }
    }

    if (rpcConfig.button1Label && rpcConfig.button1Url && rpcConfig.button1Label.trim() && rpcConfig.button1Url.trim()) {
      rpc.addButton(rpcConfig.button1Label.trim(), rpcConfig.button1Url.trim());
    }
    if (rpcConfig.button2Label && rpcConfig.button2Url && rpcConfig.button2Label.trim() && rpcConfig.button2Url.trim()) {
      rpc.addButton(rpcConfig.button2Label.trim(), rpcConfig.button2Url.trim());
    }

    client.user.setActivity(rpc);
    addLog(`[Discord] Đã cập nhật widget: "${rpcConfig.name}" (${rpcConfig.type})`);
  } catch (error) {
    botStatus.lastError = error.message;
    addLog(`[Lỗi Rich Presence]: ${error.message}`);
  }
}

function sanitizeToken(raw) {
  if (!raw || typeof raw !== 'string') return '';
  let token = raw.trim();
  token = token.replace(/^["'`]|["'`]$/g, '').trim();
  if (/^authorization:\s*/i.test(token)) {
    token = token.replace(/^authorization:\s*/i, '').trim();
  }
  if (/^bearer\s+/i.test(token)) {
    token = token.replace(/^bearer\s+/i, '').trim();
  }
  if (/^bot\s+/i.test(token)) {
    token = token.replace(/^bot\s+/i, '').trim();
  }
  token = token.replace(/^["'`]|["'`]$/g, '').trim();
  return token;
}

async function connectWithToken(token) {
  const cleanToken = sanitizeToken(token);
  if (!cleanToken) {
    throw new Error('Token rỗng hoặc không hợp lệ');
  }

  if (currentClient) {
    addLog('[Discord] Đang dọn dẹp và ngắt kết nối phiên cũ...');
    safelyDestroyClient(currentClient);
    currentClient = null;
  }

  botStatus.isLoggedIn = false;
  botStatus.userTag = null;
  botStatus.tokenConfigured = true;
  botStatus.tokenLength = cleanToken.length;
  botStatus.tokenPrefix = cleanToken.substring(0, 10) + '...';
  botStatus.lastError = null;

  const client = new Client({
    checkUpdate: false,
    makeCache: Options.cacheWithLimits({
      ApplicationCommandManager: 0,
      BaseGuildEmojiManager: 0,
      GuildBanManager: 0,
      GuildInviteManager: 0,
      GuildMemberManager: 0,
      GuildEmojiManager: 0,
      GuildStickerManager: 0,
      GuildScheduledEventManager: 0,
      MessageManager: 0,
      PresenceManager: 0,
      ReactionManager: 0,
      ReactionUserManager: 0,
      StageInstanceManager: 0,
      ThreadMemberManager: 0,
      UserManager: 0,
      VoiceStateManager: 0
    })
  });
  currentClient = client;

  client.ws.connect = async function() {
    this.gateway = 'wss://gateway.discord.gg/';
    const shards = [0];
    this.totalShards = 1;
    this.debug('Đang kết nối WebSocket Gateway...');
    this.shardQueue = new Set(shards.map(id => new WebSocketShard(this, id)));
    return this.createShards();
  };

  client.on('debug', (msg) => {
    if (!msg.toLowerCase().includes('heartbeat')) addLog(`[Debug] ${msg}`);
  });

  client.on('error', (err) => {
    botStatus.lastError = err.message;
    addLog(`[Discord Client Error]: ${err.message}`);
  });

  client.on('shardError', (err) => {
    botStatus.lastError = err.message;
    addLog(`[Shard Error]: ${err.message}`);
  });

  client.on('shardDisconnect', (event) => {
    botStatus.isLoggedIn = false;
    addLog(`[Shard Disconnect] Code: ${event.code}, Reason: ${event.reason || 'None'}`);
    if (event.code === 4013) {
      const warningMsg = 'LỖI 4013 (Invalid intent): Token hiện tại là BOT TOKEN (từ Discord Developer Portal), không phải USER TOKEN! Widget Rich Presence yêu cầu Discord USER TOKEN (tài khoản cá nhân) để hiển thị trạng thái trên profile của bạn.';
      botStatus.lastError = warningMsg;
      addLog(`[CẢNH BÁO QUAN TRỌNG] ${warningMsg}`);
    } else if (event.code === 4004) {
      const authMsg = 'LỖI 4004 (Authentication failed): Token không chính xác hoặc đã hết hạn/đổi mật khẩu. Vui lòng lấy lại USER_TOKEN mới từ F12 DevTools.';
      botStatus.lastError = authMsg;
      addLog(`[CẢNH BÁO] ${authMsg}`);
    }
  });

  client.on('ready', () => {
    botStatus.isLoggedIn = true;
    botStatus.userTag = client.user.tag;
    activeToken = cleanToken;
    saveWorkingToken(cleanToken);
    addLog(`[Discord] Đã kết nối thành công tới tài khoản: ${client.user.tag}`);
    applyRPC(client);
  });

  client.on('invalidated', () => {
    botStatus.isLoggedIn = false;
    addLog('[Discord] Phiên kết nối bị hủy (invalidated). Đang kết nối lại sau 5s...');
    setTimeout(() => {
      if (activeToken) {
        connectWithToken(activeToken).catch(err => {
          addLog(`[Tự động kết nối lại thất bại]: ${err.message}`);
        });
      }
    }, 5000);
  });

  try {
    addLog(`[Discord] Đang tiến hành kết nối WebSocket Gateway...`);
    await client.login(cleanToken);
    addLog('[Discord] Token hợp lệ, đang đồng bộ dữ liệu...');
    return client;
  } catch (loginErr) {
    let errMsg = loginErr.message;
    if (errMsg && (errMsg.includes('TOKEN_INVALID') || errMsg.includes('An invalid token'))) {
      errMsg = 'Token không hợp lệ. Vui lòng kiểm tra lại USER_TOKEN từ F12 DevTools.';
    }
    botStatus.lastError = errMsg;
    if (currentClient === client) {
      safelyDestroyClient(client);
      currentClient = null;
    }
    throw new Error(errMsg);
  }
}

// Hàm nhận diện metadata bài hát từ Link (YouTube / Spotify / SoundCloud)
async function parseMusicUrl(inputUrl) {
  const url = (inputUrl || '').trim();
  if (!url) throw new Error('Vui lòng cung cấp link bài hát');

  // 1. YouTube hoặc YouTube Music
  const ytMatch = url.match(/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?|shorts)\/|.*[?&]v=)|youtu\.be\/|music\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})/i);
  if (ytMatch) {
    const videoId = ytMatch[1];
    const oembedUrl = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`;
    const res = await fetch(oembedUrl);
    if (!res.ok) throw new Error('Không thể lấy thông tin video YouTube');
    const data = await res.json();

    let fullTitle = data.title || '';
    let artist = data.author_name || 'YouTube';
    let songName = fullTitle;

    const dashMatch = fullTitle.match(/^([^-–—|:]+)[\s]*[-–—|:][\s]*(.+)$/);
    if (dashMatch) {
      artist = dashMatch[1].trim();
      songName = dashMatch[2].trim();
    }

    const cleanRe = /\s*[\(\[\{](?:Official\s*(?:Music\s*Video|Video|Audio|Lyric\s*Video|MV)?|4K|HD|Remaster(?:ed)?|Lyrics?|Visualizer|Vietsub|Audio)[\)\]\}]/gi;
    songName = songName.replace(cleanRe, '').trim();

    return {
      type: 'LISTENING',
      name: songName || fullTitle,
      details: artist,
      state: 'YouTube Music',
      largeImage: `youtube:${videoId}`,
      previewImage: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
      largeText: fullTitle,
      button1Label: 'Nghe trên YouTube',
      button1Url: `https://www.youtube.com/watch?v=${videoId}`,
      button2Label: '',
      button2Url: '',
      showTimestamp: true
    };
  }

  // 2. Spotify Track
  const spotifyMatch = url.match(/open\.spotify\.com\/(?:intl-[a-z]+\/)?track\/([a-zA-Z0-9]+)/i);
  if (spotifyMatch) {
    const trackId = spotifyMatch[1];
    const oembedUrl = `https://open.spotify.com/oembed?url=https://open.spotify.com/track/${trackId}`;
    const res = await fetch(oembedUrl);
    if (!res.ok) throw new Error('Không thể lấy thông tin từ Spotify');
    const data = await res.json();

    return {
      type: 'LISTENING',
      name: data.title || 'Spotify Track',
      details: 'Spotify Track',
      state: 'Spotify',
      largeImage: `spotify:${trackId}`,
      previewImage: data.thumbnail_url || 'https://assets-global.website-files.com/6257adef93867e50d84d30e2/636e0a6a49cf127bf92de1e2_icon_clyde_blurple_RGB.png',
      largeText: data.title || 'Spotify',
      button1Label: 'Nghe trên Spotify',
      button1Url: `https://open.spotify.com/track/${trackId}`,
      button2Label: '',
      button2Url: '',
      showTimestamp: true
    };
  }

  // 3. SoundCloud
  if (url.includes('soundcloud.com')) {
    const oembedUrl = `https://soundcloud.com/oembed?url=${encodeURIComponent(url)}&format=json`;
    const res = await fetch(oembedUrl);
    if (!res.ok) throw new Error('Không thể lấy thông tin từ SoundCloud');
    const data = await res.json();

    return {
      type: 'LISTENING',
      name: data.title || 'SoundCloud Track',
      details: data.author_name || 'SoundCloud Artist',
      state: 'SoundCloud',
      largeImage: data.thumbnail_url || '',
      previewImage: data.thumbnail_url || '',
      largeText: data.title || 'SoundCloud',
      button1Label: 'Nghe trên SoundCloud',
      button1Url: url,
      button2Label: '',
      button2Url: '',
      showTimestamp: true
    };
  }

  throw new Error('Định dạng link không được hỗ trợ (Hãy dán link YouTube, YouTube Music hoặc Spotify)');
}

// API tự động nhận diện bài hát từ Link
app.post('/api/parse-music', async (req, res) => {
  try {
    const url = req.body.url;
    const info = await parseMusicUrl(url);

    if (req.body.autoApply) {
      saveRpcConfig(info);
      addLog(`[Auto-Music] Đã tự động nhận diện và cập nhật: "${info.name}" (${info.details})`);
      if (currentClient && currentClient.user) {
        applyRPC(currentClient);
      }
    }

    return res.json({ success: true, data: info });
  } catch (err) {
    return res.status(400).json({ success: false, error: err.message });
  }
});

app.get('/api/update-token', async (req, res) => {
  if (req.query.token && req.query.key) {
    if (req.query.key !== SYNC_KEY) {
      return res.status(401).send('Sai mã bảo mật (SYNC_KEY)');
    }
    try {
      await connectWithToken(req.query.token);
      return res.redirect('/?token_updated=true');
    } catch (e) {
      return res.status(500).send(`Lỗi kết nối: ${e.message}`);
    }
  }
  res.redirect('/');
});

app.post('/api/update-token', async (req, res) => {
  const providedKey = req.headers['x-sync-key'] || (req.body && req.body.key) || req.query.key;
  if (!providedKey || providedKey !== SYNC_KEY) {
    return res.status(401).json({ success: false, error: 'Sai Secret Key (Mã bảo mật)' });
  }

  const newToken = (req.body && req.body.token) ? req.body.token : req.query.token;
  if (!newToken || newToken.trim().length < 20) {
    return res.status(400).json({ success: false, error: 'Token không hợp lệ hoặc quá ngắn' });
  }

  addLog('[Tự động] Nhận được Token mới. Đang làm mới kết nối...');
  try {
    await connectWithToken(newToken);
    return res.json({
      success: true,
      message: 'Đã cập nhật Token và duy trì Rich Presence thành công!',
      userTag: botStatus.userTag
    });
  } catch (err) {
    botStatus.lastError = err.message;
    return res.status(500).json({
      success: false,
      error: `Không thể kết nối với token mới: ${err.message}`
    });
  }
});

app.post('/api/update-config', (req, res) => {
  const providedKey = req.headers['x-sync-key'] || req.body.key || req.query.key;
  if (!providedKey || providedKey !== SYNC_KEY) {
    return res.status(401).json({ success: false, error: 'Sai Secret Key (SYNC_KEY)' });
  }

  const updates = {
    applicationId: req.body.applicationId || rpcConfig.applicationId,
    type: req.body.type || rpcConfig.type,
    name: req.body.name || rpcConfig.name,
    details: req.body.details !== undefined ? req.body.details : rpcConfig.details,
    state: req.body.state !== undefined ? req.body.state : rpcConfig.state,
    showTimestamp: req.body.showTimestamp === 'true' || req.body.showTimestamp === true,
    largeImage: req.body.largeImage !== undefined ? req.body.largeImage : rpcConfig.largeImage,
    largeText: req.body.largeText !== undefined ? req.body.largeText : rpcConfig.largeText,
    smallImage: req.body.smallImage !== undefined ? req.body.smallImage : rpcConfig.smallImage,
    smallText: req.body.smallText !== undefined ? req.body.smallText : rpcConfig.smallText,
    button1Label: req.body.button1Label !== undefined ? req.body.button1Label : rpcConfig.button1Label,
    button1Url: req.body.button1Url !== undefined ? req.body.button1Url : rpcConfig.button1Url,
    button2Label: req.body.button2Label !== undefined ? req.body.button2Label : rpcConfig.button2Label,
    button2Url: req.body.button2Url !== undefined ? req.body.button2Url : rpcConfig.button2Url
  };

  saveRpcConfig(updates);
  addLog(`[Cấu hình] Đã cập nhật Widget: "${updates.name}"`);

  if (currentClient && currentClient.user) {
    applyRPC(currentClient);
    return res.json({ success: true, message: 'Đã cập nhật Widget lên Discord ngay lập tức!' });
  } else {
    return res.json({ success: true, message: 'Đã lưu cấu hình (Đang chờ tài khoản kết nối).' });
  }
});

app.get('/status', (req, res) => {
  res.json({ botStatus, rpcConfig });
});

// Giao diện Web Control Panel
app.get('/', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Discord Widget Control Panel & Presets</title>
      <style>
        :root {
          --bg-dark: #1e1f22;
          --card-bg: #2b2d31;
          --input-bg: #1e1f22;
          --border: #3f4147;
          --text-main: #f2f3f5;
          --text-muted: #949ba4;
          --accent: #5865f2;
          --accent-hover: #4752c4;
          --green: #23a55a;
          --green-hover: #1f8b4d;
          --yellow: #f0b232;
        }
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
          background: var(--bg-dark);
          color: var(--text-main);
          padding: 20px 10px;
          margin: 0;
        }
        .container { max-width: 900px; margin: auto; }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 20px;
          border-bottom: 1px solid var(--border);
          padding-bottom: 15px;
        }
        .title { font-size: 22px; font-weight: bold; color: var(--text-main); }
        .badge {
          display: inline-block;
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: bold;
        }
        .badge-live { background: var(--green); color: #fff; }
        .badge-wait { background: var(--yellow); color: #000; }
        .card {
          background: var(--card-bg);
          border-radius: 12px;
          padding: 24px;
          margin-bottom: 24px;
          box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        }
        .card-magic {
          border: 2px solid var(--green);
          background: #23272d;
        }
        .grid-2 {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }
        @media (max-width: 768px) {
          .grid-2 { grid-template-columns: 1fr; }
        }
        label {
          display: block;
          font-size: 13px;
          font-weight: bold;
          color: var(--text-muted);
          text-transform: uppercase;
          margin-bottom: 6px;
        }
        input, select {
          width: 100%;
          box-sizing: border-box;
          background: var(--input-bg);
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 10px 12px;
          color: var(--text-main);
          font-size: 14px;
          margin-bottom: 14px;
          outline: none;
        }
        input:focus, select:focus { border-color: var(--accent); }
        .btn-submit {
          background: var(--accent);
          color: #fff;
          border: none;
          padding: 14px 28px;
          font-size: 15px;
          font-weight: bold;
          border-radius: 8px;
          cursor: pointer;
          width: 100%;
          transition: background 0.2s;
        }
        .btn-submit:hover { background: var(--accent-hover); }
        .btn-magic {
          background: var(--green);
          color: #fff;
          border: none;
          padding: 12px 24px;
          font-size: 14px;
          font-weight: bold;
          border-radius: 6px;
          cursor: pointer;
          white-space: nowrap;
          transition: background 0.2s;
        }
        .btn-magic:hover { background: var(--green-hover); }
        .btn-row {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          margin-bottom: 16px;
        }
        .btn-sm {
          padding: 8px 16px;
          font-size: 13px;
          font-weight: bold;
          border-radius: 6px;
          cursor: pointer;
          border: none;
          color: #fff;
          transition: opacity 0.2s;
        }
        .btn-sm:hover { opacity: 0.85; }
        .btn-save-preset { background: var(--green); }
        .btn-del-preset { background: #f23f43; }
        .btn-export { background: #4e5058; }
        .preview-box {
          background: #111214;
          border-radius: 10px;
          padding: 16px;
          display: flex;
          gap: 16px;
          align-items: center;
          margin-bottom: 10px;
          border: 1px solid #3f4147;
        }
        .preview-img {
          width: 75px;
          height: 75px;
          border-radius: 8px;
          object-fit: cover;
          background: #2b2d31;
        }
        .preview-info { flex: 1; }
        .preview-type { font-size: 11px; font-weight: bold; color: #949ba4; text-transform: uppercase; }
        .preview-name { font-size: 15px; font-weight: bold; color: #fff; }
        .preview-details { font-size: 13px; color: #dbdee1; }
        .preview-state { font-size: 13px; color: #949ba4; }
        .preview-btn {
          display: inline-block;
          background: #4e5058;
          color: #fff;
          padding: 6px 14px;
          border-radius: 4px;
          font-size: 13px;
          font-weight: 500;
          margin-top: 8px;
        }
        pre {
          background: #111214;
          padding: 12px;
          border-radius: 6px;
          color: #dbdee1;
          font-size: 12px;
          max-height: 180px;
          overflow-y: auto;
        }
        .toast {
          position: fixed;
          top: 20px;
          right: 20px;
          background: var(--green);
          color: #fff;
          padding: 14px 24px;
          border-radius: 8px;
          font-weight: bold;
          display: none;
          z-index: 999;
          box-shadow: 0 4px 16px rgba(0,0,0,0.5);
        }
      </style>
    </head>
    <body>
      <div id="toast" class="toast">Đã cập nhật thành công!</div>
      <div class="container">
        
        <div class="header">
          <div class="title">
            🎮 Bảng Điều Khiển Discord Widget
          </div>
          <div>
            ${botStatus.isLoggedIn 
              ? '<span class="badge badge-live">● Đang phát: ' + botStatus.userTag + '</span>' 
              : '<span class="badge badge-wait">⏳ Đang chờ Token...</span>'}
          </div>
        </div>

        <!-- Khung xem trước trực quan -->
        <div class="card">
          <label>Mô phỏng hiển thị trên Discord (Live Preview):</label>
          <div class="preview-box">
            <img id="pvImage" class="preview-img" src="${rpcConfig.largeImage || ''}" onerror="this.src='https://assets-global.website-files.com/6257adef93867e50d84d30e2/636e0a6a49cf127bf92de1e2_icon_clyde_blurple_RGB.png'" />
            <div class="preview-info">
              <div id="pvType" class="preview-type">Đang nghe</div>
              <div id="pvName" class="preview-name">${rpcConfig.name}</div>
              <div id="pvDetails" class="preview-details">${rpcConfig.details || ''}</div>
              <div id="pvState" class="preview-state">${rpcConfig.state || ''}</div>
              <div id="pvBtn1" class="preview-btn" style="${rpcConfig.button1Label ? '' : 'display:none;'}">${rpcConfig.button1Label || 'Nút bấm'}</div>
            </div>
          </div>
        </div>

        <!-- TÍNH NĂNG MỚI: DÁN LINK TỰ ĐỘNG NHẬN DIỆN BÀI HÁT -->
        <div class="card card-magic">
          <h3 style="margin-top: 0; color: #23a55a; display: flex; align-items: center; gap: 8px;">
            ✨ Tự Động Nhận Diện Bài Hát Bằng Link (1-Click)
          </h3>
          <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 14px;">
            Chỉ cần dán link <b>YouTube</b>, <b>YouTube Music</b> hoặc <b>Spotify</b> vào ô dưới đây. Hệ thống sẽ <b>tự động trích xuất tên bài hát, ca sĩ, ảnh bìa và tạo nút nghe nhạc lên Discord chỉ trong 1 giây!</b>
          </p>

          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <input type="text" id="musicUrlInput" placeholder="Dán link bài hát vào đây (VD: https://www.youtube.com/watch?v=... hoặc Spotify...)" style="flex: 1; margin-bottom: 0;" />
            <button type="button" id="btnParseMusic" class="btn-magic">⚡ Nhận Diện & Đổi Bài Ngay</button>
          </div>
          <div style="margin-top: 8px;">
            <label style="text-transform: none; font-size: 12px; cursor: pointer;">
              <input type="checkbox" id="chkAutoApply" checked style="width: auto; margin-right: 6px; vertical-align: middle;" />
              Tự động áp dụng lên Discord ngay sau khi nhận diện
            </label>
          </div>
        </div>

        <!-- KHU VỰC QUẢN LÝ PRESET VĨNH VIỄN -->
        <div class="card" style="border: 1px solid #5865f2;">
          <h3 style="margin-top: 0; color: #5865f2;">📁 Bộ Quản Lý Preset (Lưu trữ vĩnh viễn không sợ mất)</h3>
          <p style="color: var(--text-muted); font-size: 13px;">
            Mọi bài hát bạn lưu thành Preset sẽ được giữ lại vĩnh viễn trên trình duyệt của bạn và tự động tải lại mỗi khi mở trang.
          </p>

          <label>Chọn Preset để nạp nhanh:</label>
          <div class="btn-row">
            <select id="presetSelect" style="flex: 1; margin-bottom: 0;">
              <!-- Sẽ được nạp tự động từ localStorage -->
            </select>
            <button type="button" id="btnLoadPreset" class="btn-sm" style="background: var(--accent);">⚡ Nạp Preset Này</button>
            <button type="button" id="btnDeletePreset" class="btn-sm btn-del-preset">🗑️ Xóa</button>
          </div>

          <div class="btn-row" style="margin-top: 15px;">
            <input type="text" id="newPresetName" placeholder="Đặt tên Preset mới (VD: Bài hát yêu thích, Chill, HSR...)" style="flex: 1; margin-bottom: 0;" />
            <button type="button" id="btnSavePreset" class="btn-sm btn-save-preset">💾 Lưu Cấu Hình Này Thành Preset Mới</button>
          </div>

          <div class="btn-row" style="margin-top: 15px; margin-bottom: 0;">
            <button type="button" id="btnExportPresets" class="btn-sm btn-export">📥 Xuất file Preset (.json)</button>
            <label class="btn-sm btn-export" style="cursor: pointer; margin-bottom: 0; display: inline-flex; align-items: center;">
              📤 Nhập file Preset (.json)
              <input type="file" id="fileImportPresets" accept=".json" style="display: none;" />
            </label>
          </div>
        </div>

        <!-- Form chỉnh sửa thông số Widget -->
        <div class="card">
          <h3 style="margin-top: 0; color: #5865f2;">⚡ Tùy chỉnh chi tiết thông tin bài hát</h3>

          <form id="configForm">
            <input type="hidden" name="key" value="${SYNC_KEY}" />

            <div class="grid-2">
              <div>
                <label>Tên Bài Hát (Name):</label>
                <input type="text" id="inpName" name="name" value="${rpcConfig.name}" required />
              </div>
              <div>
                <label>Loại Hoạt Động (Activity Type):</label>
                <select id="inpType" name="type">
                  <option value="LISTENING" ${rpcConfig.type === 'LISTENING' ? 'selected' : ''}>LISTENING (Đang nghe)</option>
                  <option value="PLAYING" ${rpcConfig.type === 'PLAYING' ? 'selected' : ''}>PLAYING (Đang chơi)</option>
                  <option value="WATCHING" ${rpcConfig.type === 'WATCHING' ? 'selected' : ''}>WATCHING (Đang xem)</option>
                  <option value="COMPETING" ${rpcConfig.type === 'COMPETING' ? 'selected' : ''}>COMPETING (Đang thi đấu)</option>
                  <option value="STREAMING" ${rpcConfig.type === 'STREAMING' ? 'selected' : ''}>STREAMING (Trực tiếp)</option>
                </select>
              </div>
            </div>

            <div class="grid-2">
              <div>
                <label>Ca sĩ / Nghệ sĩ (Details):</label>
                <input type="text" id="inpDetails" name="details" placeholder="VD: Rick Astley / Lost Lullaby" value="${rpcConfig.details || ''}" />
              </div>
              <div>
                <label>Nền tảng / Album (State):</label>
                <input type="text" id="inpState" name="state" placeholder="VD: YouTube Music / Spotify" value="${rpcConfig.state || ''}" />
              </div>
            </div>

            <div class="grid-2">
              <div>
                <label>Ảnh bìa (Large Image Key / URL):</label>
                <input type="text" id="inpImage" name="largeImage" placeholder="youtube:ID hoặc link ảnh..." value="${rpcConfig.largeImage || ''}" />
              </div>
              <div>
                <label>Chú thích ảnh bìa (Tooltip):</label>
                <input type="text" id="inpImageText" name="largeText" placeholder="VD: Tên bài hát" value="${rpcConfig.largeText || ''}" />
              </div>
            </div>

            <div class="grid-2">
              <div>
                <label>Nút bấm 1 - Tên nút (Label):</label>
                <input type="text" id="inpBtn1" name="button1Label" placeholder="VD: Nghe trên YouTube" value="${rpcConfig.button1Label || ''}" />
              </div>
              <div>
                <label>Nút bấm 1 - Link nghe (URL):</label>
                <input type="text" id="inpBtn1Url" name="button1Url" placeholder="https://youtube.com/..." value="${rpcConfig.button1Url || ''}" />
              </div>
            </div>

            <div class="grid-2">
              <div>
                <label>Nút bấm 2 - Tên nút (Tùy chọn):</label>
                <input type="text" id="inpBtn2" name="button2Label" placeholder="VD: YouTube" value="${rpcConfig.button2Label || ''}" />
              </div>
              <div>
                <label>Nút bấm 2 - Link nghe (Tùy chọn):</label>
                <input type="text" id="inpBtn2Url" name="button2Url" placeholder="https://..." value="${rpcConfig.button2Url || ''}" />
              </div>
            </div>

            <button type="submit" class="btn-submit">🚀 Áp Dụng Lên Discord Ngay Lập Tức</button>
          </form>
        </div>

        <!-- Form cập nhật Token dự phòng -->
        <div class="card">
          <h3 style="margin-top: 0; color: #23a55a;">🔑 Cập nhật Discord Token (Khi cần đổi tài khoản)</h3>
          <form id="tokenForm">
            <input type="hidden" name="key" value="${SYNC_KEY}" />
            <label>Discord Token mới:</label>
            <input type="password" name="token" placeholder="Chỉ dán vào khi muốn đổi token mới..." required />
            <button type="submit" class="btn-submit" style="background: var(--green);">🔄 Cập Nhật Token</button>
          </form>
        </div>

        <!-- Nhật ký -->
        <div class="card">
          <label>📋 Nhật ký máy chủ (Logs):</label>
          <pre>${botStatus.debugMessages.join('\n') || 'Chưa có nhật ký'}</pre>
        </div>

      </div>

      <script>
        const defaultPresetLamia = {
          name: 'Lamia_X_3.14',
          type: 'PLAYING',
          details: '',
          state: 'Vanguard Sound Studio',
          largeImage: 'https://media.discordapp.net/attachments/1504440289606111353/1566607690615099573/b095a8c70de8503d649c594d7eaad1f5.png?ex=6ae9289b&is=6ae7d71b&hm=10c9e6964c551a16febd71cf8f5508c7b4ca33e9468dda3dd87e93aa53284221&=&format=webp&quality=lossless',
          largeText: 'Lamia - Lost Lullaby',
          button1Label: 'Play ?',
          button1Url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ&start_radio=1',
          button2Label: '',
          button2Url: ''
        };

        function getStoredPresets() {
          try {
            const raw = localStorage.getItem('discord_widget_presets');
            if (raw) return JSON.parse(raw);
          } catch (e) {}
          return { 'Lamia (Mặc định)': defaultPresetLamia };
        }

        function saveStoredPresets(presets) {
          localStorage.setItem('discord_widget_presets', JSON.stringify(presets));
          renderPresetOptions();
        }

        function renderPresetOptions() {
          const presets = getStoredPresets();
          const select = document.getElementById('presetSelect');
          select.innerHTML = '';
          for (let name in presets) {
            const opt = document.createElement('option');
            opt.value = name;
            opt.innerText = name;
            select.appendChild(opt);
          }
          const active = localStorage.getItem('discord_widget_active_preset');
          if (active && presets[active]) select.value = active;
        }

        function resolvePreviewImage(imgVal, rawPreviewUrl) {
          if (rawPreviewUrl) return rawPreviewUrl;
          if (imgVal && imgVal.startsWith('youtube:')) {
            const id = imgVal.replace('youtube:', '');
            return 'https://i.ytimg.com/vi/' + id + '/hqdefault.jpg';
          }
          return imgVal || '';
        }

        function fillFormWithPreset(data, previewUrl) {
          document.getElementById('inpName').value = data.name || '';
          document.getElementById('inpType').value = data.type || 'LISTENING';
          document.getElementById('inpDetails').value = data.details || '';
          document.getElementById('inpState').value = data.state || '';
          document.getElementById('inpImage').value = data.largeImage || '';
          document.getElementById('inpImageText').value = data.largeText || '';
          document.getElementById('inpBtn1').value = data.button1Label || '';
          document.getElementById('inpBtn1Url').value = data.button1Url || '';
          document.getElementById('inpBtn2').value = data.button2Label || '';
          document.getElementById('inpBtn2Url').value = data.button2Url || '';
          updateLivePreview(previewUrl);
        }

        function updateLivePreview(forcedImg) {
          const name = document.getElementById('inpName').value;
          const details = document.getElementById('inpDetails').value;
          const state = document.getElementById('inpState').value;
          const imgVal = document.getElementById('inpImage').value;
          const btn1 = document.getElementById('inpBtn1').value;
          const type = document.getElementById('inpType').value;

          document.getElementById('pvName').innerText = name || 'Tên bài hát';
          document.getElementById('pvDetails').innerText = details;
          document.getElementById('pvState').innerText = state;
          document.getElementById('pvImage').src = resolvePreviewImage(imgVal, forcedImg);
          const b1 = document.getElementById('pvBtn1');
          b1.innerText = btn1 || 'Nút bấm';
          b1.style.display = btn1 ? 'inline-block' : 'none';

          const types = { PLAYING: 'Đang chơi', LISTENING: 'Đang nghe', WATCHING: 'Đang xem', COMPETING: 'Đang thi đấu', STREAMING: 'Đang phát trực tiếp' };
          document.getElementById('pvType').innerText = types[type] || 'Đang nghe';
        }

        ['inpName', 'inpDetails', 'inpState', 'inpImage', 'inpBtn1'].forEach(id => {
          document.getElementById(id).addEventListener('input', () => updateLivePreview());
        });
        document.getElementById('inpType').addEventListener('change', () => updateLivePreview());

        function showToast(msg, isError = false) {
          const toast = document.getElementById('toast');
          toast.innerText = msg;
          toast.style.background = isError ? '#f23f43' : '#23a55a';
          toast.style.display = 'block';
          setTimeout(() => toast.style.display = 'none', 4000);
        }

        // TỰ ĐỘNG NHẬN DIỆN BÀI HÁT TỪ LINK
        async function handleParseMusic() {
          const urlInput = document.getElementById('musicUrlInput');
          const url = (urlInput.value || '').trim();
          if (!url) {
            alert('Vui lòng dán link YouTube hoặc Spotify vào ô trước!');
            return;
          }

          const autoApply = document.getElementById('chkAutoApply').checked;
          showToast('⏳ Đang nhận diện bài hát từ đường link...');

          try {
            const res = await fetch('/api/parse-music', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url, autoApply })
            });
            const json = await res.json();
            if (json.success && json.data) {
              const info = json.data;
              fillFormWithPreset(info, info.previewImage);

              // Tự động lưu bài này vào Preset & LocalStorage
              localStorage.setItem('discord_widget_last_applied', JSON.stringify(info));
              const presets = getStoredPresets();
              presets[info.name] = info;
              localStorage.setItem('discord_widget_active_preset', info.name);
              saveStoredPresets(presets);

              if (autoApply) {
                showToast('✨ Đã nhận diện & cập nhật bài hát "' + info.name + '" lên Discord!');
              } else {
                showToast('✅ Đã nhận diện thông tin! Hãy bấm nút Áp Dụng Lên Discord.');
              }
              urlInput.value = '';
            } else {
              showToast('❌ ' + (json.error || 'Không thể nhận diện bài hát'), true);
            }
          } catch (err) {
            showToast('❌ Không thể kết nối tới server nhận diện', true);
          }
        }

        document.getElementById('btnParseMusic').onclick = handleParseMusic;

        // Tự động nhận diện ngay khi dán link (Paste)
        document.getElementById('musicUrlInput').addEventListener('paste', () => {
          setTimeout(handleParseMusic, 150);
        });

        // Nạp Preset
        document.getElementById('btnLoadPreset').onclick = () => {
          const select = document.getElementById('presetSelect');
          const presets = getStoredPresets();
          if (presets[select.value]) {
            fillFormWithPreset(presets[select.value]);
            localStorage.setItem('discord_widget_active_preset', select.value);
            showToast('✅ Đã nạp thông tin Preset: ' + select.value);
          }
        };

        // Lưu Preset mới
        document.getElementById('btnSavePreset').onclick = () => {
          const nameInput = document.getElementById('newPresetName');
          const presetName = nameInput.value.trim();
          if (!presetName) {
            alert('Vui lòng nhập tên cho Preset mới!');
            return;
          }

          const currentConfig = {
            name: document.getElementById('inpName').value,
            type: document.getElementById('inpType').value,
            details: document.getElementById('inpDetails').value,
            state: document.getElementById('inpState').value,
            largeImage: document.getElementById('inpImage').value,
            largeText: document.getElementById('inpImageText').value,
            button1Label: document.getElementById('inpBtn1').value,
            button1Url: document.getElementById('inpBtn1Url').value,
            button2Label: document.getElementById('inpBtn2').value,
            button2Url: document.getElementById('inpBtn2Url').value
          };

          const presets = getStoredPresets();
          presets[presetName] = currentConfig;
          localStorage.setItem('discord_widget_active_preset', presetName);
          saveStoredPresets(presets);
          nameInput.value = '';
          showToast('💾 Đã lưu thành Preset "' + presetName + '" vĩnh viễn!');
        };

        // Xóa Preset
        document.getElementById('btnDeletePreset').onclick = () => {
          const select = document.getElementById('presetSelect');
          if (select.value === 'Lamia (Mặc định)') {
            alert('Không thể xóa Preset mặc định!');
            return;
          }
          if (confirm('Bạn có chắc muốn xóa Preset: ' + select.value + '?')) {
            const presets = getStoredPresets();
            delete presets[select.value];
            saveStoredPresets(presets);
            showToast('🗑️ Đã xóa Preset');
          }
        };

        // Xuất file JSON
        document.getElementById('btnExportPresets').onclick = () => {
          const presets = getStoredPresets();
          const blob = new Blob([JSON.stringify(presets, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'discord_widget_presets.json';
          a.click();
          URL.revokeObjectURL(url);
        };

        // Nhập file JSON
        document.getElementById('fileImportPresets').onchange = (e) => {
          const file = e.target.files[0];
          if (!file) return;
          const reader = new FileReader();
          reader.onload = (event) => {
            try {
              const imported = JSON.parse(event.target.result);
              const current = getStoredPresets();
              const merged = { ...current, ...imported };
              saveStoredPresets(merged);
              showToast('📥 Đã nhập thành công các Preset từ file!');
            } catch (err) {
              alert('File JSON không hợp lệ!');
            }
          };
          reader.readAsText(file);
        };

        // Gửi áp dụng lên Discord
        document.getElementById('configForm').onsubmit = async (e) => {
          e.preventDefault();
          const formData = new FormData(e.target);
          const data = Object.fromEntries(formData.entries());
          data.showTimestamp = true;

          localStorage.setItem('discord_widget_last_applied', JSON.stringify(data));

          try {
            const res = await fetch('/api/update-config', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
            });
            const json = await res.json();
            if (json.success) {
              showToast('🚀 ' + json.message);
            } else {
              showToast('❌ ' + (json.error || 'Lỗi không xác định'), true);
            }
          } catch (err) {
            showToast('❌ Không thể kết nối tới server', true);
          }
        };

        // Form Token
        document.getElementById('tokenForm').onsubmit = async (e) => {
          e.preventDefault();
          const formData = new FormData(e.target);
          const data = Object.fromEntries(formData.entries());

          showToast('⏳ Đang kết nối với Token mới...');
          try {
            const res = await fetch('/api/update-token', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
            });
            const json = await res.json();
            if (json.success) {
              showToast('✅ ' + json.message);
              setTimeout(() => location.reload(), 2000);
            } else {
              showToast('❌ ' + (json.error || 'Lỗi không xác định'), true);
            }
          } catch (err) {
            showToast('❌ Không thể kết nối tới server', true);
          }
        };

        window.onload = () => {
          renderPresetOptions();
          const lastApplied = localStorage.getItem('discord_widget_last_applied');
          if (lastApplied) {
            try {
              const parsed = JSON.parse(lastApplied);
              fillFormWithPreset(parsed);
              fetch('/status').then(r => r.json()).then(st => {
                if (st.rpcConfig && st.rpcConfig.name !== parsed.name) {
                  document.getElementById('configForm').dispatchEvent(new Event('submit'));
                }
              }).catch(() => {});
            } catch (e) {}
          }
        };
      </script>
    </body>
    </html>
  `);
});

// Bảo vệ tiến trình khỏi crash do unhandled rejection hoặc uncaught exception (tránh lỗi status 134)
process.on('unhandledRejection', (reason) => {
  const msg = reason?.stack || reason?.message || String(reason);
  console.error('[Unhandled Rejection]:', msg);
  addLog(`[Cảnh báo hệ thống]: ${reason?.message || msg}`);
});

process.on('uncaughtException', (err) => {
  const msg = err?.stack || err?.message || String(err);
  console.error('[Uncaught Exception]:', msg);
  addLog(`[Lỗi hệ thống]: ${err?.message || msg}`);
});

// Giám sát và dọn dẹp RAM định kỳ ngăn ngừa tràn 512MB RAM của Render (ngăn lỗi exit code 134)
setInterval(() => {
  if (global.gc) {
    try { global.gc(); } catch (e) {}
  }
  const mem = process.memoryUsage();
  if (mem.rss > 320 * 1024 * 1024) {
    console.warn(`[Cảnh báo RAM] Bộ nhớ đạt ${(mem.rss / 1024 / 1024).toFixed(1)}MB. Đang giải phóng caches...`);
    if (currentClient) {
      if (currentClient.users?.cache) currentClient.users.cache.clear();
      if (currentClient.guilds?.cache) {
        currentClient.guilds.cache.forEach(g => {
          if (g.members?.cache) g.members.cache.clear();
          if (g.presences?.cache) g.presences.cache.clear();
          if (g.voiceStates?.cache) g.voiceStates.cache.clear();
          if (g.channels?.cache) {
            g.channels.cache.forEach(ch => {
              if (ch.messages?.cache) ch.messages.cache.clear();
            });
          }
        });
      }
    }
  }
}, 10 * 60 * 1000).unref();

const BIND_HOST = process.env.ORCHESTRATOR ? '127.0.0.1' : '0.0.0.0';

app.listen(PORT, BIND_HOST, async () => {
  addLog(`[Web Server] Đang lắng nghe trên ${BIND_HOST}:${PORT}`);
  addLog(`[Bảo mật] SYNC_KEY hiện tại là: ${SYNC_KEY}`);

  // Nạp cấu hình bài hát lưu trên Cloud trước khi kết nối Discord
  await syncConfigFromCloud();

  const rawToken = process.env.USER_TOKEN || process.env.TOKEN_USER || process.env.TOKEN_WIDGET || process.env.WIDGET_TOKEN || loadWorkingToken();
  const startupToken = sanitizeToken(rawToken);
  if (startupToken) {
    connectWithToken(startupToken).catch((err) => {
      addLog(`[Khởi động] Không thể kết nối với Token: ${err.message}.`);
    });
  } else {
    addLog('[Thông báo] Đang chờ cấu hình USER_TOKEN trong Render Environment hoặc qua Tampermonkey...');
  }
});