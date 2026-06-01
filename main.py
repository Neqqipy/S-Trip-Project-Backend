# pip install -r requirements.txt
# python main.py

import os, re, urllib.parse, time, requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import timedelta 

# Import các service
from hotel_services import get_smart_hotel_recommendations
from flight_services import get_smart_flight_recommendations, resolve_airport, is_route_operated, get_effective_iata
from direction_service import get_all_modes_directions
from transport_service import decide_transport
from auth_routes import auth_bp, init_oauth 
from itinerary_builder import build_itinerary
from ThuatToanDeXuat import apply_recommendation_algorithm


load_dotenv()
app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "dev-key")
app.permanent_session_lifetime = timedelta(days=30)

# Khi deploy HTTPS / Codespaces: HTTPS=true trong .env
# Khi dev localhost: để mặc định (không cần set gì)
_IS_HTTPS = (
    os.getenv('FLASK_ENV', 'development') == 'production'
    or os.getenv('HTTPS', '') == 'true'
)

app.config.update(
    SESSION_COOKIE_SAMESITE='None' if _IS_HTTPS else 'Lax',
    SESSION_COOKIE_SECURE=_IS_HTTPS,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_NAME='strip_session',
    SESSION_COOKIE_DOMAIN=None,
)

# CORS: hỗ trợ nhiều FRONTEND_URL cách nhau bằng dấu phẩy
# Ví dụ .env Codespaces:
#   FRONTEND_URL=https://ten-codespace-3000.app.github.dev
# Ví dụ .env localhost: để trống hoặc http://localhost:3000
_raw_origins = os.getenv("FRONTEND_URL", "http://localhost:3000")
_FRONTEND_ORIGINS = list({
    o.strip()
    for o in _raw_origins.split(",")
    if o.strip()
} | {"http://localhost:3000", "http://127.0.0.1:3000"})

CORS(app, supports_credentials=True, origins=_FRONTEND_ORIGINS)

app.register_blueprint(auth_bp)
init_oauth(app)

# FIX: In-memory cache cho proxy ảnh — tránh fetch lại cùng URL nhiều lần
_proxy_image_cache = {}
_tips_cache = {}
_activity_cache = {}

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# ✅ Chỉ import SerpAPI khi có key (tránh lỗi khi chạy không có key)
def get_google_search():
    if not SERPAPI_KEY:
        return None
    from serpapi import GoogleSearch
    return GoogleSearch

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "S-Trip Backend is working fine!",
        "version": "1.0.0"
    })

@app.route('/api/ai-specialties-tips')
def ai_specialties_tips():
    location = request.args.get('location', '').strip()
    if not location:
        return jsonify({'error': 'Missing location'}), 400
 
    if location in _tips_cache:
        return jsonify(_tips_cache[location])
 
    try:
        SERPAPI_KEY = os.environ.get('SERPAPI_KEY', '')
 
        # Search đặc sản nên mua tại location
        params = {
            'engine': 'google',
            'q': f'đặc sản {location} nên mua về làm quà',
            'api_key': SERPAPI_KEY,
            'hl': 'vi',
            'gl': 'vn',
            'num': 5,
        }
        resp = requests.get('https://serpapi.com/search', params=params, timeout=10)
        data = resp.json()
 
        items = set()
 
        # Lấy từ answer box / featured snippet nếu có
        answer = data.get('answer_box', {})
        for field in ['snippet', 'answer', 'list']:
            val = answer.get(field, '')
            if isinstance(val, list):
                for v in val:
                    text = re.sub(r'\(.*?\)', '', str(v)).strip(' .,;:-')
                    if 3 < len(text) < 60:
                        items.add(text)
            elif isinstance(val, str):
                for part in re.split(r'[,;\n•\-–]', val):
                    part = re.sub(r'\(.*?\)', '', part).strip(' .,;:-')
                    if 3 < len(part) < 60:
                        items.add(part)
 
        # Lấy thêm từ organic results snippets
        for r in data.get('organic_results', [])[:4]:
            snippet = r.get('snippet', '')
            for part in re.split(r'[,;\n•]', snippet):
                part = re.sub(r'\(.*?\)', '', part).strip(' .,;:-')
                if 3 < len(part) < 50:
                    items.add(part)
 
        items = list(items)[:8]
 
        # Tip mặc định nếu không parse được
        if not items:
            items = [f'Đặc sản {location}']
 
        result = {
            'items': items,
            'tip': f'Nên mua tại chợ địa phương hoặc cửa hàng đặc sản uy tín ở {location} để đảm bảo chất lượng.'
        }
        _tips_cache[location] = result
        return jsonify(result)
 
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/chat-gemini", methods=["POST"])
def chat_gemini():
    try:
        data = request.get_json()
        user_msg = data.get("message", "")
        location = data.get("location", "Đà Nẵng")

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-3.1-flash-lite')

        full_prompt = f"Bạn là trợ lý du lịch. Hãy trả lời cực kỳ ngắn gọn câu hỏi của bạn về du lịch {location}: {user_msg}"

        print(f"[AI Chat] 🚀 Đang gọi Gemini 3.1 dự đoán ngân sách/thời tiết...")
        response = model.generate_content(full_prompt)

        if response and response.text:
            print(f"[AI Chat] ✅ AI dự đoán thành công!")
            return jsonify({"success": True, "text": response.text})
        else:
            return jsonify({"success": False, "error": "Empty response"})

    except Exception as e:
        print(f"❌ DEBUG LỖI THỰC TẾ: {str(e)}")
        return jsonify({
            "success": True,
            "text": f"Hệ thống Gemini đang phản hồi chậm. Bạn muốn biết gì về khách sạn ở {location} không?"
        })



GOOGLE_IMG_DOMAINS = (
    "googleusercontent.com", "ggpht.com",
    "googleapis.com", "googleapi",
)

def to_proxy_url(url, base=None):
    """
    Wrap URL ảnh qua /api/proxy-image.
    - Ảnh local (/assets/...) hoặc data:/blob: → trả nguyên
    - placeholder → trả nguyên
    - Tất cả external URL → wrap qua proxy (đồng bộ với proxyImage() frontend)
    """
    if not url:
        return url
    if url.startswith("data:") or url.startswith("blob:"):
        return url
    if "placehold.co" in url or "placeholder" in url:
        return url
    if "api/proxy-image" in url:
        return url
    # Ảnh local same-origin (bắt đầu bằng /) → không cần proxy
    if url.startswith("/"):
        return url

    if base is None:
        try:
            from flask import request as _req
            base = _req.host_url.rstrip("/")
        except RuntimeError:
            base = os.getenv("API_BASE_URL", "http://localhost:5000")

    # Google Maps: ép size w1200-h900 để ảnh nét hơn
    optimized = url
    if any(d in url for d in GOOGLE_IMG_DOMAINS):
        if "=" in optimized:
            optimized = optimized[:optimized.index("=")] + "=w1200-h900-k-no"
        else:
            optimized = optimized + "=w1200-h900-k-no"

    return f"{base}/api/proxy-image?url={urllib.parse.quote(optimized, safe='')}"

# ----------------------------------------------------------------
# 🕐 PHÂN LOẠI BUỔI PHÙ HỢP CHO ĐỊA ĐIỂM
# ----------------------------------------------------------------
_TIME_KEYWORDS = {
    "morning": [
        "núi", "thác", "hồ", "vịnh", "bình minh", "sunrise",
        "trekking", "leo núi", "hiking", "rừng", "vườn quốc gia",
        "biển sáng", "đảo", "hang động", "đi bộ",
        "cà phê", "cafe", "coffee", "bánh mì", "phở", "bún",
        "chợ sáng", "chùa", "đền", "lăng", "tẩm", "làng nghề", "chợ nổi",
        "sáng", "điểm tâm", "cung đình", "đại nội", "cố đô", "thiên nhiên"
    ],
    "afternoon": [
        "bảo tàng", "museum", "gallery", "triển lãm", "di tích",
        "khu phố cổ", "trung tâm thương mại",
        "mua sắm", "shopping", "spa", "công viên", "vui chơi",
        "tháp", "cầu", "toà nhà", "kiến trúc", "làng",
        "chiều", "hoàng hôn", "chè", "ăn vặt", "kem", "nắng", "biển", "trưa"
    ],
    "evening": [
        "nhà hàng", "restaurant", "quán ăn", "hải sản", "lẩu",
        "nướng", "buffet", "dimsum", "sushi", "cơm tối", "ốc",
        "chợ đêm", "night market", "bar", "pub", "rooftop",
        "club", "show", "biểu diễn", "sunset", "phố đi bộ",
        "view đêm", "phố đêm", "tối", "đêm", "night", "evening", "nhậu"
    ],
}

_SLOT_LABEL = {
    "morning":   "🌅 Buổi sáng",
    "afternoon": "☀️ Buổi chiều",
    "evening":   "🌙 Buổi tối",
}

def _guess_best_time(name: str, desc: str) -> str:
    """
    Đoán buổi phù hợp nhất dựa trên keyword trong tên + mô tả địa điểm.

    Trả về một trong:
      "🌅 Buổi sáng" | "☀️ Buổi chiều" | "🌙 Buổi tối"

    Mặc định "☀️ Buổi chiều" nếu không match keyword nào.
    """
    text = f"{name} {desc}".lower()

    scores = {slot: 0 for slot in _TIME_KEYWORDS}
    for slot, keywords in _TIME_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[slot] += 1

    best = max(scores, key=scores.get)

    # Không match bất kỳ keyword nào → mặc định chiều (trung lập nhất)
    if scores[best] == 0:
        return _SLOT_LABEL["afternoon"]

    return _SLOT_LABEL[best]


# ----------------------------------------------------------------
# 🖼️ FALLBACK ẢNH CHO ACTIVITY
# ----------------------------------------------------------------

def _best_photo_url(photo: dict) -> str | None:
    """
    Ưu tiên lấy ảnh chất lượng cao nhất từ 1 phần tử trong mảng 'photos' SerpAPI.
    Thứ tự: original_image > image_url > image > thumbnail
    """
    return (
        photo.get("original_image")
        or photo.get("image_url")
        or photo.get("image")
        or photo.get("thumbnail")
    )

def get_activity_image_fallback(place_name, location, api_key):
    """
    Tìm ảnh thật cho tour/food theo 2 tầng:
      1. Google Maps Photos (qua data_id) — ảnh chính thức
      2. Google Images — fallback nhanh
    """
    GoogleSearch = get_google_search()
    if not GoogleSearch:
        return None

    # Tầng 1: Google Maps Photos
    try:
        maps_res = GoogleSearch({
            "engine": "google_maps",
            "q": f"{place_name} {location}",
            "hl": "vi",
            "api_key": api_key,
        }).get_dict()

        data_id = (
            maps_res.get("place_results", {}).get("data_id")
            or next(
                (r.get("data_id") for r in maps_res.get("local_results", []) if r.get("data_id")),
                None,
            )
        )

        if data_id:
            photos = GoogleSearch({
                "engine": "google_maps_photos",
                "data_id": data_id,
                "hl": "vi",
                "api_key": api_key,
            }).get_dict().get("photos", [])
            if photos:
                img = _best_photo_url(photos[0])
                if img:
                    return img
    except Exception:
        pass

    # Tầng 2: Google Images
    try:
        images = GoogleSearch({
            "engine": "google_images",
            "q": f"{place_name} {location}",
            "api_key": api_key,
        }).get_dict().get("images_results", [])
        if images:
            img = images[0].get("original") or images[0].get("thumbnail")
            if img:
                return img
    except Exception:
        pass

    # Tầng 3: Wikipedia API (Miễn phí, không cần key, hữu ích khi SerpAPI hết hạn mức)
    try:
        import requests, urllib.parse
        wiki_url = f"https://vi.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(place_name + ' ' + location)}&gsrlimit=1&prop=pageimages&format=json&piprop=original"
        wiki_res = requests.get(wiki_url, timeout=5).json()
        pages = wiki_res.get("query", {}).get("pages", {})
        if pages:
            for page_id, page_data in pages.items():
                if "original" in page_data:
                    img = page_data["original"]["source"]
                    if img:
                        return img
    except Exception as e:
        print(f"[Wikipedia Fallback Error]: {e}")
        pass

    return None


# ----------------------------------------------------------------
# 🗺️ LẤY DANH SÁCH HOẠT ĐỘNG + GẮN NHÃN BUỔI
# ----------------------------------------------------------------

def get_real_activities(location, query_type):
    """
    Lấy dữ liệu thực từ Google Local.
    Mỗi địa điểm trả về có thêm trường `best_time` (buổi phù hợp nhất).
    Trả về [] nếu không có SERPAPI_KEY.
    """
    cache_key = f"{location}_{query_type}"
    if cache_key in _activity_cache:
        print(f"[Cache Hit] get_real_activities: {cache_key}")
        return _activity_cache[cache_key]

    GoogleSearch = get_google_search()
    if not GoogleSearch:
        print(f"[Cảnh báo] Không có SERPAPI_KEY, bỏ qua tìm kiếm '{query_type}'")
        return []

    try:
        search = GoogleSearch({
            "engine": "google_local",
            "q": f"{query_type} tại {location}",
            "location": "Vietnam",
            "hl": "vi",
            "api_key": SERPAPI_KEY
        })

        search_data = search.get_dict()

        if "error" in search_data:
            print("🚨 LỖI SERPAPI:", search_data["error"])

        results = search_data.get("local_results", [])

        processed_results = []
        for r in results:
            img_url = r.get("featured_image")  # thumbnail local_results quá nhỏ, bỏ qua

            # Nếu featured_image là encrypted-tbn thì cũng bỏ
            if img_url and "encrypted-tbn" in img_url:
                img_url = None
                
            raw_data_id  = r.get("data_id", "")

            # Ưu tiên lấy ảnh chất lượng cao trực tiếp bằng data_id (tiết kiệm SerpAPI call)
            if not img_url and raw_data_id:
                try:
                    photos_res = GoogleSearch({
                        "engine": "google_maps_photos",
                        "data_id": raw_data_id,
                        "hl": "vi",
                        "api_key": SERPAPI_KEY,
                    }).get_dict()
                    photos = photos_res.get("photos", [])
                    if photos:
                        img_url = _best_photo_url(photos[0])
                except Exception:
                    pass

            # Nếu SerpAPI không trả ảnh, tìm ảnh thật từ Maps / Google Images
            if not img_url:
                img_url = get_activity_image_fallback(r.get("title", ""), location, SERPAPI_KEY)

            # Placeholder cuối cùng nếu mọi nguồn đều thất bại
            if not img_url:
                img_url = "https://placehold.co/300x200?text=S-Trip"

            name = r.get("title", "")
            desc = r.get("description", f"Địa điểm {query_type} nổi tiếng.")
            coords = r.get("gps_coordinates", {})

            price = r.get("price", "Giá tuỳ chọn")

            # FIX MAP: SerpAPI trả 2 loại ID:
            # - place_id dạng "ChIJ..." → dùng cho Google Maps Embed / Places API
            # - data_id  dạng "0x..."   → chỉ dùng nội bộ với google_maps_photos
            # Frontend cần ChIJ để nhúng map → lọc bỏ data_id dạng hex
            raw_place_id = r.get("place_id", "")
            raw_data_id  = r.get("data_id", "")
            maps_place_id = raw_place_id if raw_place_id and not raw_place_id.startswith("0x") else ""

            processed_results.append({
                "name":      name,
                "rating":    str(r.get("rating", "4.5")),
                "price":     price,
                "desc":      desc,
                "thumbnail": to_proxy_url(img_url),
                "lat":       coords.get("latitude"),
                "lng":       coords.get("longitude"),
                # FIX: place_id (ChIJ) cho embed map, data_id (0x) cho photos API
                "place_id":  maps_place_id,
                "data_id":   raw_data_id,
                # Tạm thời gán None, lát nữa gọi AI batch
                "best_time": None,
            })

        # ✅ Gọi AI phân loại hàng loạt cho tất cả các địa điểm vừa tìm được
        names_with_desc = [{"name": r["name"], "desc": r.get("desc", "")} for r in processed_results]
        ai_labels = {}
        try:
            from ai_time_filter import get_ai_time_filter
            ai_labels = get_ai_time_filter(names_with_desc)
        except Exception as e:
            print(f"[AI Time Filter Error] {e}")

        _SLOT_MAP = {
            "morning": "🌅 Buổi sáng",
            "afternoon": "☀️ Buổi chiều",
            "evening": "🌙 Buổi tối"
        }

        # Gắn nhãn AI và giá, nếu AI trượt thì fallback
        for item in processed_results:
            ai_data = ai_labels.get(item["name"], {})
            
            # 1. Gán thời gian
            best_time_key = ai_data.get("best_time")
            if best_time_key in _SLOT_MAP:
                item["best_time"] = _SLOT_MAP[best_time_key]
            else:
                item["best_time"] = _guess_best_time(item["name"], item["desc"])
                
            # 2. Cập nhật giá dự đoán
            if ai_data.get("estimated_price") and item["price"] == "Giá tuỳ chọn":
                item["price"] = ai_data["estimated_price"]

        final_results = processed_results[:20]
        _activity_cache[cache_key] = final_results
        return final_results

    except Exception as e:
        print(f"[Lỗi SerpAPI - {query_type}] {str(e)}")
        return []


@app.route("/api/directions", methods=["GET"])
def directions():
    """
    Lấy khoảng cách + thời gian giữa 2 điểm cho tất cả phương tiện.
    Query params:
      origin      — tên hoặc "lat,lng"
      destination — tên hoặc "lat,lng"
    """
    origin      = request.args.get("origin", "")
    destination = request.args.get("destination", "")
    if not origin or not destination:
        return jsonify({"success": False, "error": "Thiếu origin hoặc destination"}), 400
    try:
        modes = get_all_modes_directions(SERPAPI_KEY, origin, destination)
        return jsonify({"success": True, "modes": modes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/api/plan-trip", methods=["GET"])
def plan_trip():
    location       = request.args.get("location", "Đà Lạt")
    # Cho phép frontend truyền ?origin= hoặc ?from= (alias tiện hơn)
    origin         = request.args.get("origin") or request.args.get("from", "TP. Hồ Chí Minh")
    budget_raw     = request.args.get("budget", "5000000")
    budget         = int(re.sub(r"[^\d]", "", budget_raw))
    departure_date = request.args.get("departure_date", "2026-05-30")

    # Xử lý chuỗi "4 ngày 3 đêm" để lấy số ngày chuẩn
    days_raw = request.args.get("days", "3")
    m        = re.search(r'\d+', days_raw)
    num_days = int(m.group()) if m else 3

    passengers = int(request.args.get("passengers", 1))

    # Phân bổ ngân sách (40% khách sạn, 40% di chuyển)
    hotel_budget  = budget * 0.4
    transport_budget = budget * 0.4

    try:
        # Dùng ThreadPoolExecutor để chạy song song các API gọi ra ngoài (tăng tốc đáng kể)
        with ThreadPoolExecutor(max_workers=5) as executor:
            # ── 1. Địa điểm tham quan + ăn uống (fetch TRƯỚC để tính trung tâm thực tế) ──
            future_tours = executor.submit(get_real_activities, location, "Điểm tham quan")
            future_foods = executor.submit(get_real_activities, location, "Quán ăn ngon")
            future_breakfasts = executor.submit(get_real_activities, location, "Quán ăn sáng")
            
            tours = future_tours.result()
            foods = future_foods.result() + future_breakfasts.result()

            # ── 2. Tìm Khách sạn & Lấy khoảng cách (chạy song song) ──
            future_hotels = executor.submit(
                get_smart_hotel_recommendations,
                SERPAPI_KEY, location, hotel_budget, num_days, passengers, departure_date,
                tours=tours, foods=foods
            )
            future_directions = executor.submit(get_all_modes_directions, SERPAPI_KEY, origin, location)

            hotels = future_hotels.result()
            
            driving_info = None
            distance_m   = None
            driving_duration_text = None
            try:
                all_modes = future_directions.result()
                if isinstance(all_modes, dict):
                    driving_info = all_modes.get("driving") or all_modes.get("car")
                elif isinstance(all_modes, list):
                    for m in all_modes:
                        if isinstance(m, dict) and m.get("mode") in ["driving", "car"]:
                            driving_info = m
                            break

                if driving_info:
                    distance_m            = driving_info.get("distance_m")
                    driving_duration_text = driving_info.get("duration_text")
            except Exception as dir_err:
                print(f"[plan_trip] Không lấy được khoảng cách: {dir_err}")

        # ── 3. PHÂN GIẢI SÂN BAY ────────────────────────────────────────────
        origin_info = resolve_airport(origin)
        dest_info   = resolve_airport(location)

        no_airport  = dest_info["no_airport"] or origin_info["no_airport"]
        # ✅ Gộp cả 2 note thay vì bỏ mất 1 bên
        _notes = [n for n in [dest_info.get("note"), origin_info.get("note")] if n]
        flight_note = " | ".join(_notes) if _notes else ""

        # ── 4. LẤY CHUYẾN BAY THẬT SỰ TỪ API ────────
        FLIGHT_THRESHOLD_M = 150_000  # > 150km mới kích hoạt tìm máy bay
        flights = []

        # distance_m = 0 cũng coi là lỗi → treat như None
        distance_m_valid = distance_m if distance_m else None

        # Tính effective IATA (có thể qua hub) trước khi check same_airport,
        # vì 2 thành phố khác nhau có thể cùng hub (VD: Đồng Nai + Vũng Tàu → SGN)
        raw_origin_iata = origin_info["iata"]
        raw_dest_iata   = dest_info["iata"]

        # get_effective_iata() xét hướng đi để chọn hub đúng:
        #   Bạc Liêu→DAD: CAH→[SGN]→DAD   Bạc Liêu→HAN: CAH→HAN trực tiếp
        #   Đà Lạt→BMV:   DLI→[SGN]→BMV   Đồng Nai→Vũng Tàu: SGN→SGN (same hub)
        effective_origin_iata = get_effective_iata(raw_origin_iata, raw_dest_iata)
        effective_dest_iata   = get_effective_iata(raw_dest_iata,   effective_origin_iata)

        # same_airport: chỉ true khi raw IATA của 2 tỉnh giống nhau
        # (VD: Đồng Nai + Vũng Tàu đều map về SGN raw)
        # KHÔNG dùng effective để check — vì effective có thể trùng hub dù raw khác
        # (VD: Huế→HUI, Vũng Tàu→SGN, effective HUI→SGN — vẫn là 2 sân bay khác)
        same_airport = bool(raw_origin_iata and raw_origin_iata == raw_dest_iata)

        if same_airport:
            hub = effective_origin_iata or raw_origin_iata or "?"
            flight_note = (
                f"Điểm xuất phát và đến cùng khu vực sân bay ({hub}), không cần bay — "
                f"đề xuất di chuyển bằng xe."
            )

        # iata dùng trong flight_meta để frontend hiển thị
        # nếu None (thành phố không nhận ra) → giữ None, frontend tự xử lý
        flight_meta = {
            "origin_airport":    effective_origin_iata or raw_origin_iata,
            "dest_airport":      effective_dest_iata   or raw_dest_iata,
            "raw_origin_airport": raw_origin_iata,
            "raw_dest_airport":   raw_dest_iata,
            "no_airport":        no_airport,
            "note":              flight_note,
        }

        route_has_flights = (
            not same_airport
            and bool(effective_origin_iata)
            and bool(effective_dest_iata)
            and is_route_operated(effective_origin_iata, effective_dest_iata)
        )
        should_search_flights = (
            route_has_flights
            and (distance_m_valid is None or distance_m_valid > FLIGHT_THRESHOLD_M)
        )
        flight_available_flag = route_has_flights

        if should_search_flights:
            flights = get_smart_flight_recommendations(
                SERPAPI_KEY, effective_origin_iata, effective_dest_iata,
                budget, num_days, passengers, departure_date,
            )

        print(f"[DEBUG] should_search={should_search_flights}, eff_origin={effective_origin_iata}, eff_dest={effective_dest_iata}, route_ok={route_has_flights}, same={same_airport}, dist={distance_m_valid}")

        # ── 5. QUYẾT ĐỊNH PHƯƠNG TIỆN ───────────────────────────────────────────
        transport = decide_transport(
            origin                = origin,
            destination           = location,
            distance_m            = distance_m_valid,
            driving_duration_text = driving_duration_text,
            flight_available      = flight_available_flag,
            origin_info           = origin_info,   # raw info (iata sân bay gần nhất, dùng build leg xe)
            dest_info             = dest_info,     # raw info
            real_flights          = flights,
            # Truyền thêm effective iata để build label chuyến bay đúng hub
            effective_origin_iata = effective_origin_iata,
            effective_dest_iata   = effective_dest_iata,
        )
        hotels, tours, foods = apply_recommendation_algorithm(hotels, tours, foods, budget)
        return jsonify({
            "success": True,
            "plan": {
                # Thông tin sân bay (tương thích ngược với frontend cũ)
                "flight_meta": flight_meta,
                "flights":     flights or [],
                # ✅ MỚI: transport chứa đầy đủ lựa chọn phương tiện
                "transport":   transport,
                "hotels":      hotels  or [],
                "tours":       tours   or [],
                "foods":       foods   or [],
                # ✅ Lịch trình theo ngày/buổi — quán ăn ghép gần địa điểm tham quan
                "itinerary":   build_itinerary(hotels, tours, foods, num_days),
            }
        })
    except Exception as e:
        print(f"Lỗi plan_trip: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/reviews", methods=["GET"])
@app.route("/api/places/reviews", methods=["GET"])
def get_place_reviews():
    place    = request.args.get("place", "") or request.args.get("name", "")
    place_id = request.args.get("place_id", "")

    if place_id and not (place_id.startswith("ChIJ") or "0x" in place_id):
        place_id = ""

    if not place and not place_id:
        return jsonify({"success": False, "reviews": []})

    GoogleSearch = get_google_search()
    if not GoogleSearch:
        return jsonify({"success": True, "reviews": []})

    try:
        reviews       = []
        total_reviews = 0

        # 1. FALLBACK:
        if not place_id and place:
            search_data  = GoogleSearch({"engine": "google_maps", "q": place, "hl": "vi", "api_key": SERPAPI_KEY}).get_dict()
            place_results = search_data.get("place_results", {})

            place_id = place_results.get("place_id") or place_results.get("data_id", "")

            if not place_id:
                local_data = GoogleSearch({
                    "engine": "google_local",
                    "q": place, # 🟢 Bỏ chữ "điểm du lịch"
                    "location": "Vietnam",
                    "hl": "vi",
                    "api_key": SERPAPI_KEY
                }).get_dict()

            # Ưu tiên 3 (Dành cho Khách sạn): Không có ID nhưng Maps trả sẵn review
            if not place_id and "reviews" in place_results:
                reviews       = place_results.get("reviews", [])
                total_reviews = place_results.get("reviews_unparsed", len(reviews))

        # 2. KHI ĐÃ CÓ ID (Do Frontend truyền hoặc do Fallback tìm ra)
        if place_id:
            params = {"engine": "google_maps_reviews", "place_id": place_id, "hl": "vi", "api_key": SERPAPI_KEY}
            data   = GoogleSearch(params).get_dict()

            if "error" not in data:
                reviews       = data.get("reviews", [])
                total_reviews = data.get("place_info", {}).get("reviews") or len(reviews)

        # 3. CHUẨN HÓA DỮ LIỆU TRẢ VỀ FRONTEND
        result = [{
            "user":    r.get("user", {}).get("name", "Ẩn danh"),
            "avatar":  r.get("user", {}).get("thumbnail"),
            "rating":  r.get("rating"),
            "content": r.get("snippet", "") or r.get("text", ""),
            "date":    r.get("date", ""),
            "photos":  r.get("images", [])
        } for r in reviews]

        return jsonify({"success": True, "reviews": result, "total": total_reviews})

    except Exception as e:
        print(f"[Lỗi reviews] {e}")
        return jsonify({"success": False, "reviews": [], "error": str(e)})


@app.route("/api/province-images", methods=["GET"])
def get_province_images():
    """
    Lấy ảnh tỉnh thành từ Google Maps Photos (full size, ổn định).
    Query param: place — tên tỉnh
    """
    place = request.args.get("place", "")
    if not place:
        return jsonify({"success": False, "images": []})

    GoogleSearch = get_google_search()
    if not GoogleSearch:
        return jsonify({"success": True, "images": []})

    try:
        search_data = GoogleSearch({
            "engine": "google_maps",
            "q": f"du lịch {place} Việt Nam",
            "hl": "vi",
            "gl": "vn",
            "api_key": SERPAPI_KEY
        }).get_dict()

        data_id = None
        place_results = search_data.get("place_results", {})
        data_id = place_results.get("data_id")

        if not data_id:
            local_results = search_data.get("local_results", [])
            for r in local_results:
                if r.get("data_id"):
                    data_id = r["data_id"]
                    break

        if not data_id:
            return jsonify({"success": False, "images": []})

        photos_data = GoogleSearch({
            "engine": "google_maps_photos",
            "data_id": data_id,
            "hl": "vi",
            "api_key": SERPAPI_KEY
        }).get_dict()

        photos = photos_data.get("photos", [])
        images = [p.get("image") or p.get("thumbnail") for p in photos
                  if p.get("image") or p.get("thumbnail")]

        return jsonify({"success": True, "images": images[:15]})

    except Exception as e:
        print(f"[Lỗi province-images] {e}")
        return jsonify({"success": False, "images": []})


@app.route("/api/images", methods=["GET"])
@app.route("/api/places/images", methods=["GET"])
def get_place_images():
    place     = request.args.get("place", "") or request.args.get("name", "")
    passed_id = request.args.get("place_id", "")

    # Engine google_maps_photos BẮT BUỘC dùng định dạng ID là 0x...:0x...
    data_id = passed_id if passed_id and "0x" in passed_id else ""

    if not place and not data_id:
        return jsonify({"success": False, "images": []})

    GoogleSearch = get_google_search()
    if not GoogleSearch:
        return jsonify({"success": True, "images": []})

    try:
        photos = []

        # 1. FALLBACK: TÌM LẠI ĐÚNG DATA_ID CHUẨN (0x...:0x...)
        if not data_id and place:
            search_data   = GoogleSearch({"engine": "google_maps", "q": place, "hl": "vi", "api_key": SERPAPI_KEY}).get_dict()
            place_results = search_data.get("place_results", {})
            data_id       = place_results.get("data_id")

            if not data_id:
                local_results = search_data.get("local_results", [])
                if local_results:
                    data_id = local_results[0].get("data_id")

        # 2. GỌI ENGINE LẤY ẢNH VỚI THAM SỐ `data_id`
        if data_id:
            data   = GoogleSearch({"engine": "google_maps_photos", "data_id": data_id, "hl": "vi", "api_key": SERPAPI_KEY}).get_dict()
            photos = data.get("photos", [])

        images = [p.get("image") or p.get("thumbnail") for p in photos if p.get("image") or p.get("thumbnail")]
        
        # 3. FALLBACK WIKIPEDIA NẾU KHÔNG CÓ ẢNH TỪ SERPAPI (Hết Quota)
        if not images and place:
            try:
                import requests, urllib.parse
                wiki_url = f"https://vi.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(place)}&gsrlimit=1&prop=pageimages&format=json&piprop=original"
                wiki_res = requests.get(wiki_url, timeout=5).json()
                pages = wiki_res.get("query", {}).get("pages", {})
                if pages:
                    for page_id, page_data in pages.items():
                        if "original" in page_data:
                            img = page_data["original"]["source"]
                            if img:
                                images.append(img)
            except Exception as e:
                print(f"[Wikipedia Fallback Error /api/places/images]: {e}")

        return jsonify({"success": True, "images": images[:10]})

    except Exception as e:
        print(f"[Lỗi images] {e}")
        return jsonify({"success": False, "images": []})


@app.route("/api/proxy-image", methods=["GET"])
def proxy_image():
    """
    Proxy ảnh từ Google (lh3.googleusercontent.com, v.v.) về browser.
    - In-memory cache: cùng URL chỉ fetch 1 lần duy nhất từ Google
    - Cache-Control header: browser tự cache 1 giờ, không gọi lại server
    """
    import urllib.parse
    import urllib.request
    from flask import Response

    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "Thiếu url"}), 400

    # ✅ Whitelist domain được phép proxy ảnh
    ALLOWED = (
        "lh1.googleusercontent.com",
        "lh2.googleusercontent.com",
        "lh3.googleusercontent.com",
        "lh4.googleusercontent.com",
        "lh5.googleusercontent.com",
        "lh6.googleusercontent.com",
        "streetviewpixels-pa.googleapis.com",
        "maps.googleapis.com",
        "geo0.ggpht.com",
        "geo1.ggpht.com",
        "geo2.ggpht.com",
        "geo3.ggpht.com",
        "serpapi.com",
        "encrypted-tbn0.gstatic.com",
        "encrypted-tbn1.gstatic.com",
        "encrypted-tbn2.gstatic.com",
        "encrypted-tbn3.gstatic.com",
        # TripAdvisor
        "dynamic-media-cdn.tripadvisor.com",
        "media-cdn.tripadvisor.com",
        "tripadvisor.com",
        # Khác
        "images.unsplash.com",
        "placehold.co",
        "via.placeholder.com",
        "upload.wikimedia.org",
    )
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc  # vd: "localhost:3000" hoặc "lh3.googleusercontent.com"

    # ✅ Ảnh same-origin (localhost dev hoặc frontend production) → fetch trực tiếp
    # _toDataUrl trong AiSchedule gửi img.src dạng "http://localhost:3000/assets/vj.png"
    # vào đây — không cần proxy vòng, fetch thẳng từ frontend server
    frontend_host = urllib.parse.urlparse(
        os.getenv("FRONTEND_URL", "http://localhost:3000")
    ).netloc
    same_origin_hosts = {request.host, frontend_host, "localhost:3000", "127.0.0.1:3000"}
    if netloc in same_origin_hosts:
        try:
            req_local = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_local, timeout=5) as r:
                content_type = r.headers.get("Content-Type", "image/png")
                data         = r.read()
            resp = Response(data, content_type=content_type)
            resp.headers["Cache-Control"] = "public, max-age=86400"
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp
        except Exception as e:
            print(f"[PROXY LOCAL FAIL] {url[:80]} → {e}")
            return Response(status=404)

    # Kiểm tra whitelist cho external domain
    if not any(netloc == d or netloc.endswith("." + d) for d in ALLOWED):
        return jsonify({"error": "Domain không được phép"}), 403

    if url in _proxy_image_cache:
        data, content_type = _proxy_image_cache[url]
        resp = Response(data, content_type=content_type)
        resp.headers["Cache-Control"] = "public, max-age=3600"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer":    "https://www.google.com/",
            "Accept":     "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            content_type = r.headers.get("Content-Type", "image/jpeg")
            data         = r.read()

        if len(_proxy_image_cache) < 500:
            _proxy_image_cache[url] = (data, content_type)

        resp = Response(data, content_type=content_type)
        resp.headers["Cache-Control"] = "public, max-age=3600"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    except Exception as e:
        print(f"[PROXY FAIL] {url[:80]} → {e}")
        return Response(status=302, headers={
            "Location": "https://placehold.co/400x300?text=S-Trip+Hotel",
            "Access-Control-Allow-Origin": "*",
        })


@app.route("/api/proxy-image-b64", methods=["GET"])
def proxy_image_b64():
    """
    Trả ảnh dạng base64 data URL — dùng cho html2canvas screenshot.
    html2canvas không đọc được blob/proxy URL cross-origin,
    nhưng data URL thì luôn hoạt động.
    """
    import urllib.parse, urllib.request, base64
    from flask import Response

    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "Thiếu url"}), 400

    # Thử lấy từ cache proxy thường trước
    if url in _proxy_image_cache:
        data, content_type = _proxy_image_cache[url]
        b64 = base64.b64encode(data).decode()
        return jsonify({"data": f"data:{content_type};base64,{b64}"})

    # ✅ Đồng bộ whitelist với /api/proxy-image
    ALLOWED_B64 = (
        "lh1.googleusercontent.com", "lh2.googleusercontent.com",
        "lh3.googleusercontent.com", "lh4.googleusercontent.com",
        "lh5.googleusercontent.com", "lh6.googleusercontent.com",
        "streetviewpixels-pa.googleapis.com", "maps.googleapis.com",
        "geo0.ggpht.com", "geo1.ggpht.com", "geo2.ggpht.com", "geo3.ggpht.com",
        "serpapi.com",
        "encrypted-tbn0.gstatic.com", "encrypted-tbn1.gstatic.com",
        "encrypted-tbn2.gstatic.com", "encrypted-tbn3.gstatic.com",
        "dynamic-media-cdn.tripadvisor.com", "media-cdn.tripadvisor.com",
        "tripadvisor.com", "images.unsplash.com",
        "placehold.co", "via.placeholder.com",
    )
    parsed = urllib.parse.urlparse(url)
    netloc_b64 = parsed.netloc
    if not any(netloc_b64 == d or netloc_b64.endswith("." + d) for d in ALLOWED_B64):
        return jsonify({"error": "Domain không được phép"}), 403

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.google.com/"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            content_type = r.headers.get("Content-Type", "image/jpeg")
            data = r.read()

        if len(_proxy_image_cache) < 300:
            _proxy_image_cache[url] = (data, content_type)

        b64 = base64.b64encode(data).decode()
        resp = jsonify({"data": f"data:{content_type};base64,{b64}"})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    except Exception as e:
        print(f"[B64 FAIL] {url[:80]} → {e}")
        return jsonify({"data": ""}), 200

@app.route("/api/activities", methods=["GET"])
def activities():
    location   = request.args.get("location", "")
    query_type = request.args.get("type", "Quán cà phê")
    results    = get_real_activities(location, query_type)
    return jsonify({"success": True, "results": results})


# ----------------------------------------------------------------
# 🌤️ THỜI TIẾT
# ----------------------------------------------------------------
from weather_service import get_weather as _get_weather

@app.route("/api/weather", methods=["GET"])
def get_weather():
    location = request.args.get("location", "").strip()
    lang     = request.args.get("lang", "vi")
    if not location:
        return jsonify({"success": False, "error": "Thiếu tham số location"}), 400
    result = _get_weather(SERPAPI_KEY, location, lang)
    # Trả 200 kể cả khi lỗi — tránh frontend retry vô hạn
    # Chỉ 502 khi lỗi không mong đợi (exception thật)
    error_code = result.get("error_code", "")
    if not result.get("success") and error_code not in ("NO_API_KEY", "NO_LOCATION"):
        status = 502
    else:
        status = 200
    return jsonify(result), status

# ================================================================
# 🔗 SHARE LINK  —  /trip/<trip_id>  (Supabase)
# ================================================================
import json, hashlib, time

def _gen_id(payload: str) -> str:
    """8 ký tự hex ngắn gọn, đủ unique cho demo."""
    h = hashlib.sha256((payload + str(time.time())).encode()).hexdigest()
    return h[:8]


@app.route("/api/trip/save", methods=["POST"])
def trip_save():
    """
    Body JSON:
      {
        "plan":        <object>,   # toàn bộ plan từ /api/plan-trip
        "dailyPlans":  <array>,    # lịch trình từ AiSchedule state
        "meta": {
          "location":  "Đà Lạt",
          "days":      3,
          "origin":    "TP. Hồ Chí Minh",
          "startDate": "2026-06-01"
        }
      }
    """
    try:
        body = request.get_json(force=True)
        if not body:
            return jsonify({"success": False, "error": "Body rỗng"}), 400

        uid     = _sp_get_uid()
        meta    = body.get("meta", {})
        trip_id = _gen_id(json.dumps(body, ensure_ascii=False, sort_keys=True))

        sb = _get_supabase(uid)
        sb.table("trips").upsert({
            "id":          trip_id,
            "user_id":     str(uid) if uid else "anonymous",
            "location":    meta.get("location",  ""),
            "origin":      meta.get("origin",    ""),
            "days":        int(meta.get("days",  3)),
            "start_date":  meta.get("startDate", ""),
            "plan":        body.get("plan",       {}),
            "daily_plans": body.get("dailyPlans", []),
            "created_at":  int(time.time()),
        }).execute()

        share_url = f"{request.host_url.rstrip('/')}/trip/{trip_id}"
        return jsonify({"success": True, "trip_id": trip_id, "share_url": share_url})

    except Exception as e:
        print(f"[trip_save] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/trip/<trip_id>", methods=["GET"])
def trip_get(trip_id):
    """Trả về JSON data của trip (dùng cho frontend load lại lịch trình)."""
    try:
        sb  = _get_supabase(uid)
        res = sb.table("trips").select("*").eq("id", trip_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy lịch trình"}), 404
        row = res.data[0]
        return jsonify({
            "success":    True,
            "plan":       row.get("plan",        {}),
            "dailyPlans": row.get("daily_plans",  []),
            "meta": {
                "location":  row.get("location",   ""),
                "origin":    row.get("origin",     ""),
                "days":      row.get("days",        3),
                "startDate": row.get("start_date", ""),
            },
            "created_at": row.get("created_at", 0),
        })
    except Exception as e:
        print(f"[trip_get] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/my-trips", methods=["GET"])
def my_trips():
    """Danh sách lịch trình đã lưu của user đang đăng nhập."""
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    try:
        sb  = _get_supabase(uid)
        res = (
            sb.table("trips")
            .select("id, location, origin, days, start_date, created_at")
            .eq("user_id", str(uid))
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify({"success": True, "trips": res.data or []})
    except Exception as e:
        print(f"[my_trips] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/my-trips/<trip_id>", methods=["DELETE"])
def my_trips_delete(trip_id):
    """Xóa 1 lịch trình của user."""
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    try:
        sb  = _get_supabase(uid)
        res = (
            sb.table("trips")
            .delete()
            .eq("id", trip_id)
            .eq("user_id", str(uid))
            .execute()
        )
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy hoặc không có quyền"}), 404
        return jsonify({"success": True})
    except Exception as e:
        print(f"[my_trips_delete] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# 🔍 LỊCH SỬ TÌM KIẾM — /api/search-history (Supabase)
# ================================================================

@app.route("/api/search-history", methods=["GET"])
def search_history_list():
    """Lấy lịch sử tìm kiếm của user, mới nhất lên trước, tối đa 20 mục."""
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    try:
        sb  = _get_supabase(uid)
        res = (
            sb.table("search_history")
            .select("id, location, origin, budget, days, passengers, departure_date, searched_at")
            .eq("user_id", str(uid))
            .order("searched_at", desc=True)
            .limit(20)
            .execute()
        )
        return jsonify({"success": True, "history": res.data or []})
    except Exception as e:
        print(f"[search_history_list] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/search-history", methods=["POST"])
def search_history_add():
    """
    Tự động gọi khi user bấm tìm kiếm.
    Body JSON: { location, origin, budget, days, passengers, departure_date }
    """
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    data = request.get_json(force=True) or {}
    location = (data.get("location", "") or "").strip()
    if not location:
        return jsonify({"success": False, "error": "Thiếu location"}), 400

    try:
        sb = _get_supabase(uid)
        sb.table("search_history").insert({
            "user_id":        str(uid),
            "location":       location,
            "origin":         data.get("origin",         ""),
            "budget":         int(data.get("budget",      0)),
            "days":           int(data.get("days",        3)),
            "passengers":     int(data.get("passengers",  1)),
            "departure_date": data.get("departure_date", ""),
            "searched_at":    int(time.time()),
        }).execute()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[search_history_add] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/search-history/<int:history_id>", methods=["DELETE"])
def search_history_delete(history_id):
    """Xóa 1 mục lịch sử tìm kiếm."""
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    try:
        sb  = _get_supabase(uid)
        res = (
            sb.table("search_history")
            .delete()
            .eq("id", history_id)
            .eq("user_id", str(uid))
            .execute()
        )
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy"}), 404
        return jsonify({"success": True})
    except Exception as e:
        print(f"[search_history_delete] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/search-history/clear", methods=["DELETE"])
def search_history_clear():
    """Xóa toàn bộ lịch sử tìm kiếm của user."""
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    try:
        sb = _get_supabase(uid)
        sb.table("search_history").delete().eq("user_id", str(uid)).execute()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[search_history_clear] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# 🌐 OG TAGS — /trip/<trip_id>  (Zalo / Messenger / Facebook share)
# ================================================================

_OG_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <!-- ── Primary meta ── -->
  <title>{title}</title>
  <meta name="description" content="{description}">

  <!-- ── Open Graph (Facebook, Messenger, Zalo Web) ── -->
  <meta property="og:type"        content="website">
  <meta property="og:url"         content="{url}">
  <meta property="og:title"       content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image"       content="{image}">
  <meta property="og:image:width"  content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:locale"      content="vi_VN">
  <meta property="og:site_name"   content="S-Trip · AI Travel Planner">

  <!-- ── Twitter Card ── -->
  <meta name="twitter:card"        content="summary_large_image">
  <meta name="twitter:title"       content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image"       content="{image}">

  <!-- ── Redirect sau 1s ── -->
  <script>
    setTimeout(function(){{
      window.location.replace("{app_url}");
    }}, 800);
  </script>

  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#f0fdf4;display:flex;align-items:center;justify-content:center;
          min-height:100vh;padding:20px}}
    .card{{background:white;border-radius:24px;padding:40px;max-width:480px;
           text-align:center;box-shadow:0 8px 40px rgba(16,185,129,.15)}}
    .logo{{font-size:48px;margin-bottom:12px}}
    h1{{font-size:22px;font-weight:900;color:#111;margin-bottom:8px}}
    p{{font-size:15px;color:#64748b;line-height:1.5;margin-bottom:24px}}
    .btn{{display:inline-block;background:#10b981;color:white;padding:14px 32px;
          border-radius:99px;font-weight:800;font-size:16px;text-decoration:none}}
    .hint{{font-size:12px;color:#94a3b8;margin-top:16px}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">✈️</div>
    <h1>{title}</h1>
    <p>{description}</p>
    <a class="btn" href="{app_url}">Xem lịch trình →</a>
    <p class="hint">Đang chuyển hướng...</p>
  </div>
</body>
</html>"""


@app.route("/trip/<trip_id>", methods=["GET"])
def trip_share_page(trip_id):
    """
    Trang share link — trả HTML với OG tags đầy đủ.
    Crawler (Zalo/FB/Messenger) đọc OG tags.
    Browser thật sẽ bị redirect sang app React sau 0.8s.
    """
    from flask import Response

    trip = _trip_store.get(trip_id)
    meta = trip.get("meta", {}) if trip else {}

    location   = meta.get("location", "Điểm đến")
    days       = meta.get("days", 3)
    origin     = meta.get("origin", "")
    start_date = meta.get("startDate", "")

    title = f"🗺️ Lịch trình {days} ngày tại {location} – S-Trip"

    parts = [f"Hành trình {days} ngày {days - 1} đêm tại {location}"]
    if origin:
        parts.append(f"khởi hành từ {origin}")
    if start_date:
        parts.append(f"ngày {start_date}")
    description = " · ".join(parts) + ". Xem và tùy chỉnh lịch trình trên S-Trip!"

    # Ảnh OG — dùng ảnh tỉnh từ SerpAPI nếu có, fallback placeholder
    og_image = (
        f"{request.host_url.rstrip('/')}/api/og-image/{trip_id}"
    )

    current_url = request.url
    # URL app React (đổi thành domain thật khi deploy)
    app_url = f"http://localhost:3000/trip/{trip_id}"

    if not trip:
        title       = "S-Trip · AI Travel Planner"
        description = "Lên kế hoạch du lịch thông minh với AI. Tìm khách sạn, chuyến bay và điểm tham quan chỉ trong vài giây."
        og_image    = "https://placehold.co/1200x630/10b981/white?text=S-Trip"
        app_url     = "http://localhost:3000"

    html = _OG_TEMPLATE.format(
        title=title,
        description=description,
        url=current_url,
        image=og_image,
        app_url=app_url,
    )
    return Response(html, mimetype="text/html")


@app.route("/api/og-image/<trip_id>", methods=["GET"])
def og_image(trip_id):
    """
    Trả về ảnh 1200×630 cho OG tag.
    Thứ tự ưu tiên: ảnh tỉnh từ SerpAPI → placeholder đẹp.
    """
    from flask import Response
    import urllib.request

    trip = _trip_store.get(trip_id)
    meta = trip.get("meta", {}) if trip else {}
    location = meta.get("location", "")

    # Thử lấy ảnh tỉnh từ SerpAPI
    if location and SERPAPI_KEY:
        try:
            GoogleSearch = get_google_search()
            if GoogleSearch:
                res = GoogleSearch({
                    "engine": "google_images",
                    "q": f"du lịch {location} Việt Nam phong cảnh",
                    "api_key": SERPAPI_KEY,
                    "num": 1,
                }).get_dict()
                imgs = res.get("images_results", [])
                if imgs:
                    img_url = imgs[0].get("original") or imgs[0].get("thumbnail")
                    if img_url:
                        req = urllib.request.Request(
                            img_url,
                            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.google.com/"}
                        )
                        with urllib.request.urlopen(req, timeout=6) as r:
                            data = r.read()
                            ct   = r.headers.get("Content-Type", "image/jpeg")
                        return Response(data, content_type=ct)
        except Exception as e:
            print(f"[og-image] SerpAPI fallback: {e}")

    # Fallback: SVG placeholder 1200×630
    loc_display = location or "S-Trip"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#g)"/>
  <text x="600" y="260" font-family="Arial" font-size="80" font-weight="bold"
        fill="white" text-anchor="middle">✈️ S-Trip</text>
  <text x="600" y="360" font-family="Arial" font-size="48"
        fill="rgba(255,255,255,0.9)" text-anchor="middle">Ha trinh tai {loc_display}</text>
  <text x="600" y="430" font-family="Arial" font-size="28"
        fill="rgba(255,255,255,0.7)" text-anchor="middle">AI Travel Planner</text>
</svg>"""
    return Response(svg, content_type="image/svg+xml")



# ================================================================
# 🗺️  MAP HELPERS — trả URL nhúng map hoặc link mở Google Maps
# ================================================================

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

@app.route("/api/map-embed-url", methods=["GET"])
def map_embed_url():
    """
    Trả về URL dùng nhúng <iframe> Google Maps cho 1 địa điểm.

    Ưu tiên:
      1. place_id (ChIJ...)  → dùng Maps Embed API ?q=place_id:ChIJ...
      2. lat + lng           → dùng tọa độ
      3. name + location     → fallback tìm kiếm text

    Query params:
      place_id  — Google Places ID (ChIJ...)
      lat, lng  — tọa độ
      name      — tên địa điểm
      location  — tỉnh/thành (dùng kết hợp với name)
    """
    MAPS_KEY   = GOOGLE_MAPS_API_KEY
    place_id   = request.args.get("place_id", "").strip()
    lat        = request.args.get("lat", "").strip()
    lng        = request.args.get("lng", "").strip()
    name       = request.args.get("name", "").strip()
    location   = request.args.get("location", "").strip()

    # Trường hợp 1: có place_id chuẩn
    if place_id and not place_id.startswith("0x") and MAPS_KEY:
        embed = (
            f"https://www.google.com/maps/embed/v1/place"
            f"?key={MAPS_KEY}&q=place_id:{urllib.parse.quote(place_id)}&language=vi"
        )
        return jsonify({"success": True, "embed_url": embed, "source": "place_id"})

    # Trường hợp 2: có tọa độ
    if lat and lng and MAPS_KEY:
        label = urllib.parse.quote(name or location or "Địa điểm")
        embed = (
            f"https://www.google.com/maps/embed/v1/place"
            f"?key={MAPS_KEY}&q={label}&center={lat},{lng}&zoom=16&language=vi"
        )
        return jsonify({"success": True, "embed_url": embed, "source": "latlng"})

    # Trường hợp 3: fallback tìm kiếm text
    if (name or location) and MAPS_KEY:
        q = urllib.parse.quote(f"{name} {location}".strip())
        embed = (
            f"https://www.google.com/maps/embed/v1/search"
            f"?key={MAPS_KEY}&q={q}&language=vi"
        )
        return jsonify({"success": True, "embed_url": embed, "source": "search"})

    # Không có API key hoặc không đủ thông tin → trả link mở Maps thường
    if lat and lng:
        link = f"https://www.google.com/maps?q={lat},{lng}"
    elif name:
        link = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(name + ' ' + location)}"
    else:
        link = "https://www.google.com/maps"

    return jsonify({"success": False, "maps_link": link, "reason": "Thiếu GOOGLE_MAPS_API_KEY hoặc thiếu thông tin"})


@app.route("/api/static-map", methods=["GET"])
def static_map():
    """
    Trả URL ảnh bản đồ tĩnh (Static Maps API) cho thumbnail map.
    Dùng khi không muốn nhúng iframe.

    Query params: lat, lng, zoom (default 15), size (default 400x250)
    """
    lat  = request.args.get("lat", "")
    lng  = request.args.get("lng", "")
    zoom = request.args.get("zoom", "15")
    size = request.args.get("size", "400x250")
    MAPS_KEY = GOOGLE_MAPS_API_KEY

    if not lat or not lng:
        return jsonify({"success": False, "error": "Thiếu lat/lng"}), 400

    if not MAPS_KEY:
        # Fallback: ảnh tile OpenStreetMap (không cần key)
        osm_url = (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lng}&zoom={zoom}&size={size}&markers={lat},{lng}"
        )
        return jsonify({"success": True, "url": osm_url, "source": "osm"})

    url = (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat},{lng}&zoom={zoom}&size={size}"
        f"&markers=color:red%7C{lat},{lng}&key={MAPS_KEY}&language=vi"
    )
    return jsonify({"success": True, "url": url, "source": "google"})


# ================================================================
# 🔖 LƯU TRỮ ĐỊA ĐIỂM — /api/saved-places (Supabase)
# ================================================================
# Cài đặt: pip install supabase
# Thêm vào .env:
#   SUPABASE_URL=https://xxxx.supabase.co
#   SUPABASE_SERVICE_ROLE_KEY=eyJh...   <-- dùng service_role key (lấy tại Supabase → Settings → API → service_role)
#
# Tạo bảng trên Supabase (SQL Editor):
#   CREATE TABLE saved_places (
#       id         BIGSERIAL PRIMARY KEY,
#       user_id    TEXT      NOT NULL,
#       name       TEXT      NOT NULL,
#       location   TEXT      DEFAULT '',
#       rating     TEXT      DEFAULT '',
#       thumbnail  TEXT      DEFAULT '',
#       type       TEXT      DEFAULT 'default',
#       saved_at   BIGINT    DEFAULT EXTRACT(EPOCH FROM NOW())
#   );
#   CREATE INDEX idx_saved_places_user_id ON saved_places(user_id);
# ================================================================

from auth_routes import get_sb as _get_supabase_base

def _get_supabase(user_id=None):
    return _get_supabase_base(user_id)

def _sp_get_uid():
    from flask import session
    return session.get("user_id")


@app.route("/api/saved-places", methods=["GET"])
def saved_places_list():
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    try:
        sb = _get_supabase(uid)
        res = (
            sb.table("saved_places")
            .select("id, name, location, rating, thumbnail, type, saved_at")
            .eq("user_id", str(uid))
            .order("saved_at", desc=True)
            .execute()
        )
        places = res.data or []
        return jsonify({"success": True, "savedPlaces": places, "places": places})
    except Exception as e:
        print(f"[saved_places_list] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/saved-places", methods=["POST"])
def saved_places_add():
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    data     = request.get_json(force=True) or {}
    name     = (data.get("name",     "") or "").strip()
    location = (data.get("location", "") or "").strip()

    if not name:
        return jsonify({"success": False, "error": "Thiếu tên địa điểm"}), 400

    try:
        sb = _get_supabase(uid)

        # Kiểm tra đã lưu chưa
        check = (
            sb.table("saved_places")
            .select("id")
            .eq("user_id", str(uid))
            .eq("name", name)
            .eq("location", location)
            .execute()
        )
        if check.data:
            return jsonify({"success": True, "message": "Đã lưu trước đó", "id": check.data[0]["id"]})

        # Thêm mới
        insert_res = (
            sb.table("saved_places")
            .insert({
                "user_id":   str(uid),
                "name":      name,
                "location":  location,
                "rating":    str(data.get("rating",    "") or ""),
                "thumbnail": data.get("thumbnail", "") or "",
                "type":      data.get("type",      "default") or "default",
                "saved_at":  int(time.time()),
            })
            .execute()
        )
        new_id = insert_res.data[0]["id"] if insert_res.data else None
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        print(f"[saved_places_add] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/saved-places/check", methods=["GET"])
def saved_places_check():
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "isSaved": False})

    name     = request.args.get("name",     "").strip()
    location = request.args.get("location", "").strip()
    try:
        sb = _get_supabase(uid)
        res = (
            sb.table("saved_places")
            .select("id")
            .eq("user_id", str(uid))
            .eq("name", name)
            .eq("location", location)
            .execute()
        )
        return jsonify({"success": True, "isSaved": bool(res.data), "exists": bool(res.data)})
    except Exception as e:
        print(f"[saved_places_check] Lỗi: {e}")
        return jsonify({"success": False, "isSaved": False})


@app.route("/api/saved-places/remove-by-name", methods=["POST"])
def saved_places_remove_by_name():
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    data     = request.get_json(force=True) or {}
    name     = (data.get("name",     "") or "").strip()
    location = (data.get("location", "") or "").strip()

    try:
        sb = _get_supabase(uid)
        res = (
            sb.table("saved_places")
            .delete()
            .eq("user_id", str(uid))
            .eq("name", name)
            .eq("location", location)
            .execute()
        )
        removed = len(res.data) if res.data else 0
        return jsonify({"success": True, "removed": removed})
    except Exception as e:
        print(f"[saved_places_remove_by_name] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/saved-places/<int:place_id>", methods=["DELETE"])
def saved_places_delete(place_id):
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    try:
        sb = _get_supabase(uid)
        res = (
            sb.table("saved_places")
            .delete()
            .eq("user_id", str(uid))
            .eq("id", place_id)
            .execute()
        )
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy địa điểm"}), 404
        return jsonify({"success": True})
    except Exception as e:
        print(f"[saved_places_delete] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/saved-places/<int:place_id>", methods=["PUT"])
def saved_places_update(place_id):
    uid = _sp_get_uid()
    if not uid:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401

    data          = request.get_json(force=True) or {}
    new_thumbnail = data.get("thumbnail", "")

    try:
        sb = _get_supabase(uid)
        res = (
            sb.table("saved_places")
            .update({"thumbnail": to_proxy_url(new_thumbnail)})
            .eq("user_id", str(uid))
            .eq("id", place_id)
            .execute()
        )
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy địa điểm"}), 404
        return jsonify({"success": True, "message": "Đã cập nhật ảnh thành công"})
    except Exception as e:
        print(f"[saved_places_update] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)