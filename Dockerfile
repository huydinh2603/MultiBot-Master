# ==============================================================================
# Multi-Bot Master — Dual-Runtime Production Dockerfile (Node.js 20 + Python 3.12)
# Tailored for Render.com Free Tier (512MB RAM Limit)
# ==============================================================================

FROM node:20-bookworm-slim

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# 1. Install system packages & Python 3 runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    libffi-dev \
    libnacl-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Install PM2 globally
RUN npm install -g pm2

# 3. Create Python virtual environment and install Python dependencies
RUN python3 -m venv /opt/venv
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy and install Node.js dependencies for each bot
COPY package.json ./
RUN npm install --omit=dev

COPY bots/sheriff/package.json ./bots/sheriff/
RUN cd bots/sheriff && npm install --omit=dev

COPY bots/widget/package.json ./bots/widget/
RUN cd bots/widget && npm install --omit=dev

# 5. Copy full project files
COPY . .

# 6. Expose default port (Render will override via $PORT)
EXPOSE 8080

# 7. Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:' + (process.env.PORT || 8080) + '/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1); }).on('error', () => process.exit(1));"

# 8. Start all 5 bots + Hub Gateway using PM2 process manager
CMD ["pm2-runtime", "ecosystem.config.cjs"]
