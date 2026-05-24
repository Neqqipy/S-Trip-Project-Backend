import math
import re

# ---------------------------------------------------------------------------
# Trọng số & hằng số toàn cục
# ---------------------------------------------------------------------------
W_DISTANCE = 0.5
W_PRICE    = 0.15
W_RATING   = 0.35

W_HOTEL_QUALITY = 0.55   # trọng số chất lượng (Bayesian rating) cho khách sạn
W_HOTEL_PRICE   = 0.45   # trọng số giá phù hợp ngân sách

# Ngưỡng giá sàn: khách sạn rẻ hơn X% ngân sách/đêm bị coi là "phèn"
PRICE_FLOOR_RATIO = 0.25   # dưới 25% max_per_night → điểm giá = 0

MIN_REVIEWS       = 50
SYSTEM_AVG_RATING = 4.2
MAX_DISTANCE_KM   = 30


# ---------------------------------------------------------------------------
# Hàm tiện ích
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    """Tính khoảng cách đường chim bay (km) giữa 2 tọa độ."""
   if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return 999.0
    R = 6371
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi       = math.radians(float(lat2) - float(lat1))
    dlambda    = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bayesian_rating(r, v):
    """
    Bayesian Rating — kéo rating về trung bình hệ thống khi số review thấp.
    Giúp tránh địa điểm 5★ chỉ có 3 lượt đánh giá chiếm top.
    """
    try:
        r, v = float(r), int(v)
    except Exception:
        r, v = 4.0, MIN_REVIEWS
    return (v / (v + MIN_REVIEWS)) * r + (MIN_REVIEWS / (v + MIN_REVIEWS)) * SYSTEM_AVG_RATING


def extract_price(price_str, default_price):
    """Trích xuất số nguyên đầu tiên từ chuỗi giá (VD: '350,000đ' → 350000)."""
    if not price_str or price_str == "Giá tùy chọn":
        return default_price
    nums = re.findall(r'\d+', str(price_str).replace('.', '').replace(',', ''))
    return int(nums[0]) if nums else default_price


# ---------------------------------------------------------------------------
# Scoring — Tours & Foods  (dùng khoảng cách tới khách sạn làm trung tâm)
# ---------------------------------------------------------------------------

def _score_activity(item, center_lat, center_lng, ideal_price, default_price):
    """Chấm điểm 1 item tour/food theo 3 tiêu chí: rating, khoảng cách, giá."""
    r_score = (bayesian_rating(item.get("rating", 4.0), item.get("reviews", MIN_REVIEWS)) / 5.0) * 10

    dist    = haversine(center_lat, center_lng, item.get("lat"), item.get("lng"))
    d_score = max(0, 10 - (dist / MAX_DISTANCE_KM) * 10)

    price   = extract_price(item.get("price"), default_price)
    if price <= ideal_price:
        p_score = 10
    else:
        p_score = max(0, 10 - ((price - ideal_price) / 100_000 * 2.5))

    return (d_score * W_DISTANCE) + (p_score * W_PRICE) + (r_score * W_RATING)


# ---------------------------------------------------------------------------
# Scoring — Hotels
# ---------------------------------------------------------------------------

def score_hotels(hotels, total_hotel_budget, num_nights, top_k=5):
    """
    Chấm điểm và chọn top_k khách sạn:
      1. Bayesian quality score (55%)
      2. Price-fit score (45%) — ưu tiên giá sát ngân sách:
         - Dưới sàn (< 25% max/đêm): price_score = 0  → tránh chọn "phèn"
         - Trong khoảng [sàn, max]:  price_score tỉ lệ thuận với giá (gần max = tốt)
         - Vượt ngân sách:           price_score = 0  → loại khỏi pool chính

    Fallback: nếu pool ideal rỗng, bổ sung rẻ nhất vào đủ top_k
              (hơn là trả về danh sách trống).

    Args:
        hotels            : list[dict] từ SerpAPI (có price_per_night, rating, reviews)
        total_hotel_budget: tổng ngân sách phần khách sạn (VND)
        num_nights        : số đêm
        top_k             : số khách sạn trả về

    Returns:
        list[dict] — đã gắn 'score', 'price_tier'; sắp xếp điểm cao → thấp
    """
    if not hotels:
        return []

    max_per_night   = total_hotel_budget / max(num_nights, 1)
    floor_per_night = max_per_night * PRICE_FLOOR_RATIO   # giá sàn "không phèn"
    scored = []

    for h in hotels:
        price   = h.get("price_per_night", 0)
        rating  = h.get("rating", 0)
        reviews = h.get("reviews", 0)

        if price <= 0:
            continue

        b_rating      = bayesian_rating(rating, reviews)
        quality_score = (b_rating / 5.0) * 10

        if price > max_per_night:
            # Vượt ngân sách → đánh dấu nhưng vẫn score để dùng fallback sau
            price_score = 0
            h['price_tier'] = 'over_budget'
        elif price < floor_per_night:
            # Quá rẻ so với khả năng chi → coi là "phèn", price_score = 0
            price_score = 0
            h['price_tier'] = 'too_cheap'
        else:
            # Trong khoảng lý tưởng: càng sát max càng tốt (tận dụng ngân sách)
            price_score = ((price - floor_per_night) / (max_per_night - floor_per_night)) * 10
            h['price_tier'] = 'ideal'

        h['score'] = round((quality_score * W_HOTEL_QUALITY) + (price_score * W_HOTEL_PRICE), 4)
        scored.append(h)

    if not scored:
        return []

    # Pool chính: giá trong khoảng lý tưởng
    ideal_pool = [h for h in scored if h.get('price_tier') == 'ideal']
    ideal_pool.sort(key=lambda x: x['score'], reverse=True)

    if len(ideal_pool) >= top_k:
        return ideal_pool[:top_k]

    # Fallback: bổ sung "too_cheap" (ưu tiên rating cao) rồi "over_budget" (rẻ nhất)
    result = ideal_pool[:]
    needed = top_k - len(result)

    cheap_pool = sorted(
        [h for h in scored if h.get('price_tier') == 'too_cheap'],
        key=lambda x: x['score'], reverse=True
    )
    result += cheap_pool[:needed]
    needed = top_k - len(result)

    if needed > 0:
        over_pool = sorted(
            [h for h in scored if h.get('price_tier') == 'over_budget'],
            key=lambda x: x.get('price_per_night', float('inf'))
        )
        result += over_pool[:needed]

    return result[:top_k]


# ---------------------------------------------------------------------------
# Hàm điều phối chính — Tours & Foods
# ---------------------------------------------------------------------------

def _centroid(items: list[dict]) -> tuple[float | None, float | None]:
    """Tính trung tâm địa lý (trung bình lat/lng) của danh sách địa điểm có tọa độ."""
    pts = [(float(i["lat"]), float(i["lng"])) for i in items
           if i.get("lat") and i.get("lng")]
    if not pts:
        return None, None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def pick_food_for_slot(
    foods: list[dict],
    prev_tour: dict | None,
    next_tour: dict | None,
    ideal_price: float,
    used_names: set | None = None,
    top_k: int = 1,
) -> list[dict]:
    """
    Chọn quán ăn phù hợp nhất cho 1 slot dựa trên khoảng cách tới
    tour TRƯỚC và tour SAU (midpoint), tránh dùng lại quán đã chọn.

    Logic:
      - Tính midpoint giữa prev_tour và next_tour làm "điểm lý tưởng"
        → quán ăn nằm giữa 2 tour sẽ không làm du khách đi lòng vòng.
      - Nếu chỉ có 1 tour (slot đầu hoặc cuối), dùng tọa độ tour đó.
      - Nếu không có tour nào có tọa độ, fallback về ai_score đã tính sẵn.
      - used_names: set tên quán đã dùng trong ngày → tránh lặp.

    Args:
        foods       : toàn bộ pool quán ăn (đã có ai_score từ apply_recommendation_algorithm)
        prev_tour   : tour cùng buổi (VD: tour Sáng khi chọn food Sáng)
        next_tour   : tour buổi kế tiếp (VD: tour Chiều khi chọn food Sáng)
        ideal_price : giá mục tiêu (VND)
        used_names  : set[str] tên quán đã dùng hôm đó, sẽ bị bỏ qua
        top_k       : số quán trả về (mặc định 1)

    Returns:
        list[dict] — tối đa top_k quán ăn phù hợp nhất, không trùng used_names.
    """
    if not foods:
        return []

    used = used_names or set()

    # Tính midpoint giữa 2 tour để làm gốc đánh giá khoảng cách
    lats, lngs = [], []
    for t in [prev_tour, next_tour]:
        if t and t.get("lat") and t.get("lng"):
            lats.append(float(t["lat"]))
            lngs.append(float(t["lng"]))

    if lats:
        mid_lat = sum(lats) / len(lats)
        mid_lng = sum(lngs) / len(lngs)
    else:
        # Không có tọa độ tour → sort theo ai_score có sẵn
        candidates = [f for f in foods if f.get("name") not in used]
        return candidates[:top_k] if candidates else foods[:top_k]

    # Chấm lại điểm cho từng quán theo midpoint của 2 tour
    scored = []
    for f in foods:
        if f.get("name") in used:
            continue
        slot_score = _score_activity(f, mid_lat, mid_lng, ideal_price, 150_000)
        scored.append((slot_score, f))

    if not scored:
        # Tất cả đã dùng → fallback không lọc used
        scored = [(_score_activity(f, mid_lat, mid_lng, ideal_price, 150_000), f) for f in foods]

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]


def apply_recommendation_algorithm(hotels, tours, foods, budget):
    """
    Chấm điểm tours & foods theo rating + khoảng cách + giá, sắp xếp điểm cao xuống thấp.

    Trung tâm tham chiếu:
      - Tours → trung tâm khách sạn (hotel[0])
      - Foods → centroid top-10 tours (pre-sort nhanh cho pool)
        Lưu ý: đây chỉ là sort SƠ BỘ cho toàn pool.
        Khi build itinerary, dùng pick_food_for_slot() để chọn food
        CHÍNH XÁC theo midpoint giữa tour trước + tour sau của từng slot.

    Việc tối ưu thứ tự đi lại theo ngày/buổi được xử lý bởi itinerary_builder.py.
    """
    hotel_lat   = float(hotels[0].get("lat", 0) or 0)
    hotel_lng   = float(hotels[0].get("lng", 0) or 0)
    ideal_price = (budget * 0.2) / 3
    # Chấm tours theo khoảng cách tới khách sạn (điểm xuất phát mỗi ngày)
    # Ngưỡng 13km chim bay ≈ 20km đường bộ (hệ số ~1.5x)
    MAX_KM = 13
    valid_tours = []
    for t in tours:
        dist = haversine(hotel_lat, hotel_lng, t.get("lat"), t.get("lng"))
        if dist <= MAX_KM:
            t['ai_score'] = round(
                _score_activity(t, hotel_lat, hotel_lng, ideal_price, 100_000), 4
            )
            valid_tours.append(t)
    
    valid_tours.sort(key=lambda x: x.get('ai_score', 0), reverse=True)
    tours = valid_tours
    # ... (lấy trung tâm tour) ...
    valid_foods = []
    for f in foods:
        dist_hotel = haversine(hotel_lat, hotel_lng, f.get("lat"), f.get("lng"))
        if dist_hotel <= MAX_KM:
            f['ai_score'] = round(
                _score_activity(f, tour_center_lat, tour_center_lng, ideal_price, 150_000), 4
            )
            valid_foods.append(f)
            
    valid_foods.sort(key=lambda x: x.get('ai_score', 0), reverse=True)
    foods = valid_foods

    return hotels, tours, foods
