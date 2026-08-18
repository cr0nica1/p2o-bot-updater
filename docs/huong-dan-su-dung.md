# Hướng dẫn sử dụng — Kiểm tra & theo dõi phiên bản target

Tài liệu này hướng dẫn cách dùng tính năng **version checker** (lấy phiên bản mới
nhất của từng target) và **quét hàng ngày + thông báo Discord** khi có bản cập nhật.

- Lấy phiên bản **theo yêu cầu** (on-demand): CLI `version-lookup` hoặc lệnh Discord `/check-version`.
- **Tự động hàng ngày**: bot quét toàn bộ checker theo lịch, chỉ **thông báo khi có thay đổi**.
- **Khởi tạo CSDL không gây thông báo**: xem [mục 6](#6-khởi-tạo-cơ-sở-dữ-liệu-mà-không-để-bot-thông-báo) — DB version im lặng sẵn, DB lỗ hổng (CVE) cần thao tác riêng.

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

## 6. Khởi tạo cơ sở dữ liệu mà không để bot thông báo

Hệ thống có **hai** cơ sở dữ liệu và chúng hành xử **khác nhau** khi khởi tạo.

### 6.1. DB phiên bản (version) — mặc định đã im lặng ✅

- `version-config seed` **không** lấy phiên bản, chỉ nạp target + checker → không có gì đăng lên Discord.
- Lần quét **đầu tiên** của mỗi target chỉ ghi mốc nền (baseline) với `previous_version = None`; truy vấn thông báo (`list_recent_changes`) loại bỏ các bản ghi này → **không thông báo**. Chỉ các lần **đổi phiên bản về sau** mới được báo.
- Để tạo baseline hoàn toàn im lặng: cứ để vòng quét theo lịch (`_run_sync` lúc `SYNC_TIME`) chạy một lần — nó ghi baseline, còn bước `notify` sẽ không đăng gì. (Chạy `/scan-versions` cũng ghi baseline, nhưng có trả về một dòng `No version updates. scanned N…` cho đúng người gõ lệnh.)

> Kết luận: **khởi tạo DB version luôn im lặng.** Không cần làm gì thêm.

### 6.2. DB lỗ hổng (vuln / CVE) — KHÔNG im lặng ⚠️

Khác với version, mọi cách nạp CVE hiện có đều khiến bot **đăng findings**:

- **Không có CLI** để sync CVE (`[project.scripts]` chỉ có `updater-bot`, `firmware-lookup`, `vendor-config`).
- **`/sync-cves`**: chạy sync rồi trả về một embed cho **mỗi** finding. Trên DB rỗng, mọi CVE đều "tạo mới" trong lần sync đó → đăng **toàn bộ** vào kênh gõ lệnh.
- **Sync/notify theo lịch**: `_run_notify` **luôn** đăng một dòng tóm tắt + một embed mỗi finding. Nó chỉ lọc "tạo mới từ lúc sync" khi `notify` **cùng tick** với `sync`; với cấu hình khuyến nghị (`SYNC_TIME` ≠ `NOTIFY_TIME`) thì **không lọc** → đăng nguyên toàn bộ DB. Vì vậy lần `notify` đầu tiên sau khi DB có dữ liệu sẽ đăng hàng loạt lên `DISCORD_CHANNEL_ID`.

**Cách nạp DB vuln im lặng** — gọi thẳng `sync_all()`, không dựng Discord client:

```bash
cd /home/minhht21/Documents/p2o-bot-updater
python3 - <<'PY'
from updater.infrastructure.mongo import (
    MongoDatabase, MongoTargetRepository,
    MongoTargetVulnerabilityRepository, MongoVulnerabilityRepository,
)
from updater.infrastructure.sources.nvd import NvdSource
from updater.infrastructure.sources.zdi import ZdiSource
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService

db = MongoDatabase(uri="mongodb://localhost:27017", database="p2o")
sync = SyncVulnerabilitiesService(
    MongoTargetRepository(db.db),
    MongoVulnerabilityRepository(db.db),
    MongoTargetVulnerabilityRepository(db.db),
    [NvdSource(), ZdiSource()],
)
r = sync.sync_all()
print("done:", r.targets_processed, "targets,", r.vulnerabilities_seen, "CVEs")
PY
```

Script này **không gửi gì lên Discord** — DB được nạp yên lặng tại thời điểm chạy.

> ⚠️ **Bẫy:** vòng `notify` theo lịch **đầu tiên** vẫn sẽ đăng toàn bộ snapshot (nó dựng lại findings từ cả DB, không phải delta). Muốn tránh luôn cú đó, làm **một** trong hai:
> - Chạy script **trước khi** thêm bot vào kênh thật / trước khi đặt `DISCORD_CHANNEL_ID`; hoặc
> - Tạm trỏ `DISCORD_CHANNEL_ID` sang **kênh test riêng** cho chu kỳ `notify` đầu, rồi đổi lại kênh thật.

Tính năng CVE **không** có "baseline im lặng" như version — `notify` vốn được thiết kế để **báo cáo findings hàng ngày**. Muốn nó chỉ báo **CVE mới** về sau (thay vì đăng lại toàn bộ) thì cần **sửa code**, nằm ngoài phạm vi bản hướng dẫn này.

---

## 7. Thêm / sửa / xóa checker

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

## 8. Quy tắc `regex` và `select`

- **`regex`**: phải có **ít nhất 1 nhóm bắt** `( ... )`; **nhóm 1** là chuỗi phiên bản.
  URL bắt buộc **HTTPS**.
- **`fetch`**: `http` (mặc định cho trang release/changelog) hoặc `browser` (trang cần JS).
- **`select`** — chọn kết quả khi regex khớp nhiều lần:
  - `first` (mặc định) — lấy kết quả đầu tiên.
  - `last` — lấy kết quả cuối.
  - `max` — lấy phiên bản **số lớn nhất** (ví dụ Oracle dùng `max`).

---

## 9. Xử lý sự cố (Troubleshooting)

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|-----------|------------------------|-----------|
| `/check-version` báo "No firmware vendor config found" | Tên target không khớp `target` của checker (vd "Dynamo" vs "NVIDIA Dynamo"), hoặc target chưa có checker | Đổi tên target cho khớp, hoặc `/set-version-check` với `target` đúng tên |
| Target không xuất hiện trong thông báo hàng ngày | Lần quét đầu (baseline im lặng), hoặc phiên bản không đổi, hoặc target chưa có checker | Bình thường — chỉ báo khi có thay đổi thật |
| Không nhận được thông báo dù có bản mới | `NOTIFY_TIME` đặt **sớm hơn** `SYNC_TIME` | Đặt `NOTIFY_TIME ≥ SYNC_TIME` (cửa sổ báo là 24h gần nhất nên vòng kế tiếp vẫn báo) |
| `regex` không khớp | Trang nguồn đổi HTML | Cập nhật `regex` bằng `version-config add` / `/set-version-check` |
| Target bị trùng lặp | Vừa `seed` vừa import CSV với tên khác nhau | Dùng đúng một bộ tên chuẩn (file mẫu đã được canh khớp) |
| Bot đăng loạt CVE ngay lần đầu chạy | DB lỗ hổng rỗng → sync đầu coi mọi CVE là "mới"; `notify` đăng toàn bộ snapshot | Nạp DB vuln im lặng bằng script ở [mục 6.2](#62-db-lỗ-hổng-vuln--cve--không-im-lặng) và kiểm soát kênh cho chu kỳ `notify` đầu |

---

## 10. Tóm tắt lệnh

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
