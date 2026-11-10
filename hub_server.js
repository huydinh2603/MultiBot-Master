// ==============================================================================
// Multi-Bot Master — Central Gateway, Reverse Proxy & Telemetry Dashboard
// ==============================================================================
const http = require('node:http');
const os = require('node:os');

const PORT = parseInt(process.env.PORT || '8080', 10);
const WIDGET_PORT = parseInt(process.env.WIDGET_PORT || '3005', 10);
const startTime = Date.now();

// Proxy helper for Widget HTTP requests
function proxyToWidget(req, res, targetPath) {
  const options = {
    hostname: '127.0.0.1',
    port: WIDGET_PORT,
    path: targetPath || req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${WIDGET_PORT}` },
  };

  const proxyReq = http.request(options, proxyRes => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', err => {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({
      error: 'Widget service is starting or unreachable',
      details: err.message,
    }));
  });

  req.pipe(proxyReq, { end: true });
}

// Format duration
function formatUptime(seconds) {
  const d = Math.floor(seconds / (3600 * 24));
  const h = Math.floor((seconds % (3600 * 24)) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(' ');
}

// Check configured tokens
function getBotStatuses() {
  const hasToken = (key) => !!process.env[key] && process.env[key].trim().length > 10;
  return {
    autores: {
      name: 'AutoRes',
      type: 'Python 3.12 (discord.py)',
      description: 'Smart Auto-Response & Custom Commands',
      configured: hasToken('TOKEN_AUTORES') || hasToken('DISCORD_BOT_TOKEN') || hasToken('DISCORD_TOKEN'),
    },
    voiceguard: {
      name: 'VoiceGuard',
      type: 'Python 3.12 (discord.py[voice])',
      description: '24/7 Voice Channel Keeper & Watchdog',
      configured: hasToken('TOKEN_VOICEGUARD') || hasToken('VOICEGUARD_TOKEN') || hasToken('DISCORD_TOKEN'),
    },
    moderator: {
      name: 'Moderator',
      type: 'Python 3.12 (discord.py)',
      description: 'Automod, Tickets, Verification, Logging',
      configured: hasToken('TOKEN_MODERATOR') || hasToken('MODERATOR_TOKEN') || hasToken('DISCORD_TOKEN'),
    },
    sheriff: {
      name: 'Sheriff',
      type: 'Node.js 20 (discord.js v14)',
      description: 'Tactical Mute Combat & Economy',
      configured: hasToken('TOKEN_SHERIFF') || hasToken('SHERIFF_TOKEN') || hasToken('DISCORD_TOKEN'),
    },
    widget: {
      name: 'Widget',
      type: 'Node.js 20 (discord.js-selfbot-v13)',
      description: 'Custom Rich Presence 24/7 & Token Sync',
      configured: hasToken('TOKEN_WIDGET') || hasToken('WIDGET_TOKEN') || hasToken('DISCORD_TOKEN'),
    },
  };
}

const server = http.createServer((req, res) => {
  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = parsedUrl.pathname;

  // 1. Health & Ping endpoints for Render Keep-Alive / UptimeRobot / Cron
  if (pathname === '/health' || pathname === '/ping') {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('OK - MultiBot Orchestrator Healthy');
  }

  // 2. Status Telemetry API
  if (pathname === '/status') {
    const mem = process.memoryUsage();
    const uptimeSec = (Date.now() - startTime) / 1000;
    const totalMemMb = Math.round(os.totalmem() / 1024 / 1024);
    const freeMemMb = Math.round(os.freemem() / 1024 / 1024);
    const usedMemMb = totalMemMb - freeMemMb;

    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    return res.end(JSON.stringify({
      orchestrator: 'MultiBot-Master v1.0.0',
      status: 'healthy',
      uptimeSeconds: Math.floor(uptimeSec),
      uptimeHuman: formatUptime(uptimeSec),
      systemMemory: {
        totalMb: totalMemMb,
        freeMb: freeMemMb,
        usedMb: usedMemMb,
      },
      hubProcessMemory: {
        rssMb: (mem.rss / 1024 / 1024).toFixed(2),
        heapUsedMb: (mem.heapUsed / 1024 / 1024).toFixed(2),
      },
      bots: getBotStatuses(),
    }, null, 2));
  }

  // 3. Proxy API calls directly to Widget (for Tampermonkey auto-sync script and music API)
  if (pathname.startsWith('/api/')) {
    return proxyToWidget(req, res);
  }

  // 4. Proxy /widget to Widget's Express Web UI
  if (pathname === '/widget' || pathname.startsWith('/widget/')) {
    const target = pathname === '/widget' ? '/' : pathname.replace(/^\/widget/, '') || '/';
    return proxyToWidget(req, res, target + (parsedUrl.search || ''));
  }

  // 5. Root Dashboard (Dark Modern UI)
  if (pathname === '/') {
    const uptimeSec = (Date.now() - startTime) / 1000;
    const uptimeText = formatUptime(uptimeSec);
    const bots = getBotStatuses();
    const botKeys = Object.keys(bots);
    const configuredCount = botKeys.filter(k => bots[k].configured).length;

    const html = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MultiBot Master — 24/7 Orchestrator Dashboard</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --success: #22c55e;
      --warning: #eab308;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 30px 20px;
    }
    .container {
      max-width: 960px;
      width: 100%;
    }
    header {
      text-align: center;
      margin-bottom: 30px;
    }
    h1 {
      font-size: 2.2rem;
      font-weight: 800;
      background: linear-gradient(135deg, #818cf8, #38bdf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
    }
    .subtitle {
      color: var(--text-muted);
      font-size: 1rem;
    }
    .metrics-bar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 26px;
    }
    .metric-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px;
      text-align: center;
    }
    .metric-label {
      font-size: 0.85rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }
    .metric-val {
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--text-main);
    }
    .bot-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
      margin-bottom: 30px;
    }
    .bot-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .bot-card:hover {
      transform: translateY(-2px);
      border-color: #64748b;
    }
    .bot-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .bot-name {
      font-size: 1.25rem;
      font-weight: 700;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 9999px;
    }
    .badge-online {
      background: rgba(34, 197, 94, 0.15);
      color: var(--success);
      border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .badge-missing {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .badge-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
    }
    .bot-type {
      font-size: 0.8rem;
      color: #38bdf8;
      font-family: monospace;
      margin-bottom: 8px;
    }
    .bot-desc {
      color: var(--text-muted);
      font-size: 0.9rem;
      line-height: 1.4;
      margin-bottom: 16px;
      flex-grow: 1;
    }
    .bot-actions {
      display: flex;
      gap: 8px;
    }
    .btn {
      display: inline-block;
      background: var(--accent);
      color: white;
      text-decoration: none;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      text-align: center;
      transition: background 0.2s;
    }
    .btn:hover { background: var(--accent-hover); }
    .btn-secondary {
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
    }
    .btn-secondary:hover {
      background: rgba(255,255,255,0.05);
      color: var(--text-main);
    }
    footer {
      text-align: center;
      color: var(--text-muted);
      font-size: 0.85rem;
      margin-top: auto;
      padding-top: 20px;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>MultiBot Orchestrator</h1>
      <p class="subtitle">5 Discord Bots Running Concurrently in 1 Single 24/7 Container</p>
    </header>

    <div class="metrics-bar">
      <div class="metric-card">
        <div class="metric-label">Trạng Thái</div>
        <div class="metric-val" style="color: var(--success);">ONLINE 24/7</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Thời Gian Hoạt Động</div>
        <div class="metric-val">${uptimeText}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Bots Cấu Hình</div>
        <div class="metric-val">${configuredCount} / 5</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Dung Lượng RAM</div>
        <div class="metric-val" style="color: #38bdf8;">~220 MB <span style="font-size: 0.9rem; color: var(--text-muted);">/ 512MB</span></div>
      </div>
    </div>

    <div class="bot-grid">
      ${botKeys.map(k => {
        const b = bots[k];
        const badgeClass = b.configured ? 'badge-online' : 'badge-missing';
        const badgeText = b.configured ? 'ĐÃ CẤU HÌNH' : 'CHƯA CÓ TOKEN';
        const isWidget = k === 'widget';
        return `
        <div class="bot-card">
          <div>
            <div class="bot-top">
              <span class="bot-name">${b.name}</span>
              <span class="badge ${badgeClass}"><span class="badge-dot"></span>${badgeText}</span>
            </div>
            <div class="bot-type">${b.type}</div>
            <div class="bot-desc">${b.description}</div>
          </div>
          <div class="bot-actions">
            ${isWidget ? '<a href="/widget" class="btn">Mở Giao Diện Widget</a>' : ''}
            <a href="/status" class="btn btn-secondary">Xem JSON Status</a>
          </div>
        </div>`;
      }).join('')}
    </div>

    <footer>
      <p>MultiBot-Master • Designed for Render.com Free Tier 512MB • Zero Downtime</p>
    </footer>
  </div>
</body>
</html>`;

    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(html);
  }

  // Fallback 404
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not Found');
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[Hub Server] Multi-Bot Central Gateway listening on 0.0.0.0:${PORT}`);
  console.log(`[Hub Server] Keep-alive endpoint: http://0.0.0.0:${PORT}/health`);
  console.log(`[Hub Server] Status endpoint:     http://0.0.0.0:${PORT}/status`);
});
