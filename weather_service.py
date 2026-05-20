"""
weather_service.py
──────────────────
Lấy thông tin thời tiết qua OpenWeatherMap API (miễn phí, 1000 calls/ngày).

Hàm chính:
  get_weather(serpapi_key, location, lang="vi") -> dict

Giữ nguyên signature cũ để không cần sửa main.py.
Đọc OPENWEATHER_KEY từ biến môi trường.

Response dict:
{
  "success":       bool,
  "location":      str,
  "current": {
    "temp_c":        float | None,
    "feels_like_c":  float | None,
    "condition":     str,
    "icon":          str,          # emoji
    "humidity":      int | None,   # %
    "wind_kph":      int | None,
    "uv_index":      int | None,
    "visibility_km": int | None,
  },
  "forecast": [                    # tối đa 7 ngày
    {
      "day":         str,          # "Thứ Hai"
      "date":        str,          # "02/06"
      "high_c":      float | None,
      "low_c":       float | None,
      "condition":   str,
      "icon":        str,
      "rain_chance": int | None,   # %
    },
    ...
  ],
  "travel_advice": str,
  "unit":          "celsius",
  "source":        str,
}
"""

from __future__ import annotations
import os
import time
import requests
from datetime import datetime, timezone

# ────────────────────────────────────────────────────────────────────────────
# 0. IN-MEMORY CACHE — tránh gọi OpenWeatherMap lặp lại (TTL 30 phút)
# ────────────────────────────────────────────────────────────────────────────
_WEATHER_CACHE: dict[str, dict] = {}
_CACHE_TTL = 30 * 60  # 30 phút (giây)

def _cache_get(key: str) -> dict | None:
    entry = _WEATHER_CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        print(f"[weather_service] Cache HIT: {key}")
        return entry["data"]
    return None

def _cache_set(key: str, data: dict) -> None:
    _WEATHER_CACHE[key] = {"ts": time.time(), "data": data}

# ────────────────────────────────────────────────────────────────────────────
# 1. ICON MAP
# ────────────────────────────────────────────────────────────────────────────

_WEATHER_ICON_MAP: list[tuple[list[str], str]] = [
    (["nắng", "sunny", "clear"],                  "☀️"),
    (["mây", "cloud", "overcast", "partly"],       "⛅"),
    (["mưa", "rain", "shower", "drizzle"],         "🌧️"),
    (["dông", "storm", "thunder", "lightning"],    "⛈️"),
    (["tuyết", "snow", "sleet", "hail"],           "❄️"),
    (["sương", "fog", "mist", "haze"],             "🌫️"),
    (["gió", "wind", "breezy"],                    "💨"),
]

def _condition_icon(condition: str) -> str:
    low = condition.lower()
    for keywords, icon in _WEATHER_ICON_MAP:
        if any(k in low for k in keywords):
            return icon
    return "🌡️"


# ────────────────────────────────────────────────────────────────────────────
# 2. MAP OWM WEATHER ID → TIẾNG VIỆT
# ────────────────────────────────────────────────────────────────────────────

def _owm_condition_vi(weather_id: int, description: str) -> str:
    """Chuyển OpenWeatherMap weather id → mô tả tiếng Việt."""
    if 200 <= weather_id < 300:
        return "Dông bão"
    if 300 <= weather_id < 400:
        return "Mưa phùn"
    if 500 <= weather_id < 600:
        if weather_id == 500:
            return "Mưa nhẹ"
        if weather_id == 501:
            return "Mưa vừa"
        if weather_id >= 502:
            return "Mưa to"
        return "Mưa"
    if 600 <= weather_id < 700:
        return "Tuyết"
    if 700 <= weather_id < 800:
        d = description.lower()
        if "fog" in d or "mist" in d:
            return "Sương mù"
        if "haze" in d:
            return "Sương khói"
        return "Tầm nhìn kém"
    if weather_id == 800:
        return "Trời nắng"
    if weather_id == 801:
        return "Ít mây"
    if weather_id == 802:
        return "Mây rải rác"
    if weather_id >= 803:
        return "Nhiều mây"
    return description.capitalize()


# ────────────────────────────────────────────────────────────────────────────
# 3. GỢI Ý DU LỊCH
# ────────────────────────────────────────────────────────────────────────────

def _travel_advice(condition: str, temp_c: float | None) -> str:
    low = condition.lower()
    if any(k in low for k in ["dông", "storm", "thunder"]):
        return "⚠️ Có dông — tránh hoạt động ngoài trời, ở trong nhà an toàn hơn."
    if any(k in low for k in ["mưa", "rain", "shower", "drizzle", "phùn"]):
        return "☂️ Trời mưa — mang theo áo mưa, ưu tiên điểm tham quan trong nhà."
    if temp_c is not None and temp_c >= 36:
        return "🥵 Rất nóng — uống nhiều nước, tránh ra ngoài 11h–15h, mang kem chống nắng."
    if temp_c is not None and temp_c >= 32:
        return "☀️ Nắng nóng — nên đi sáng sớm hoặc chiều tối, đội mũ và mang nước."
    if temp_c is not None and temp_c <= 15:
        return "🧥 Trời mát lạnh — mang thêm áo khoác nhẹ khi ra ngoài."
    if any(k in low for k in ["nắng", "sunny", "clear"]):
        return "✅ Thời tiết lý tưởng — phù hợp mọi hoạt động ngoài trời!"
    return "🙂 Thời tiết ổn — phù hợp để tham quan và khám phá."


# ────────────────────────────────────────────────────────────────────────────
# 4. NGÀY TRONG TUẦN TIẾNG VIỆT
# ────────────────────────────────────────────────────────────────────────────

_DAY_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

def _day_vi(dt: datetime) -> str:
    return _DAY_VI[dt.weekday()]


# ────────────────────────────────────────────────────────────────────────────
# 5. HÀM CHÍNH: GET_WEATHER
# ────────────────────────────────────────────────────────────────────────────

def get_weather(serpapi_key: str, location: str, lang: str = "vi") -> dict:
    """
    Lấy thời tiết hiện tại + dự báo 7 ngày qua OpenWeatherMap.
    Giữ nguyên signature cũ (serpapi_key được bỏ qua).
    Đọc OPENWEATHER_KEY từ biến môi trường.
    Cache 30 phút — tránh gọi API lặp lại.
    """
    api_key = os.getenv("OPENWEATHER_KEY", "").strip()
    if not api_key:
        return {
            "success": False,
            "error": "Chưa cấu hình OPENWEATHER_KEY trong .env",
            "error_code": "NO_API_KEY",
        }

    if not location or not location.strip():
        return {"success": False, "error": "Thiếu tham số location", "error_code": "NO_LOCATION"}

    loc       = location.strip()
    loc_lower = loc.lower()

    _ALIAS: dict[str, str] = {
        # Miền Nam
        "bà rịa - vũng tàu": "Vung Tau",
        "bà rịa":             "Vung Tau",
        "vũng tàu":           "Vung Tau",
        "bình dương":         "Thu Dau Mot",
        "đồng nai":           "Bien Hoa",
        "tây ninh":           "Tay Ninh",
        "long an":            "Tan An",
        "tiền giang":         "My Tho",
        "bến tre":            "Ben Tre",
        "vĩnh long":          "Vinh Long",
        "trà vinh":           "Tra Vinh",
        "sóc trăng":          "Soc Trang",
        "bạc liêu":           "Bac Lieu",
        "cà mau":             "Ca Mau",
        "hậu giang":          "Vi Thanh",
        "an giang":           "Long Xuyen",
        "đồng tháp":          "Cao Lanh",
        "kiên giang":         "Phu Quoc",
        "tp. hồ chí minh":    "Ho Chi Minh City",
        "hồ chí minh":        "Ho Chi Minh City",
        "sài gòn":            "Ho Chi Minh City",
        # Miền Trung
        "thừa thiên huế":     "Hue",
        "thừa thiên - huế":   "Hue",
        "tth":                "Hue",
        "quảng nam":          "Hoi An",
        "hội an":             "Hoi An",
        "quảng ngãi":         "Quang Ngai",
        "quảng bình":         "Dong Hoi",
        "quảng trị":          "Dong Ha",
        "hà tĩnh":            "Ha Tinh",
        "nghệ an":            "Vinh",
        "thanh hóa":          "Thanh Hoa",
        "ninh thuận":         "Phan Rang",
        "bình thuận":         "Phan Thiet",
        "khánh hòa":          "Nha Trang",
        "khánh hoà":          "Nha Trang",
        "phú yên":            "Tuy Hoa",
        "bình định":          "Quy Nhon",
        "gia lai":            "Pleiku",
        "đắk lắk":            "Buon Ma Thuot",
        "đắk nông":           "Gia Nghia",
        "kon tum":            "Kon Tum",
        "lâm đồng":           "Da Lat",
        # Miền Bắc
        "hà nội":             "Hanoi",
        "hải phòng":          "Hai Phong",
        "quảng ninh":         "Ha Long",
        "hạ long":            "Ha Long",
        "bắc ninh":           "Bac Ninh",
        "bắc giang":          "Bac Giang",
        "hưng yên":           "Hung Yen",
        "hải dương":          "Hai Duong",
        "thái bình":          "Thai Binh",
        "nam định":           "Nam Dinh",
        "ninh bình":          "Ninh Binh",
        "hà nam":             "Phu Ly",
        "vĩnh phúc":          "Vinh Yen",
        "phú thọ":            "Viet Tri",
        "thái nguyên":        "Thai Nguyen",
        "tuyên quang":        "Tuyen Quang",
        "lào cai":            "Lao Cai",
        "sapa":               "Sa Pa",
        "yên bái":            "Yen Bai",
        "sơn la":             "Son La",
        "điện biên":          "Dien Bien Phu",
        "lai châu":           "Lai Chau",
        "hà giang":           "Ha Giang",
        "cao bằng":           "Cao Bang",
        "lạng sơn":           "Lang Son",
        "bắc kạn":            "Bac Kan",
    }

    loc = _ALIAS.get(loc_lower, loc)
    cache_key = f"{loc.lower()}:{lang}"

    # Trả cache nếu còn hạn
    cached = _cache_get(cache_key)
    if cached:
        return cached
    BASE = "https://api.openweathermap.org/data/2.5"

    try:
        # ── 1. THỜI TIẾT HIỆN TẠI ─────────────────────────────────────────
        cur_resp = requests.get(
            f"{BASE}/weather",
            params={"q": f"{loc},VN", "appid": api_key, "units": "metric", "lang": "vi"},
            timeout=8,
        )
        if cur_resp.status_code != 200:
            # Thử không kèm ,VN nếu location là tên tiếng Việt có dấu
            cur_resp = requests.get(
                f"{BASE}/weather",
                params={"q": loc, "appid": api_key, "units": "metric", "lang": "vi"},
                timeout=8,
            )
        if cur_resp.status_code != 200:
            err = cur_resp.json().get("message", "Không tìm thấy địa điểm")
            return {"success": False, "error": err}

        cur = cur_resp.json()
        lat = cur["coord"]["lat"]
        lon = cur["coord"]["lon"]

        weather_id  = cur["weather"][0]["id"]
        description = cur["weather"][0].get("description", "")
        condition   = _owm_condition_vi(weather_id, description)
        temp_c      = round(cur["main"]["temp"], 1)
        feels_like  = round(cur["main"]["feels_like"], 1)
        humidity    = cur["main"].get("humidity")
        wind_kph    = round(cur["wind"].get("speed", 0) * 3.6, 1)  # m/s → km/h
        visibility  = round(cur.get("visibility", 0) / 1000, 1)    # m → km

        current = {
            "temp_c":        temp_c,
            "feels_like_c":  feels_like,
            "condition":     condition,
            "icon":          _condition_icon(condition),
            "humidity":      humidity,
            "wind_kph":      wind_kph,
            "uv_index":      None,   # cần One Call API
            "visibility_km": visibility,
        }

        # ── 2. DỰ BÁO 5 NGÀY (3h/lần) → gom thành ngày ───────────────────
        fc_resp = requests.get(
            f"{BASE}/forecast",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric", "lang": "vi"},
            timeout=8,
        )
        forecast = []
        if fc_resp.status_code == 200:
            fc_data = fc_resp.json().get("list", [])

            # Gom theo ngày (key = "YYYY-MM-DD")
            days: dict[str, dict] = {}
            for item in fc_data:
                dt   = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
                key  = dt.strftime("%Y-%m-%d")
                temp = item["main"]["temp"]
                pop  = item.get("pop", 0)  # probability of precipitation 0-1
                w_id = item["weather"][0]["id"]
                desc = item["weather"][0].get("description", "")

                if key not in days:
                    days[key] = {"high": temp, "low": temp, "pop_max": pop,
                                 "w_id": w_id, "desc": desc, "dt": dt,
                                 "hourly": []}
                else:
                    days[key]["high"]    = max(days[key]["high"], temp)
                    days[key]["low"]     = min(days[key]["low"],  temp)
                    days[key]["pop_max"] = max(days[key]["pop_max"], pop)
                    # Lấy điều kiện lúc 12h trưa nếu có
                    if dt.hour == 12:
                        days[key]["w_id"] = w_id
                        days[key]["desc"] = desc

                # Ghi lại slot 3h nếu có mưa (pop >= 20%)
                if pop >= 0.2:
                    days[key]["hourly"].append({
                        "hour":  dt.hour,           # 0,3,6,9,12,15,18,21
                        "pop":   int(pop * 100),    # %
                        "temp":  round(temp, 1),
                        "desc":  _owm_condition_vi(w_id, item["weather"][0].get("description",""))
                    })

            for key, d in sorted(days.items())[:7]:
                cond = _owm_condition_vi(d["w_id"], d["desc"])
                dt   = d["dt"]

                # Tóm tắt giờ mưa thành chuỗi dễ đọc, VD "6h–9h, 15h–18h"
                rain_hours = d.get("hourly", [])
                rain_slots = []
                for slot in sorted(rain_hours, key=lambda x: x["hour"]):
                    h = slot["hour"]
                    label = f"{h}h–{h+3}h ({slot['pop']}%)"
                    rain_slots.append(label)

                forecast.append({
                    "day":         _day_vi(dt),
                    "date":        dt.strftime("%d/%m"),
                    "high_c":      round(d["high"], 1),
                    "low_c":       round(d["low"],  1),
                    "condition":   cond,
                    "icon":        _condition_icon(cond),
                    "rain_chance": int(d["pop_max"] * 100),
                    # MỚI: khung giờ có mưa (list chuỗi, rỗng nếu không mưa)
                    "rain_hours":  rain_slots,
                    # MỚI: nhiệt độ buổi sáng/chiều/tối
                    "hourly":      [{"hour": s["hour"], "pop": s["pop"], "temp": s["temp"], "desc": s["desc"]}
                                    for s in sorted(rain_hours, key=lambda x: x["hour"])],
                })

        result = {
            "success":       True,
            "location":      loc,
            "current":       current,
            "forecast":      forecast,
            "travel_advice": _travel_advice(condition, temp_c),
            "unit":          "celsius",
            "source":        "OpenWeatherMap",
        }
        _cache_set(cache_key, result)
        return result

    except Exception as e:
        print(f"[weather_service] Lỗi: {e}")
        return {"success": False, "error": str(e), "error_code": "EXCEPTION"}