"""
Order Status Tracker - TikHub
-----------------------------
Đọc mã vận đơn (cột "Tracking") trong Lark Sheet, tra trạng thái qua 17TRACK API,
rồi ghi kết quả vào cột ngay bên phải cột "KHO HÀNG".

Chạy: python tracker.py
Biến môi trường bắt buộc:
  LARK_APP_ID, LARK_APP_SECRET, LARK_SPREADSHEET_TOKEN, TRACK17_API_KEY
Biến môi trường tuỳ chọn: xem README.md
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ============================ CẤU HÌNH ============================
LARK_BASE = os.getenv("LARK_BASE_URL", "https://open.larksuite.com/open-apis")
LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")
SPREADSHEET_TOKEN = os.getenv("LARK_SPREADSHEET_TOKEN", "")
SHEET_NAME = os.getenv("LARK_SHEET_NAME", "")          # để trống = sheet đầu tiên

TRACK17_BASE = os.getenv("TRACK17_BASE_URL", "https://api.17track.net/track/v2.2")
TRACK17_KEY = os.getenv("TRACK17_API_KEY", "")

HEADER_ROW = int(os.getenv("HEADER_ROW", "1"))
TRACKING_HEADER = os.getenv("TRACKING_HEADER", "Tracking")
ANCHOR_HEADER = os.getenv("ANCHOR_HEADER", "KHO HÀNG")  # ghi vào cột ngay sau cột này
DATE_HEADER = os.getenv("DATE_HEADER", "Date")
STATUS_COLUMN = os.getenv("STATUS_COLUMN", "")          # ép cột cụ thể, vd "S" (tuỳ chọn)

# Bỏ qua đơn cũ hơn N ngày (tính theo cột Date) để tiết kiệm quota. 0 = không giới hạn
SKIP_OLDER_THAN_DAYS = int(os.getenv("SKIP_OLDER_THAN_DAYS", "30"))
# Không có cập nhật mới sau N ngày -> gắn cảnh báo "Kẹt"
STUCK_DAYS = int(os.getenv("STUCK_DAYS", "4"))
# Gợi ý mã hãng cho 17TRACK theo tiền tố mã vận đơn, vd {"GFUS": 191234}
CARRIER_HINTS = json.loads(os.getenv("CARRIER_HINTS", "{}") or "{}")

VN_TZ = timezone(timedelta(hours=7))
BATCH = 40          # 17TRACK nhận tối đa 40 mã/lần gọi
DELIVERED_MARK = "✅"

STATUS_LABELS = {
    "NotFound": "🔍 Chưa có thông tin",
    "InfoReceived": "📦 Đã tạo vận đơn",
    "InTransit": "🚚 Đang vận chuyển",
    "Expired": "⌛ Hết hạn theo dõi",
    "AvailableForPickup": "📍 Chờ nhận tại bưu cục",
    "OutForDelivery": "🛵 Đang giao",
    "DeliveryFailure": "❌ Giao thất bại",
    "Delivered": f"{DELIVERED_MARK} Đã giao",
    "Exception": "⚠️ Bất thường",
}


def log(msg):
    print(f"[{datetime.now(VN_TZ):%H:%M:%S}] {msg}", flush=True)


# ============================ TIỆN ÍCH ============================
def col_letter(idx0):
    """0 -> A, 25 -> Z, 26 -> AA"""
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def col_index(letter):
    n = 0
    for ch in letter.strip().upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def cell_text(v):
    """Lark có thể trả về số, chuỗi, hoặc list các đoạn rich-text/link."""
    if v is None:
        return ""
    if isinstance(v, list):
        parts = []
        for seg in v:
            if isinstance(seg, dict):
                parts.append(str(seg.get("text") or seg.get("link") or ""))
            else:
                parts.append(str(seg))
        return "".join(parts).strip()
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # Số > 15 chữ số đã bị làm tròn -> không tin được, đánh dấu để bỏ qua
        if abs(v) >= 1e15:
            return "#NUMBER_LOST_PRECISION"
        return str(int(v)) if v.is_integer() else str(v)
    return str(v).strip()


def clean_tracking(text):
    t = re.sub(r"[^A-Za-z0-9]", "", text or "")
    return t.upper() if 8 <= len(t) <= 50 else ""


def parse_sheet_date(text):
    text = (text or "").strip()
    for fmt in ("%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# ============================ LARK ============================
class Lark:
    def __init__(self):
        r = requests.post(
            f"{LARK_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
            timeout=30,
        ).json()
        if r.get("code") != 0:
            raise RuntimeError(f"Lark auth lỗi: {r}")
        self.h = {"Authorization": f"Bearer {r['tenant_access_token']}",
                  "Content-Type": "application/json; charset=utf-8"}

    def _check(self, r, what):
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark {what} lỗi: {data}")
        return data["data"]

    def get_sheet(self):
        d = self._check(requests.get(
            f"{LARK_BASE}/sheets/v3/spreadsheets/{SPREADSHEET_TOKEN}/sheets/query",
            headers=self.h, timeout=30), "đọc danh sách sheet")
        sheets = d.get("sheets", [])
        if not sheets:
            raise RuntimeError("Spreadsheet không có sheet nào")
        if SHEET_NAME:
            for s in sheets:
                if s.get("title") == SHEET_NAME:
                    return s
            raise RuntimeError(f"Không tìm thấy sheet tên '{SHEET_NAME}'")
        return sheets[0]

    def read(self, rng):
        d = self._check(requests.get(
            f"{LARK_BASE}/sheets/v2/spreadsheets/{SPREADSHEET_TOKEN}/values/{rng}",
            params={"valueRenderOption": "ToString",
                    "dateTimeRenderOption": "FormattedString"},
            headers=self.h, timeout=60), f"đọc {rng}")
        return d.get("valueRange", {}).get("values") or []

    def write_many(self, ranges):
        """ranges: list of (range_str, [[value]])"""
        for i in range(0, len(ranges), 100):
            chunk = ranges[i:i + 100]
            body = {"valueRanges": [{"range": r, "values": v} for r, v in chunk]}
            self._check(requests.post(
                f"{LARK_BASE}/sheets/v2/spreadsheets/{SPREADSHEET_TOKEN}/values_batch_update",
                headers=self.h, json=body, timeout=60), "ghi dữ liệu")
            time.sleep(0.5)


# ============================ 17TRACK ============================
class Track17:
    def __init__(self):
        self.h = {"17token": TRACK17_KEY, "Content-Type": "application/json"}

    def _post(self, path, payload):
        for attempt in range(3):
            r = requests.post(f"{TRACK17_BASE}/{path}", headers=self.h,
                              json=payload, timeout=60)
            if r.status_code == 429:
                time.sleep(2 + attempt * 2)
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("code") != 0:
                raise RuntimeError(f"17TRACK {path} lỗi: {d}")
            time.sleep(0.4)  # giới hạn ~3 request/giây
            return d.get("data", {})
        raise RuntimeError(f"17TRACK {path}: quá nhiều request (429)")

    @staticmethod
    def _item(num):
        item = {"number": num}
        for prefix, code in CARRIER_HINTS.items():
            if num.startswith(prefix.upper()):
                item["carrier"] = int(code)
                break
        return item

    def register(self, numbers):
        """Mã đã đăng ký trước đó sẽ bị 'rejected' -> không tốn quota."""
        new = 0
        for i in range(0, len(numbers), BATCH):
            d = self._post("register", [self._item(n) for n in numbers[i:i + BATCH]])
            new += len(d.get("accepted", []))
        return new

    def get_info(self, numbers):
        out = {}
        for i in range(0, len(numbers), BATCH):
            d = self._post("gettrackinfo", [self._item(n) for n in numbers[i:i + BATCH]])
            for acc in d.get("accepted", []):
                out[str(acc.get("number", "")).upper()] = acc.get("track_info") or {}
        return out


# ============================ FORMAT ============================
def format_status(track_info, now_utc):
    if not track_info:
        return "⏳ Đang lấy dữ liệu – lần chạy sau sẽ có"

    latest_status = track_info.get("latest_status") or {}
    status = latest_status.get("status") or "NotFound"
    sub = str(latest_status.get("sub_status") or "")
    label = STATUS_LABELS.get(status, status)
    if "return" in sub.lower():
        label = "↩️ Đang hoàn hàng"

    ev = track_info.get("latest_event") or {}
    desc = (ev.get("description") or "").strip()
    loc = (ev.get("location") or "").strip()
    ev_time = parse_iso(ev.get("time_iso") or ev.get("time_utc"))

    parts = [label]
    if ev_time:
        parts.append(ev_time.strftime("%d/%m %H:%M"))
    if desc:
        text = desc if not loc or loc.lower() in desc.lower() else f"{desc}, {loc}"
        parts.append(text[:120])
    result = " | ".join(parts)

    if status != "Delivered" and ev_time:
        age = (now_utc - ev_time.astimezone(timezone.utc)).days
        if age >= STUCK_DAYS:
            result = f"🚨 Kẹt {age} ngày – " + result
    return result


# ============================ MAIN ============================
def main():
    missing = [k for k, v in {
        "LARK_APP_ID": LARK_APP_ID, "LARK_APP_SECRET": LARK_APP_SECRET,
        "LARK_SPREADSHEET_TOKEN": SPREADSHEET_TOKEN, "TRACK17_API_KEY": TRACK17_KEY,
    }.items() if not v]
    if missing:
        sys.exit(f"Thiếu biến môi trường: {', '.join(missing)}")

    lark = Lark()
    sheet = lark.get_sheet()
    sid = sheet["sheet_id"]
    grid = sheet.get("grid_properties", {})
    n_rows = int(grid.get("row_count", 5000))
    n_cols = min(int(grid.get("column_count", 26)), 100)
    log(f"Sheet '{sheet.get('title')}' – {n_rows} dòng, {n_cols} cột")

    # 1) Tìm cột theo tiêu đề
    header = lark.read(f"{sid}!A{HEADER_ROW}:{col_letter(n_cols - 1)}{HEADER_ROW}")
    header = [norm(cell_text(c)) for c in (header[0] if header else [])]

    def find(name, required=True):
        key = norm(name)
        for i, h in enumerate(header):
            if h == key:
                return i
        for i, h in enumerate(header):
            if h.startswith(key):
                return i
        if required:
            raise RuntimeError(f"Không tìm thấy cột tiêu đề '{name}' ở dòng {HEADER_ROW}")
        return None

    trk_col = find(TRACKING_HEADER)
    date_col = find(DATE_HEADER, required=False)
    st_col = col_index(STATUS_COLUMN) if STATUS_COLUMN else find(ANCHOR_HEADER) + 1
    log(f"Tracking = cột {col_letter(trk_col)}, ghi trạng thái vào cột {col_letter(st_col)}")

    # 2) Đọc dữ liệu
    first = HEADER_ROW + 1
    def read_col(c):
        vals = lark.read(f"{sid}!{col_letter(c)}{first}:{col_letter(c)}{n_rows}")
        return [cell_text(r[0]) if r else "" for r in vals]

    trackings = read_col(trk_col)
    statuses = read_col(st_col)
    dates = read_col(date_col) if date_col is not None else []

    today = datetime.now(VN_TZ).date()
    todo = {}  # tracking -> [row numbers]
    skipped_old = 0
    bad_rows = []
    for i, raw in enumerate(trackings):
        if raw == "#NUMBER_LOST_PRECISION":
            bad_rows.append(first + i)
            continue
        num = clean_tracking(raw)
        if not num:
            continue
        current = statuses[i] if i < len(statuses) else ""
        if current.startswith(DELIVERED_MARK):
            continue  # đã giao -> không cần tra nữa
        if SKIP_OLDER_THAN_DAYS and i < len(dates):
            d = parse_sheet_date(dates[i])
            if d and (today - d).days > SKIP_OLDER_THAN_DAYS:
                skipped_old += 1
                continue
        todo.setdefault(num, []).append(first + i)

    log(f"Cần kiểm tra {len(todo)} mã vận đơn (bỏ qua {skipped_old} đơn quá {SKIP_OLDER_THAN_DAYS} ngày)")
    if bad_rows:
        log(f"⚠️ {len(bad_rows)} ô Tracking đang ở dạng SỐ nên bị làm tròn, không tra được "
            f"(dòng {', '.join(map(str, bad_rows[:10]))}{'...' if len(bad_rows) > 10 else ''}). "
            f"Hãy định dạng cột Tracking thành Văn bản (Text) và dán lại mã.")

    now_vn = datetime.now(VN_TZ)
    header_cell = (f"{sid}!{col_letter(st_col)}{HEADER_ROW}:{col_letter(st_col)}{HEADER_ROW}",
                   [[f"TRẠNG THÁI ĐƠN (cập nhật {now_vn:%d/%m %H:%M})"]])

    if not todo:
        lark.write_many([header_cell])
        log("Không có đơn nào cần cập nhật. Xong.")
        return

    # 3) Đăng ký + tra 17TRACK
    t17 = Track17()
    numbers = list(todo)
    new = t17.register(numbers)
    log(f"Đăng ký mới {new} mã (tốn {new} quota)")
    if new:
        time.sleep(60)  # đợi 17TRACK lấy dữ liệu lần đầu
    info = t17.get_info(numbers)

    # 4) Ghi về sheet
    now_utc = datetime.now(timezone.utc)
    writes, summary = [header_cell], {}
    for num, rows in todo.items():
        text = format_status(info.get(num), now_utc)
        summary[text.split(" | ")[0]] = summary.get(text.split(" | ")[0], 0) + len(rows)
        for r in rows:
            cell = f"{col_letter(st_col)}{r}"
            writes.append((f"{sid}!{cell}:{cell}", [[text]]))

    lark.write_many(writes)
    log(f"Đã cập nhật {len(writes) - 1} ô.")
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
        log(f"   {k}: {v}")


if __name__ == "__main__":
    main()
