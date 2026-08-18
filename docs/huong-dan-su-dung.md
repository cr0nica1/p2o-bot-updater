# Hướng dẫn sử dụng — Kiểm tra & theo dõi phiên bản target

Tài liệu này hướng dẫn cách dùng tính năng **version checker** (lấy phiên bản mới
nhất của từng target) và **quét hàng ngày + thông báo Discord** khi có bản cập nhật.

- Lấy phiên bản **theo yêu cầu** (on-demand): CLI `version-lookup` hoặc lệnh Discord `/check-version`.
- **Tự động hàng ngày**: bot quét toàn bộ checker theo lịch, chỉ **thông báo khi có thay đổi**.

---

## 1. Yêu cầu & chuẩn bị

- **MongoDB** đang chạy.
- **Python 3.12** (môi trường này dùng `python3`, không phải `python`).
- Cài dependencies: `discord.py`, `pymongo`, `python-dotenv`, `requests`,
  `beautifulsoup4` (thêm `--break-system-packages` nếu gặp lỗi PEP 668).
- Một file **`.env`** ở thư mục gốc dự án:

```dotenv
DISCORD_TOKEN=...                 # token của bot
DISCORD_GUILD_ID=...              # ID server Discord
DISCORD_CHANNEL_ID=...            # kênh nhận thông báo cập nhật
DISCORD_ADMIN_ROLE_ID=...         # role được phép chạy lệnh admin
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=p2o
SYNC_TIME=08:00                   # giờ quét dữ liệu (gồm cả quét version)
NOTIFY_TIME=09:00                 # giờ gửi thông báo — nên đặt ≥ SYNC_TIME
TIMEZONE=Asia/Ho_Chi_Minh
```

---

## 2. Nạp dữ liệu (target + checker)

### Cách nhanh nhất — `seed`
Lệnh `seed` nạp **cả 10 target lẫn 10 version checker** với đúng tên chuẩn:

```bash
version-config seed
# → "Seeded 10 targets and 10 version checks."
```

### Hoặc import từ file mẫu qua Discord
- `/import-targets` — đính kèm `samples/targets.csv`
- `/import-vendor-firmware` — đính kèm `samples/version_checks.csv`

> Tên target trong hai file mẫu đã được chỉnh cho **khớp nhau và khớp với seed**,
> nên seed + import không tạo target trùng lặp.

---

## 3. Danh sách 10 target đã cấu hình

| # | Target | `select` | URL nguồn |
|---|--------|----------|-----------|
| 1 | Philips Hue Bridge Pro | first | https://www.philips-hue.com/en-us/support/release-notes/bridge-pro |
| 2 | Samsung Galaxy S26 | first | https://security.samsungmobile.com/securityUpdate.smsb |
| 3 | Home Assistant Green | first | https://github.com/home-assistant/operating-system/releases |
| 4 | OpenAI Codex | first | https://learn.chatgpt.com/docs/changelog?type=codex-cli |
| 5 | Anthropic Claude Code | first | https://code.claude.com/docs/en/changelog |
| 6 | Postgres pgvector | first | https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md |
| 7 | Oracle Autonomous AI Database | max | https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html |
| 8 | LiteLLM | first | https://docs.litellm.ai/release_notes/ |
| 9 | NVIDIA Dynamo | first | https://docs.nvidia.com/dynamo/reference/releases |
| 10 | Chroma | first | https://github.com/chroma-core/chroma/releases |

> `Oura Ring 5` (và các thiết bị Wellness khác) hiện **chưa có checker** — vòng quét
> hàng ngày sẽ bỏ qua, `/check-version` sẽ báo "No firmware vendor config found".

---

## 4. Kiểm tra phiên bản thủ công (on-demand)

### Dùng CLI
```bash
version-config list                 # xem các checker đã cấu hình
version-lookup --target-id 7        # lấy phiên bản 1 target theo số thứ tự
```

### Dùng Discord
- `/list-targets` — xem **số thứ tự** của từng target.
- `/check-version target_id:7` — kiểm tra ngay 1 target.
- `/scan-versions` — quét **toàn bộ** 10 checker ngay và đăng các thay đổi (chỉ admin).

---

## 5. Quét hàng ngày & thông báo tự động

Không cần bật thêm gì — tính năng gắn sẵn vào lịch `sync/notify` có sẵn:

1. Đến **`SYNC_TIME`**: bot quét cả 10 checker, lưu phiên bản vào DB.
2. Đến **`NOTIFY_TIME`**: nếu có target đổi phiên bản, bot đăng vào `DISCORD_CHANNEL_ID`:

   ```
   🔔 Version updates — 2026-08-18
   • Chroma: 1.5.9 → 1.6.0
   • LiteLLM: v1.97.0 → v1.98.0
   ```

3. Lần quét **đầu tiên** của mỗi target chỉ ghi mốc nền (baseline), **không thông báo**;
   chỉ thông báo khi phiên bản **thay đổi** ở các lần sau.
4. Nếu không có gì thay đổi → **không đăng** phần version nào (im lặng).

Quản lý lịch:
- `/set-schedule sync_time:08:00 notify_time:09:00`
- `/show-schedule`

---

## 6. Thêm / sửa / xóa checker

### Thêm hoặc ghi đè (CLI)
```bash
version-config add --vendor Chroma --target Chroma \
  --url-template https://github.com/chroma-core/chroma/releases \
  --fetch http --select first \
  --regex 'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'
```

### Thêm hoặc ghi đè (Discord)
`/set-version-check` với các tham số: `vendor`, `url_template`, `regex`,
`target`, `fetch`, `selector`, `select`.

### Xóa
```bash
version-config remove --vendor Chroma
```

> ⚠️ **`target` phải trùng đúng tên target** thì checker mới "bind" được. Việc so khớp
> dựa trên tên (đã chuẩn hoá: viết thường, gộp khoảng trắng), **không dùng alias**.
> Sai tên → `/check-version` sẽ rơi sang luồng cũ và báo lỗi "No firmware vendor
> config found".

---

## 7. Quy tắc `regex` và `select`

- **`regex`**: phải có **ít nhất 1 nhóm bắt** `( ... )`; **nhóm 1** là chuỗi phiên bản.
  URL bắt buộc **HTTPS**.
- **`fetch`**: `http` (mặc định cho trang release/changelog) hoặc `browser` (trang cần JS).
- **`select`** — chọn kết quả khi regex khớp nhiều lần:
  - `first` (mặc định) — lấy kết quả đầu tiên.
  - `last` — lấy kết quả cuối.
  - `max` — lấy phiên bản **số lớn nhất** (ví dụ Oracle dùng `max`).

---

## 8. Xử lý sự cố (Troubleshooting)

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|-----------|------------------------|-----------|
| `/check-version` báo "No firmware vendor config found" | Tên target không khớp `target` của checker (vd "Dynamo" vs "NVIDIA Dynamo"), hoặc target chưa có checker | Đổi tên target cho khớp, hoặc `/set-version-check` với `target` đúng tên |
| Target không xuất hiện trong thông báo hàng ngày | Lần quét đầu (baseline im lặng), hoặc phiên bản không đổi, hoặc target chưa có checker | Bình thường — chỉ báo khi có thay đổi thật |
| Không nhận được thông báo dù có bản mới | `NOTIFY_TIME` đặt **sớm hơn** `SYNC_TIME` | Đặt `NOTIFY_TIME ≥ SYNC_TIME` (cửa sổ báo là 24h gần nhất nên vòng kế tiếp vẫn báo) |
| `regex` không khớp | Trang nguồn đổi HTML | Cập nhật `regex` bằng `version-config add` / `/set-version-check` |
| Target bị trùng lặp | Vừa `seed` vừa import CSV với tên khác nhau | Dùng đúng một bộ tên chuẩn (file mẫu đã được canh khớp) |

---

## 9. Tóm tắt lệnh

**CLI**
| Lệnh | Chức năng |
|------|-----------|
| `version-config seed` | Nạp 10 target + 10 checker |
| `version-config list` | Liệt kê checker |
| `version-config add ...` | Thêm/ghi đè checker |
| `version-config remove --vendor X` | Xóa checker |
| `version-lookup --target-id N` | Lấy phiên bản 1 target |

**Discord**
| Lệnh | Chức năng |
|------|-----------|
| `/list-targets` | Danh sách + số thứ tự target |
| `/check-version target_id:N` | Kiểm tra 1 target |
| `/scan-versions` | Quét tất cả ngay (admin) |
| `/set-version-check ...` | Thêm/ghi đè checker (admin) |
| `/import-targets` | Import target từ CSV |
| `/import-vendor-firmware` | Import checker từ CSV |
| `/set-schedule` · `/show-schedule` | Đặt / xem lịch quét & thông báo |
