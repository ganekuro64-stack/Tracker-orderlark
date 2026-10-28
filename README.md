# Order Status Tracker – Hướng dẫn cài đặt

Mỗi sáng lúc **7h (giờ VN)**, hệ thống tự động:
1. Đọc cột **Tracking** trong Lark Sheet tổng
2. Tra trạng thái vận đơn qua **17TRACK** (tự nhận diện USPS, GOFO, SpeedX...)
3. Ghi kết quả vào **cột trống ngay bên phải cột "KHO HÀNG"**

Ví dụ nội dung ô sau khi cập nhật:

```
✅ Đã giao | 27/10 14:05 | Delivered, Front Door/Porch, TAMPA FL
🚚 Đang vận chuyển | 26/10 22:10 | Departed USPS Regional Facility, DALLAS TX
🚨 Kẹt 5 ngày – 📦 Đã tạo vận đơn | 23/10 09:00 | Shipping label created
```

Đơn đã **✅ Đã giao** sẽ không tra lại nữa. Đơn cũ hơn 30 ngày (theo cột Date) được bỏ qua để tiết kiệm quota.

Tổng thời gian cài đặt: khoảng **30–40 phút**, chỉ làm 1 lần.

---

## Bước 1 – Lấy API key 17TRACK (5 phút)

1. Đăng ký tài khoản tại **https://api.17track.net** (trang dành cho API, khác app tra cứu thường).
2. Vào **Settings → Security → Access Key**, copy key → đây là `TRACK17_API_KEY`.
3. Nếu trong Settings có mục **IP whitelist**, để trống (cho phép mọi IP), vì GitHub chạy từ IP thay đổi.

**Chi phí:** tài khoản mới có **100 quota miễn phí** để chạy thử. Mỗi mã vận đơn tốn **1 quota duy nhất** khi đăng ký lần đầu; các lần tra lại hằng ngày sau đó **miễn phí**.
Với 10–30 đơn/ngày (~300–900 mã/tháng) cần mua gói trả trước, dùng trong 12 tháng (tham khảo: khoảng $49 cho 1.000 mã). Kiểm tra giá hiện tại trên trang 17TRACK trước khi mua.

---

## Bước 2 – Tạo Lark Custom App (10–15 phút)

1. Vào **https://open.larksuite.com/app** → **Create Custom App**. Đặt tên, ví dụ `Order Tracker`.
2. Tab **Credentials & Basic Info**: copy **App ID** và **App Secret**.
3. Tab **Features / Add features**: bật **Bot** (cần để thêm app vào tài liệu).
4. Tab **Permissions & Scopes**: tìm và thêm quyền
   - `sheets:spreadsheet` (View, comment, edit, and manage Sheets)
5. Tab **Version Management & Release**: tạo version → **Publish**. Nếu công ty bật duyệt app, nhờ admin Lark duyệt.

### Cấp quyền app vào sheet tổng
6. Mở sheet tổng → nút **"…"** góc phải trên → **More → Add Apps** (hoặc "Thêm ứng dụng tài liệu") → tìm `Order Tracker` → cấp quyền **Edit** (có thể chỉnh sửa).
   - Nếu không thấy app: kiểm tra đã bật Bot và đã Publish ở bước 3 và 5.

### Lấy Spreadsheet Token
7. Nhìn URL của sheet:
   `https://xxx.larksuite.com/sheets/`**`ShtcnAbC123XyZ`**`?sheet=...`
   Đoạn in đậm (sau `/sheets/`, trước `?`) là `LARK_SPREADSHEET_TOKEN`.
   - Nếu URL có dạng `/wiki/...` (sheet nằm trong Wiki), báo lại để chỉnh code, vì token Wiki khác token Sheet.

---

## Bước 3 – Đưa code lên GitHub (10 phút)

1. Tạo tài khoản GitHub (nếu chưa có) → **New repository** → tên `order-tracker` → chọn **Private** → Create.
2. Trong repo, bấm **Add file → Upload files**, kéo thả 3 file: `tracker.py`, `requirements.txt`, `README.md` → Commit.
3. Tạo file lịch chạy: **Add file → Create new file**
   - Ô tên file gõ chính xác: `.github/workflows/order-status.yml`
   - Dán nội dung file `order-status.yml` trong gói này → Commit.

### Nhập các khoá bí mật
4. Repo → **Settings → Secrets and variables → Actions → tab Secrets → New repository secret**, tạo 4 secret:

| Tên | Giá trị |
|---|---|
| `LARK_APP_ID` | App ID ở Bước 2 |
| `LARK_APP_SECRET` | App Secret ở Bước 2 |
| `LARK_SPREADSHEET_TOKEN` | Token ở Bước 2.7 |
| `TRACK17_API_KEY` | Key ở Bước 1 |

---

## Bước 4 – Chạy thử

1. Repo → tab **Actions** → chọn **Cập nhật trạng thái đơn** → **Run workflow**.
2. Đợi 1–3 phút, bấm vào lần chạy để xem log, ví dụ:
   ```
   Sheet 'Tổng đơn' – 1000 dòng, 26 cột
   Tracking = cột Q, ghi trạng thái vào cột S
   Cần kiểm tra 85 mã vận đơn (bỏ qua 150 đơn quá 30 ngày)
   Đăng ký mới 85 mã (tốn 85 quota)
   Đã cập nhật 87 ô.
   ```
3. Mở Lark Sheet kiểm tra cột cạnh KHO HÀNG.
   - Lần chạy đầu, một số đơn có thể hiện **"⏳ Đang lấy dữ liệu"**: 17TRACK cần thời gian lấy dữ liệu lần đầu, sáng hôm sau sẽ đầy đủ.

> ⚠️ Lần chạy đầu tiên sẽ đăng ký toàn bộ đơn trong 30 ngày gần nhất. Nếu số đơn này > 100 mà chưa mua quota, hãy tạm đặt biến `SKIP_OLDER_THAN_DAYS` = `5` để chạy thử trước (xem phần Tuỳ chỉnh).

Từ đó trở đi hệ thống **tự chạy lúc 7h sáng mỗi ngày**. GitHub đôi khi chạy trễ 5–20 phút so với giờ đặt, đây là bình thường.

---

## Tuỳ chỉnh (không bắt buộc)

Repo → **Settings → Secrets and variables → Actions → tab Variables → New repository variable**:

| Tên biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LARK_SHEET_NAME` | sheet đầu tiên | Tên tab cần đọc, nếu sheet tổng không phải tab đầu |
| `SKIP_OLDER_THAN_DAYS` | `30` | Bỏ qua đơn cũ hơn N ngày (0 = không giới hạn) |
| `STUCK_DAYS` | `4` | Bao nhiêu ngày không có cập nhật thì gắn 🚨 Kẹt |
| `CARRIER_HINTS` | `{}` | Chỉ định hãng theo tiền tố mã, xem dưới |

**CARRIER_HINTS:** nếu mã `GFUS...` cứ hiện "🔍 Chưa có thông tin" dù đã qua vài ngày, có thể 17TRACK nhận diện sai hãng. Tra mã hãng GOFO trong danh sách hãng của 17TRACK rồi đặt biến, ví dụ:
```
{"GFUS": 123456}
```

**Đổi giờ chạy:** sửa dòng `cron` trong `order-status.yml` (giờ UTC = giờ VN − 7). Ví dụ chạy 7h và 15h: `"0 0,8 * * *"`.

---

## Ý nghĩa các trạng thái

| Hiển thị | Nghĩa |
|---|---|
| 📦 Đã tạo vận đơn | Có label, hãng chưa nhận hàng |
| 🚚 Đang vận chuyển | Đang trên đường |
| 🛵 Đang giao | Shipper đang đi giao |
| 📍 Chờ nhận tại bưu cục | Khách cần ra bưu cục lấy |
| ✅ Đã giao | Hoàn tất – không tra lại nữa |
| ❌ Giao thất bại | Giao không thành công |
| ⚠️ Bất thường | Có sự cố (sai địa chỉ, hư hỏng...) |
| ↩️ Đang hoàn hàng | Hàng đang trả về người gửi |
| 🔍 Chưa có thông tin | Hãng chưa có dữ liệu |
| ⏳ Đang lấy dữ liệu | Mã mới đăng ký, chờ lần chạy sau |
| 🚨 Kẹt N ngày – ... | Không có cập nhật mới ≥ N ngày, cần kiểm tra |

---

## Lỗi thường gặp

| Log báo | Cách xử lý |
|---|---|
| `Lark auth lỗi` | Sai App ID/Secret, hoặc app chưa Publish |
| `Lark đọc danh sách sheet lỗi ... 91403` (hoặc forbidden) | App chưa được thêm vào sheet (Bước 2.6) hoặc thiếu quyền `sheets:spreadsheet` |
| `Không tìm thấy cột tiêu đề 'Tracking'` | Tiêu đề cột ở dòng 1 bị đổi tên; sửa lại cho đúng |
| `ô Tracking đang ở dạng SỐ nên bị làm tròn` | Mã USPS dài 22 số bị Lark lưu thành số. Định dạng cột Tracking thành **Văn bản (Text)** rồi dán lại mã ở các dòng được báo |
| `17TRACK ... 401` | Sai API key, hoặc đang bật IP whitelist |
| `17TRACK register lỗi ... quota` | Hết quota, cần mua thêm |
