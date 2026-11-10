// ==UserScript==
// @name         Discord Token Auto-Sync to Render
// @namespace    http://tampermonkey.net/
// @version      1.3
// @description  Tự động trích xuất token Discord và đồng bộ lên server Render để duy trì Rich Presence 24/7
// @author       Antigravity
// @match        https://discord.com/*
// @connect      *
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // SỬA URL NÀY THÀNH DOMAIN DỊCH VỤ RENDER CỦA BẠN (VD: https://multibot-master.onrender.com)
  const RENDER_DOMAIN = 'https://multibot-master.onrender.com';
  const RENDER_ENDPOINT = `${RENDER_DOMAIN}/api/update-token`;
  const SYNC_KEY = 'LamiaSync2026';

  function showNotification(text, color = '#23a55a') {
    const existing = document.getElementById('render-sync-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'render-sync-toast';
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.backgroundColor = color;
    toast.style.color = '#ffffff';
    toast.style.padding = '14px 22px';
    toast.style.borderRadius = '8px';
    toast.style.boxShadow = '0 6px 18px rgba(0,0,0,0.6)';
    toast.style.zIndex = '999999';
    toast.style.fontSize = '14px';
    toast.style.fontWeight = 'bold';
    toast.style.fontFamily = 'sans-serif';
    toast.style.transition = 'all 0.3s ease';
    toast.innerText = text;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 400);
    }, 7000);
  }

  // Phương thức trích xuất chuẩn 100% từ Webpack Chunk Discord
  function extractToken() {
    try {
      const win = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
      if (!win.webpackChunkdiscord_app) return null;

      let m = [];
      win.webpackChunkdiscord_app.push([
        [''],
        {},
        e => {
          m = [];
          for (let c in e.c) m.push(e.c[c]);
        }
      ]);

      const mod = m.find(item => item?.exports?.default?.getToken !== undefined);
      if (mod && typeof mod.exports.default.getToken === 'function') {
        const t = mod.exports.default.getToken();
        if (t && t.length > 20) return t;
      }

      const mod2 = m.find(item => item?.exports?.getToken !== undefined);
      if (mod2 && typeof mod2.exports.getToken === 'function') {
        const t = mod2.exports.getToken();
        if (t && t.length > 20) return t;
      }
    } catch (e) {
      console.error('[AutoSync] Lỗi đọc token:', e);
    }
    return null;
  }

  function sendTokenToRender(token, retryCount = 0) {
    console.log('[AutoSync] Đang gửi token lên Render:', token.substring(0, 10) + '...');
    showNotification('⏳ Đang gửi Token Discord lên Render...', '#5865f2');

    GM_xmlhttpRequest({
      method: 'POST',
      url: RENDER_ENDPOINT,
      headers: {
        'Content-Type': 'application/json',
        'x-sync-key': SYNC_KEY
      },
      data: JSON.stringify({ token: token, key: SYNC_KEY }),
      timeout: 15000,
      onload: function (response) {
        if (response.status === 502 || response.status === 503 || response.responseText.includes('<!DOCTYPE') || response.responseText.includes('<html')) {
          if (retryCount < 4) {
            showNotification('⏳ Server Render đang thức giấc, sẽ thử lại sau 6 giây...', '#f0b232');
            setTimeout(() => sendTokenToRender(token, retryCount + 1), 6000);
          } else {
            showNotification('⚠️ Server Render chưa sẵn sàng, hãy dán thủ công trên web', '#f23f43');
          }
          return;
        }

        try {
          const res = JSON.parse(response.responseText);
          if (res.success) {
            GM_setValue('last_synced_token', token);
            showNotification('🟢 Đã đồng bộ Token lên Render thành công! Widget đã online.', '#23a55a');
          } else {
            showNotification('🔴 Lỗi từ Render: ' + (res.error || 'Token không hợp lệ'), '#f23f43');
          }
        } catch (err) {
          showNotification('🔴 Phản hồi không hợp lệ từ Render (HTTP ' + response.status + ')', '#f23f43');
        }
      },
      ontimeout: function () {
        if (retryCount < 3) {
          showNotification('⏳ Timeout, đang thử lại kết nối Render...', '#f0b232');
          setTimeout(() => sendTokenToRender(token, retryCount + 1), 5000);
        } else {
          showNotification('⚠️ Không thể kết nối tới Render (Timeout)', '#f23f43');
        }
      },
      onerror: function (err) {
        console.error('[AutoSync] Lỗi kết nối:', err);
        showNotification('⚠️ Tampermonkey chưa được cấp quyền kết nối tới Render! Hãy bấm "Always allow" nếu có popup hỏi quyền.', '#f23f43');
      }
    });
  }

  let attempts = 0;
  const interval = setInterval(() => {
    attempts++;
    const token = extractToken();

    if (token) {
      clearInterval(interval);
      const lastToken = GM_getValue('last_synced_token', null);

      if (token !== lastToken) {
        sendTokenToRender(token);
      } else {
        console.log('[AutoSync] Token này đã được đồng bộ thành công trước đó.');
      }
    } else if (attempts >= 25) {
      clearInterval(interval);
    }
  }, 2000);
})();
