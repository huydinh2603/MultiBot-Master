// ==============================================================================
// Multi-Bot Master — PM2 Ecosystem Configuration
// Ultra-optimized for 512MB RAM Container on Render.com Free Tier
// ==============================================================================

module.exports = {
  apps: [
    // --------------------------------------------------------------------------
    // 1. Central Gateway & Keepalive Hub Server
    // --------------------------------------------------------------------------
    {
      name: 'hub-server',
      script: 'hub_server.js',
      cwd: './',
      node_args: '--max-old-space-size=48 --expose-gc',
      env: {
        NODE_ENV: 'production',
        PORT: process.env.PORT || '8080',
        WIDGET_PORT: '3005',
      },
      restart_delay: 2000,
      max_restarts: 10,
      max_memory_restart: '80M',
    },

    // --------------------------------------------------------------------------
    // 2. AutoRes Bot (Python 3.12)
    // --------------------------------------------------------------------------
    {
      name: 'bot-autores',
      script: 'main.py',
      cwd: './bots/autores',
      interpreter: 'python3',
      env: {
        PYTHONUNBUFFERED: '1',
        MALLOC_TRIM_THRESHOLD_: '100000',
        ORCHESTRATOR: 'true',
        DISABLE_KEEP_ALIVE: 'true',
        AUTORES_TOKEN: process.env.TOKEN_AUTORES || process.env.AUTORES_TOKEN || process.env.DISCORD_BOT_TOKEN || process.env.DISCORD_TOKEN,
      },
      restart_delay: 5000,
      max_restarts: 10,
      max_memory_restart: '100M',
    },

    // --------------------------------------------------------------------------
    // 3. VoiceGuard Bot (Python 3.12)
    // --------------------------------------------------------------------------
    {
      name: 'bot-voiceguard',
      script: 'main.py',
      cwd: './bots/voiceguard',
      interpreter: 'python3',
      env: {
        PYTHONUNBUFFERED: '1',
        MALLOC_TRIM_THRESHOLD_: '100000',
        ORCHESTRATOR: 'true',
        DISABLE_KEEP_ALIVE: 'true',
        VOICEGUARD_TOKEN: process.env.TOKEN_VOICEGUARD || process.env.VOICEGUARD_TOKEN || process.env.DISCORD_TOKEN,
        VOICEGUARD_CHANNEL_ID: process.env.VOICEGUARD_CHANNEL_ID || process.env.VOICE_CHANNEL_ID,
      },
      restart_delay: 5000,
      max_restarts: 10,
      max_memory_restart: '100M',
    },

    // --------------------------------------------------------------------------
    // 4. Moderator Bot (Python 3.12)
    // --------------------------------------------------------------------------
    {
      name: 'bot-moderator',
      script: 'main.py',
      cwd: './bots/moderator',
      interpreter: 'python3',
      env: {
        PYTHONUNBUFFERED: '1',
        MALLOC_TRIM_THRESHOLD_: '100000',
        ORCHESTRATOR: 'true',
        DISABLE_KEEP_ALIVE: 'true',
        MODERATOR_TOKEN: process.env.TOKEN_MODERATOR || process.env.MODERATOR_TOKEN || process.env.DISCORD_TOKEN,
      },
      restart_delay: 5000,
      max_restarts: 10,
      max_memory_restart: '110M',
    },

    // --------------------------------------------------------------------------
    // 5. Sheriff Bot (Node.js 20)
    // --------------------------------------------------------------------------
    {
      name: 'bot-sheriff',
      script: 'src/index.js',
      cwd: './bots/sheriff',
      node_args: '--max-old-space-size=64 --expose-gc --dns-result-order=ipv4first',
      env: {
        NODE_ENV: 'production',
        ORCHESTRATOR: 'true',
        DISABLE_KEEP_ALIVE: 'true',
        SHERIFF_TOKEN: process.env.TOKEN_SHERIFF || process.env.SHERIFF_TOKEN || process.env.DISCORD_TOKEN,
      },
      restart_delay: 5000,
      max_restarts: 10,
      max_memory_restart: '100M',
    },

    // --------------------------------------------------------------------------
    // 6. Widget Bot (Node.js 20)
    // --------------------------------------------------------------------------
    {
      name: 'bot-widget',
      script: 'index.js',
      cwd: './bots/widget',
      node_args: '--max-old-space-size=64 --expose-gc',
      env: {
        NODE_ENV: 'production',
        ORCHESTRATOR: 'true',
        WIDGET_PORT: '3005',
        WIDGET_TOKEN: process.env.USER_TOKEN || process.env.TOKEN_USER || process.env.TOKEN_WIDGET || process.env.WIDGET_TOKEN || process.env.DISCORD_TOKEN,
      },
      restart_delay: 5000,
      max_restarts: 10,
      max_memory_restart: '100M',
    },
  ],
};
