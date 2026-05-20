from serpapi import GoogleSearch
from datetime import datetime, timedelta
import os
import json

# Scoring và MMR tập trung ở ThuatToanDeXuat
from ThuatToanDeXuat import score_hotels, haversine

GOOGLE_IMG_DOMAINS = (
    "googleusercontent.com", "ggpht.com",
    "googleapis.com", "googleapi",
)

# --- CACHE ẢNH: tránh gọi lại SerpAPI cho cùng khách sạn ---
IMG_CACHE_FILE = "hotel_img_cache.json"

def _load_img_cache():
    if os.path.exists(IMG_CACHE_FILE):
        try:
            with open(IMG_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_img_cache(cache):
    try:
        with open(IMG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CACHE] Không lưu được cache ảnh: {e}")


def is_expiring_url(url):
    """
    URL dạng googleusercontent.com/proxy/... expire rất nhanh, không dùng được.
    Lọc bỏ trước khi trả về frontend.
    """
    if not url:
        return True
    bad_patterns = [
        "googleusercontent.com/proxy/",  # Google proxy URL — expire ngay
        "encrypted-tbn",                  # Google thumbnail nhỏ, chất lượng thấp
    ]
    return any(p in url for p in bad_patterns)


def to_proxy_url(url, base=None):
    """
    Wrap URL ảnh Google thành proxy endpoint để tránh expire/hotlink block.
    - Nếu set env API_BASE_URL → dùng URL production (khi deploy)
    - Nếu không có env → trả thẳng URL gốc (tránh lỗi localhost khi dev)
    """
    if not url:
        return url

    if base is None:
        base = os.environ.get("API_BASE_URL", "")

    if base and any(d in url for d in GOOGLE_IMG_DOMAINS):
        import urllib.parse
        return f"{base}/api/proxy-image?url={urllib.parse.quote(url, safe='')}"

    return url


def _get_review_image(place_id, api_key):
    """
    Tầng 3: Lấy ảnh từ review của khách sạn.
    Ảnh review (r.get('images')) là URL ổn định, không expire như thumbnail Maps.
    """
    if not place_id:
        return None
    try:
        data = GoogleSearch({
            "engine": "google_maps_reviews",
            "place_id": place_id,
            "hl": "vi",
            "api_key": api_key,
        }).get_dict()
        for review in data.get("reviews", []):
            images = review.get("images", [])
            if images:
                img = images[0].get("thumbnail") or images[0].get("image")
                if img:
                    return img
    except Exception:
        pass
    return None


def get_hotel_image_fallback(hotel_name, location, api_key):
    """
    Tìm ảnh thật theo 3 tầng, có cache để tránh gọi SerpAPI lặp lại:
      1. Google Images — nhanh, thường có kết quả
      2. Google Maps Photos — ảnh chính thức của khách sạn
      3. Ảnh từ Review — URL ổn định, không expire (fallback cuối)
    Trả về None chỉ khi cả 3 nguồn đều thất bại.
    """
    cache_key = f"{hotel_name}|{location}"
    cache = _load_img_cache()

    # Cache hit → trả ngay, không gọi API
    if cache_key in cache:
        print(f"[CACHE HIT] Ảnh khách sạn: {hotel_name}")
        return cache[cache_key]

    img = None
    found_data_id = None

    # --- Tầng 1: Google Images ---
    try:
        res = GoogleSearch({
            "engine": "google_images",
            "q": f"{hotel_name} {location} exterior photo",
            "api_key": api_key,
        }).get_dict()
        images = res.get("images_results", [])
        for im in images:
            candidate = im.get("original") or im.get("thumbnail")
            if candidate and not is_expiring_url(candidate):
                img = candidate
                print(f"[T1 OK] {hotel_name} → {img}")
                break
        if not img:
            print(f"[T1 FAIL] {hotel_name} → không tìm được URL hợp lệ")
    except Exception as e:
        print(f"[T1 ERR] {hotel_name} → {e}")

    # --- Tầng 2: Google Maps Photos (chỉ gọi nếu tầng 1 thất bại) ---
    if not img:
        try:
            maps_res = GoogleSearch({
                "engine": "google_maps",
                "q": f"{hotel_name} {location}",
                "hl": "vi",
                "api_key": api_key,
            }).get_dict()

            found_data_id = (
                maps_res.get("place_results", {}).get("data_id")
                or next(
                    (r.get("data_id") for r in maps_res.get("local_results", []) if r.get("data_id")),
                    None,
                )
            )
            print(f"[T2] {hotel_name} → data_id: {found_data_id}")

            if found_data_id:
                photos_res = GoogleSearch({
                    "engine": "google_maps_photos",
                    "data_id": found_data_id,
                    "hl": "vi",
                    "api_key": api_key,
                }).get_dict()
                photos = photos_res.get("photos", [])
                if photos:
                    img = photos[0].get("image") or photos[0].get("thumbnail")
                    print(f"[T2 OK] {hotel_name} → {img}")
                else:
                    print(f"[T2 FAIL] {hotel_name} → không có photos")
        except Exception as e:
            print(f"[T2 ERR] {hotel_name} → {e}")

    # --- Tầng 3: Ảnh từ Review (URL ổn định, không expire) ---
    if not img and found_data_id:
        img = _get_review_image(found_data_id, api_key)
        if img:
            print(f"[T3 OK] {hotel_name} → {img}")
        else:
            print(f"[T3 FAIL] {hotel_name} → không có ảnh review")

    # Lưu cache dù img là None → lần sau không gọi lại nữa
    cache[cache_key] = img
    _save_img_cache(cache)
    print(f"[CACHE SAVE] {hotel_name} → {img or 'không có ảnh'}")

    return img


def _parse_hotel(h, location, api_key, num_nights, passengers):
    """
    Chuẩn hoá 1 entry từ SerpAPI thành dict nhất quán.
    Trả về None nếu không lấy được giá.
    """
    rate  = h.get("rate_per_night", {})
    price = rate.get("extracted_lowest") or rate.get("extracted_before_taxes_fees") or 0
    if price <= 0:
        return None

    # --- Ảnh: thử nhiều nguồn theo thứ tự ưu tiên ---
    img = h.get("thumbnail") or h.get("featured_image")
    if not img and h.get("images"):
        first = h["images"][0]
        img = first.get("thumbnail") if isinstance(first, dict) else first
    # FIX: Lọc bỏ URL dạng googleusercontent.com/proxy/ — expire ngay lập tức
    if is_expiring_url(img):
        img = None
    if not img:
        img = get_hotel_image_fallback(h.get("name"), location, api_key)
    # Kiểm tra thêm lần nữa sau fallback
    if is_expiring_url(img):
        img = None

    coords = h.get("gps_coordinates", {})
    lat = coords.get("latitude")
    lng = coords.get("longitude")

    # Fix 1: Luôn đảm bảo có place_id ngay từ lần render đầu tiên.
    # - Nếu thiếu tọa độ: gọi fallback để lấy cả (lat, lng, place_id) cùng lúc.
    # - Nếu có tọa độ nhưng Google Hotels không trả place_id: gọi fallback chỉ để lấy place_id,
    #   giữ nguyên lat/lng gốc (chính xác hơn) — frontend có place_id ngay, không cần đổi hotel.
    native_place_id = h.get("place_id") or h.get("data_id") or ""
    fallback_place_id = ""
    if not lat or not lng:
        lat, lng, fallback_place_id = get_hotel_coords_fallback(h.get("name"), location, api_key)
    elif not native_place_id:
        _, _, fallback_place_id = get_hotel_coords_fallback(h.get("name"), location, api_key)

    desc = h.get("description", "").lower()
    name = h.get("name", "").lower()

    amenities = [a.lower() for a in h.get("amenities", [])]
    amenities_text = " ".join(amenities)

    full_info = f"{name} {desc} {amenities_text}"

    room_type = None

    if any(word in full_info for word in ["2 giường đơn", "twin", "2 single beds"]):
        room_type = "Phòng 2 Giường Đơn"
    elif any(word in full_info for word in ["giường đôi", "double bed", "queen bed", "king bed"]):
        room_type = "Phòng Giường Đôi"
    elif any(word in full_info for word in ["villa", "nguyên căn", "apartment"]):
        room_type = "Nguyên căn / Villa"
    elif "family" in full_info or "gia đình" in full_info:
        room_type = "Phòng Family"
    elif "dorm" in full_info or "tập thể" in full_info:
        room_type = "Phòng Dorm / Tập thể"

    if not room_type:
        if passengers == 1: room_type = "Phòng Đơn"
        elif passengers == 2: room_type = "Phòng Đôi / 2 Phòng Đơn"
        else: room_type = "Phòng tiêu chuẩn"

    # --- Tự build nhận xét ngắn từ data thật ---
    raw_desc  = h.get("description", "").strip()
    amenities = h.get("amenities", [])

    # Highlight tiện ích nổi bật (tối đa 3)
    HIGHLIGHT_KEYWORDS = {
        "hồ bơi": "hồ bơi", "pool": "hồ bơi",
        "bãi biển": "bãi biển riêng", "beach": "bãi biển riêng",
        "spa": "spa", "gym": "gym / fitness",
        "bữa sáng": "bao gồm bữa sáng", "breakfast": "bao gồm bữa sáng",
        "đưa đón": "đưa đón sân bay", "airport": "đưa đón sân bay",
        "wifi": "wifi miễn phí", "bar": "bar / rooftop",
        "nhà hàng": "nhà hàng tại chỗ", "restaurant": "nhà hàng tại chỗ",
        "view biển": "view biển", "ocean view": "view biển",
    }
    highlights = []
    amenities_joined = " ".join(a.lower() for a in amenities)
    for kw, label in HIGHLIGHT_KEYWORDS.items():
        if kw in amenities_joined and label not in highlights:
            highlights.append(label)
        if len(highlights) == 3:
            break

    if raw_desc and len(raw_desc) > 20:
        short_desc = raw_desc[:120].rstrip() + ("..." if len(raw_desc) > 120 else "")
    elif highlights:
        short_desc = "Tiện ích: " + " · ".join(highlights) + "."
    else:
        rating_val = h.get("overall_rating", 0) or 0
        if   rating_val >= 4.8: short_desc = "Được đánh giá xuất sắc bởi du khách."
        elif rating_val >= 4.5: short_desc = "Đánh giá rất tốt từ khách lưu trú."
        elif rating_val >= 4.0: short_desc = "Khách sạn chất lượng tốt, phù hợp lưu trú."
        else:                   short_desc = "Lựa chọn hợp lý trong tầm ngân sách."

    return {
        "name":            h.get("name"),
        "rating":          h.get("overall_rating", 0),
        "reviews":         h.get("reviews", 0),
        "price_per_night": price,
        "total_price":     price * num_nights,
        "desc":            short_desc,
        # FIX: chỉ wrap proxy khi có ảnh thật — placeholder không bao giờ đi qua proxy
        "thumbnail":       to_proxy_url(img) if img else "https://placehold.co/400x300?text=S-Trip+Hotel",
        "link":            h.get("link"),
        "room_type":       room_type,
        "lat":             lat,
        "lng":             lng,
        "place_id":        native_place_id or fallback_place_id or "",
    }


# ---------------------------------------------------------------------------
# 📍 LỌC KHÁCH SẠN THEO TRUNG TÂM THỰC TẾ CỦA CÁC ĐỊA ĐIỂM THAM QUAN / ĂN UỐNG
# ---------------------------------------------------------------------------

def _get_center_from_activities(tours=None, foods=None):
    """
    Tính trung bình tọa độ của tất cả tours + foods có lat/lng.
    Đây là 'trung tâm thực tế' — nơi tập trung địa điểm du lịch trong chuyến đi,
    chính xác hơn nhiều so với tọa độ hành chính của tỉnh.

    Trả về (lat, lng) hoặc None nếu không đủ điểm (< 3).
    """
    points = []
    for item in (tours or []) + (foods or []):
        lat = item.get("lat")
        lng = item.get("lng")
        if lat and lng:
            try:
                points.append((float(lat), float(lng)))
            except (ValueError, TypeError):
                continue

    if len(points) < 3:
        print(f"[CENTER] Chỉ có {len(points)} điểm tham quan/ăn uống — chưa đủ để tính trung tâm")
        return None

    center_lat = sum(p[0] for p in points) / len(points)
    center_lng = sum(p[1] for p in points) / len(points)
    print(f"[CENTER] Tính từ {len(points)} địa điểm tours+foods → ({center_lat:.4f}, {center_lng:.4f})")
    return center_lat, center_lng


def _get_location_center_nominatim(location):
    """
    Fallback: dùng Nominatim (OpenStreetMap) để geocode tên tỉnh/thành.
    Không tốn API quota, nhưng kém chính xác hơn trung tâm hoạt động.
    Trả về (lat, lng) hoặc None nếu lỗi.
    """
    import urllib.request, urllib.parse, json as _json
    try:
        q   = urllib.parse.quote_plus(f"{location}, Vietnam")
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1&countrycodes=vn"
        req = urllib.request.Request(url, headers={"User-Agent": "STrip-App/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        if data:
            lat = float(data[0]["lat"])
            lng = float(data[0]["lon"])
            print(f"[CENTER] Nominatim fallback '{location}' → ({lat:.4f}, {lng:.4f})")
            return lat, lng
    except Exception as e:
        print(f"[CENTER] Nominatim lỗi cho '{location}': {e}")
    return None


def filter_hotels_in_bounds(hotels, location, max_km=10, tours=None, foods=None):
    """
    Lọc bỏ khách sạn nằm quá xa khu vực du lịch thực tế.

    Thứ tự ưu tiên khi tính 'trung tâm':
      1. Trung bình tọa độ các tours + foods (chính xác nhất — phản ánh nơi khách thực sự đến)
      2. Geocode tên tỉnh qua Nominatim (fallback khi tours/foods chưa đủ)
      3. Bỏ qua lọc nếu không tính được trung tâm

    Rules:
      - Hotel không có tọa độ → giữ lại (để frontend geocode sau)
      - Lọc với radius max_km; nếu còn < 3 → tự động nới rộng lên max_km * 2
      - Sau khi nới vẫn không đủ → sort theo khoảng cách, trả top gần nhất
        (thay vì trả nguyên list gốc không liên quan)
    """
    if not hotels:
        return hotels

    # Ưu tiên 1: trung tâm từ địa điểm thực tế
    center = _get_center_from_activities(tours, foods)

    # Ưu tiên 2: geocode tỉnh qua Nominatim
    if not center:
        center = _get_location_center_nominatim(location)

    if not center:
        print(f"[filter_hotels] Không xác định được trung tâm — bỏ qua lọc.")
        return hotels

    clat, clng = center

    def _dist(h):
        lat, lng = h.get("lat"), h.get("lng")
        if lat is None or lng is None:
            return None
        try:
            return haversine(clat, clng, float(lat), float(lng))
        except Exception:
            return None

    def _apply_radius(radius):
        result = []
        for h in hotels:
            d = _dist(h)
            if d is None:
                # Không có tọa độ → giữ lại, frontend tự geocode
                result.append(h)
            elif d <= radius:
                result.append(h)
            else:
                print(f"[filter_hotels] Bỏ '{h.get('name', '?')}' — cách trung tâm {d:.1f}km (>{radius}km)")
        return result

    # Gán dist_to_center cho từng hotel (dùng trong score_hotels để ưu tiên gần trung tâm)
    for h in hotels:
        d = _dist(h)
        h["dist_to_center"] = round(d, 3) if d is not None else None

    # --- Vòng 1: lọc với radius gốc ---
    filtered = _apply_radius(max_km)
    print(f"[filter_hotels] {len(filtered)}/{len(hotels)} hotel trong phạm vi {max_km}km.")

    # FIX 2: Adaptive radius — nới rộng gấp đôi nếu còn < 3 kết quả có tọa độ
    hotels_with_coords = [h for h in filtered if h.get("lat") is not None]
    if len(hotels_with_coords) < 3:
        expanded_km = max_km * 2
        print(f"[filter_hotels] Chỉ còn {len(hotels_with_coords)} hotel có tọa độ — nới rộng lên {expanded_km}km.")
        filtered = _apply_radius(expanded_km)
        print(f"[filter_hotels] Sau nới rộng: {len(filtered)}/{len(hotels)} hotel trong phạm vi {expanded_km}km.")

    # FIX 3: Fallback thông minh — sort theo khoảng cách thay vì trả nguyên list gốc
    if not filtered:
        print(f"[filter_hotels] Lọc hết sạch → fallback sort theo khoảng cách gần nhất.")
        def sort_key(h):
            d = _dist(h)
            return d if d is not None else float("inf")
        sorted_hotels = sorted(hotels, key=sort_key)
        top = sorted_hotels[:10]
        nearest_dist = _dist(top[0]) if top else None
        print(f"[filter_hotels] Trả {len(top)} hotel gần nhất (gần nhất: {nearest_dist:.1f}km)." if nearest_dist else f"[filter_hotels] Trả {len(top)} hotel.")
        return top

    return filtered


def get_smart_hotel_recommendations(api_key, location, total_hotel_budget,
                                    num_days, passengers, departure_date=None,
                                    tours=None, foods=None):
    """
    Lấy danh sách khách sạn từ SerpAPI, parse, lọc theo khu vực thực tế,
    rồi uỷ toàn bộ việc chấm điểm + chọn lọc cho `score_hotels()`.

    Args:
        tours, foods: list địa điểm đã fetch — dùng để tính trung tâm thực tế,
                      thay vì geocode tên tỉnh (tránh lệch như Quảng Nam → Tam Kỳ)

    Returns:
        list[dict] — top 5 khách sạn, đã có trường 'score', sắp xếp điểm cao xuống thấp
    """
    num_nights = max(num_days - 1, 1)

    try:
        check_in = datetime.strptime(departure_date, "%Y-%m-%d")
    except Exception:
        check_in = datetime.today() + timedelta(days=14)
    check_out = check_in + timedelta(days=num_nights)

    # Tính ngưỡng giá sàn để truyền vào SerpAPI — loại hostel/nhà nghỉ từ đầu
    # Sàn = 25% ngân sách/đêm, tối thiểu 200k để tránh dorm
    max_per_night   = total_hotel_budget / max(num_nights, 1)
    floor_per_night = max(int(max_per_night * 0.25), 200_000)

    params = {
        "engine":          "google_hotels",
        "q":               f"Hotels in {location}, Vietnam",
        "check_in_date":   check_in.strftime("%Y-%m-%d"),
        "check_out_date":  check_out.strftime("%Y-%m-%d"),
        "adults":          passengers,
        "currency":        "VND",
        "hl":              "vi",
        "gl":              "vn",                    # GEO: giới hạn kết quả Việt Nam
        "location":        f"{location}, Vietnam",  # GEO: bias địa lý đúng tỉnh/thành
        "min_price":       floor_per_night,         # PRICE: loại hostel/nhà nghỉ từ SerpAPI
        "num":             20,                      # POOL: lấy nhiều hơn để score_hotels có đủ lựa chọn
        "api_key":         api_key,
    }
    print(f"[hotels] Tìm tại '{location}' | ngân sách/đêm: {max_per_night:,.0f}đ | sàn giá: {floor_per_night:,.0f}đ")

    try:
        raw_hotels = GoogleSearch(params).get_dict().get("properties", [])
    except Exception as e:
        print(f"Lỗi Hotel SerpAPI: {e}")
        return []

    # Parse — bỏ entry không có giá
    parsed = [
        h for h in (
            _parse_hotel(raw, location, api_key, num_nights, passengers)
            for raw in raw_hotels
        )
        if h is not None
    ]

    # ✅ Lọc theo trung tâm thực tế (tours+foods) thay vì trung tâm hành chính tỉnh
    parsed = filter_hotels_in_bounds(parsed, location, max_km=10, tours=tours, foods=foods)

    # Fix 2: Tính proximity blend TRƯỚC khi score_hotels để max_dist chuẩn hoá
    # trên toàn bộ pool (không phải top-5), tránh skew khi top-5 đều gần nhau.
    center = _get_center_from_activities(tours, foods)
    if not center:
        center = _get_location_center_nominatim(location)

    if center and parsed:
        clat, clng = center
        # max_dist tính trên toàn pool — đảm bảo proximity_bonus luôn trong [0, 0.3]
        all_dists = [h.get("dist_to_center") for h in parsed if h.get("dist_to_center") is not None]
        max_dist = max(all_dists) if all_dists else 1
        if max_dist == 0:
            max_dist = 1
        for h in parsed:
            d = h.get("dist_to_center")
            if d is not None:
                h["proximity_bonus"] = round((1 - d / max_dist) * 0.3, 4)   # 0..0.3
            else:
                h["proximity_bonus"] = 0.0
        print(f"[hotels] Proximity blend sẵn sàng | max_dist={max_dist:.2f}km | pool={len(parsed)}")

    # Uỷ scoring cho ThuatToanDeXuat
    scored = score_hotels(parsed, total_hotel_budget, num_nights, top_k=5)

    # Áp blend: score_cuối = score_gốc × 0.7 + proximity_bonus × 0.3
    if center and scored:
        for h in scored:
            bonus = h.get("proximity_bonus", 0.0)
            h["score"] = round(h.get("score", 0) * 0.7 + bonus, 4)
            if h.get("dist_to_center") is not None:
                h["dist_to_center_km"] = round(h["dist_to_center"], 2)
        scored.sort(key=lambda h: -h.get("score", 0))
        print(f"[hotels] Sau blend proximity: top={scored[0].get('name')} score={scored[0].get('score')}")

    return scored


def get_hotel_coords_fallback(hotel_name, location, api_key):
    """
    Tìm tọa độ thật + place_id từ Google Local nếu Google Hotels không trả về.
    Trả về (lat, lng, place_id).
    """
    params = {
        "engine": "google_local",
        "q": f"{hotel_name} tại {location}",
        "location": "Vietnam",
        "hl": "vi",
        "api_key": api_key
    }
    try:
        res = GoogleSearch(params).get_dict()
        local_results = res.get("local_results", [])
        if local_results:
            r      = local_results[0]
            coords = r.get("gps_coordinates", {})
            lat    = coords.get("latitude")
            lng    = coords.get("longitude")
            pid    = r.get("place_id") or r.get("data_id") or ""
            print(f"[coords_fallback] {hotel_name} → ({lat}, {lng}) place_id={pid}")
            return lat, lng, pid
    except Exception as e:
        print(f"Lỗi fallback tọa độ cho {hotel_name}: {e}")
    return None, None, ""