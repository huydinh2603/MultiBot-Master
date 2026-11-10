# 🌟 MultiBot Master — 24/7 Multi-Bot Orchestrator

[![Render Status](https://img.shields.io/badge/Deploy%20to-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![Runtime](https://img.shields.io/badge/Runtime-Node.js%2020%20%2B%20Python%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Process Manager](https://img.shields.io/badge/PM2-Cluster%20Orchestrator-2B037A?style=for-the-badge&logo=pm2&logoColor=white)](https://pm2.keymetrics.io)
[![RAM Limit](https://img.shields.io/badge/RAM%20Budget-~220MB%20%2F%20512MB-success?style=for-the-badge)](https://render.com)

Chạy đồng thời **5 Discord Bots** trong **1 duy nhất Web Service container** trên Render.com Free Tier 24/7 mà **không vượt quá giới hạn 512MB RAM** và **không tiêu tốn quá 744 giờ/tháng** (hạn mức miễn phí của Render là 750 giờ/tháng).

---

## 🤖 Danh Sách 5 Bots Trong Cụm

| Bot | Ngôn Ngữ / Thư Viện | Chức Năng Chính | RAM Ước Tính |
| :--- | :--- | :--- | :--- |
| **AutoRes** | Python 3.12 (`discord.py`) | Trả lời tự động thông minh & quản lý lệnh tùy chỉnh | ~38 MB |
| **VoiceGuard** | Python 3.12 (`discord.py[voice]`) | Treo phòng voice 24/7, tự kết nối lại khi rớt mạng | ~35 MB |
| **Moderator** | Python 3.12 (`discord.py`) | Hệ thống Quản trị Server, AutoMod, Ticket, Cổng xác minh | ~45 MB |
| **Sheriff** | Node.js 20 (`discord.js v14`) | Mini-game bắn súng câm lặng (Mute) & Kinh tế T-Coin | ~40 MB |
| **Widget** | Node.js 20 (`discord.js-selfbot`) | Rich Presence hiển thị trạng thái/bài hát 24/7 & Web UI | ~40 MB |
| **Hub Gateway** | Node.js 20 (`PM2 + Gateway`) | Giữ kết nối (Keep-Alive), Dashboard telemetry & Reverse proxy | ~22 MB |
| **TỔNG CỘNG** | **Dual Runtime Container** | **Chạy mượt mà, ổn định 24/7** | **~220 MB / 512 MB** |

> 💡 **Headroom An Toàn:** Cụm bot chỉ sử dụng khoảng **220 MB RAM**, để lại hơn **290 MB RAM dự phòng** (>55%) giúp tránh hoàn toàn lỗi Out-Of-Memory (Exit code 137 / 134) của Render.

---

## ⚡ Kiến Trúc Độc Lập & Tối Ưu Hóa Bộ Nhớ

1. **Bộ Quản Lý Tiến Trình PM2 (`pm2-runtime`):**
   - Tự động giám sát, gom rác định kỳ và tự khởi động lại (auto-heal) từng bot riêng biệt nếu gặp sự cố mà không làm ảnh hưởng các bot khác.
2. **Cắt Giảm Heap Node.js V8:**
   - Cấu hình cờ `--max-old-space-size=64 --expose-gc` cho Sheriff và Widget. Bộ thu gom rác chủ động chạy định kỳ mỗi 10 phút.
3. **Thu Hồi Heap Python (`glibc malloc_trim`):**
   - Thiết lập biến môi trường `MALLOC_TRIM_THRESHOLD_=100000` giúp Python ngay lập tức trả các trang bộ nhớ đã giải phóng về lại cho hệ điều hành.
   - Thiết lập `max_messages=50` và `chunk_guilds_at_startup=False` trên `discord.py` để không lưu trữ cache tin nhắn dư thừa.
4. **Cổng Tập Trung (Centralized Hub Port):**
   - Duy nhất một Web Gateway lắng nghe trên biến môi trường `$PORT` do Render cấp.
   - Endpoint `/health` phản hồi UptimeRobot / Cron-job trong < 2ms.
   - Proxy thông minh `/api/*` và `/widget` trực tiếp tới Widget UI mà không bị xung đột cổng `EADDRINUSE`.

---

## 🚀 Hướng Dẫn Triển Khai Lên Render.com (5 Phút)

### Bước 1: Chuẩn Bị Token Các Bot
Đảm bảo bạn đã tạo Application và lấy Token trên [Discord Developer Portal](https://discord.com/developers/applications):
- Bật mục **Privileged Gateway Intents** (Message Content Intent, Server Members Intent) cho các bot nếu có yêu cầu.

### Bước 2: Tạo Dịch Vụ Mới Trên Render
1. Đăng nhập vào [Render Dashboard](https://dashboard.render.com).
2. Nhấn nút **New +** > chọn **Web Service**.
3. Chọn kho GitHub: `huydinh2603/MultiBot-Master` (hoặc repo của bạn).
4. Thiết lập các thông số:
   - **Name:** `multibot-master` (hoặc tên tùy thích).
   - **Region:** `Singapore` hoặc `Frankfurt` (khuyến nghị Singapore để giảm độ trễ về Việt Nam).
   - **Language / Runtime:** Chọn **Docker**.
   - **Instance Type:** Chọn **Free (512 MB RAM, 0.1 CPU)**.

### Bước 3: Cấu Hình Biến Môi Trường (Environment Variables)
Chuyển sang tab **Environment** trên Render và thêm các biến sau:

| Tên Biến | Giá Trị Mẫu / Mô Tả |
| :--- | :--- |
| `TOKEN_AUTORES` | Token của Bot AutoRes |
| `TOKEN_VOICEGUARD` | Token của Bot VoiceGuard |
| `VOICEGUARD_CHANNEL_ID` | *(Tùy chọn)* ID kênh voice muốn bot vào treo 24/7 |
| `TOKEN_MODERATOR` | Token của Bot Moderator |
| `TOKEN_SHERIFF` | Token của Bot Sheriff |
| `USER_TOKEN` | Token tài khoản cá nhân Discord (User Token) cho Widget |
| `SYNC_KEY` | `LamiaSync2026` (Khóa bảo mật đồng bộ Widget) |

> 📌 *Lưu ý: Nếu bạn chưa muốn bật bot nào, chỉ cần để trống hoặc không điền token của bot đó. Cụm điều phối sẽ tự động phát hiện và bỏ qua bot chưa có token.*

### Bước 4: Nhấn Create Web Service & Hoàn Tất!
Render sẽ tự động build image Docker và khởi chạy cả 5 bot trong vòng 2-3 phút!

---

## 🌐 Giữ Bot Luôn Online 24/7 (Chống Sleep Sau 15 Phút)

Render Free Web Service sẽ ngủ sau 15 phút nếu không có lượt truy cập HTTP. Để giữ bot chạy liên tục 24/7/365:

1. Đăng ký tài khoản miễn phí tại [Cron-Job.org](https://cron-job.org) hoặc [UptimeRobot.com](https://uptimerobot.com).
2. Tạo một Monitor mới:
   - **URL:** `https://<tên-app-của-bạn>.onrender.com/health`
   - **Interval:** Mỗi `5 phút` (hoặc `10 phút`).
   - **Method:** `GET` hoặc `HEAD`.

Như vậy, bot của bạn sẽ hoạt động hoàn toàn miễn phí, không bao giờ bị tắt máy!

---

## 🛠️ Giám Sát Trạng Thái Trực Quan

Sau khi triển khai thành công, bạn có thể truy cập thẳng vào domain Render:
- `https://<tên-app-của-bạn>.onrender.com/`: Giao diện Dashboard đẹp mắt hiển thị trạng thái cả 5 bot và dung lượng RAM.
- `https://<tên-app-của-bạn>.onrender.com/status`: Trả về JSON trạng thái chi tiết của từng bot và hệ thống.
- `https://<tên-app-của-bạn>.onrender.com/widget`: Giao diện điều khiển Rich Presence của Widget bot.
- `https://<tên-app-của-bạn>.onrender.com/health`: Endpoint kiểm tra sống/chết (Healthcheck).
