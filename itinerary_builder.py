"""
itinerary_builder.py
────────────────────
Xây dựng lịch trình theo ngày/buổi từ danh sách tours + foods đã được
ThuatToanDeXuat.py chấm điểm sẵn.

Ba vấn đề được giải quyết:
  1. Quán ăn KHÔNG quá xa cả tour trước lẫn tour sau
     → Dùng pick_food_for_slot() với midpoint giữa tour hiện tại và tour kế tiếp.
     → Food Sáng: midpoint(tour_Sáng, tour_Chiều)
     → Food Chiều: midpoint(tour_Chiều, tour_Tối hoặc None)
     → Food Tối: chọn theo buổi tối, không cần midpoint

  2. Phân bổ địa điểm theo thời gian hợp lý
     → Mỗi ngày có 3 slot: sáng / chiều / tối
     → Sáng & chiều: 1 tour + 1 food ghép theo midpoint
     → Tối: 1 quán ăn tối (chợ đêm / nhà hàng) + tour tối nếu có

  3. Không lặp quán ăn trong cùng 1 ngày
     → used_food_names_today reset mỗi ngày mới

Sơ đồ 1 ngày:
  🌅 Sáng  → tour_m + food gần midpoint(tour_m, tour_a)
  ☀️ Chiều → tour_a + food gần midpoint(tour_a, tour_e hoặc None)
  🌙 Tối   → [tour_e nếu có] + food_evening

Dữ liệu đầu vào:
  hotels  : list[dict]  — đã scored, phần tử [0] là khách sạn được chọn
  tours   : list[dict]  — đã sorted theo ai_score giảm dần, có 'best_time' + lat/lng
  foods   : list[dict]  — đã sorted theo ai_score giảm dần, có 'best_time' + lat/lng
  num_days: int

Dữ liệu đầu ra (thêm vào response /api/plan-trip):
  itinerary: list[dict] — mỗi phần tử là 1 ngày:
    {
      "day": 1,
      "slots": [
        {
          "slot":  "🌅 Buổi sáng",
          "items": [
            { ...tour fields..., "item_type": "tour" },
            { ...food fields..., "item_type": "food", "note": "Gần đây ~1.2 km" }
          ]
        },
        { "slot": "☀️ Buổi chiều", "items": [...] },
        { "slot": "🌙 Buổi tối",   "items": [...] },
      ]
    }
"""

from __future__ import annotations
import math
from typing import Optional
from ThuatToanDeXuat import pick_food_for_slot


# ─────────────────────────────────────────────────────────────────────────────
# Hằng số label — phải khớp với _SLOT_LABEL trong main.py
# ─────────────────────────────────────────────────────────────────────────────
SLOT_MORNING   = "🌅 Buổi sáng"
SLOT_AFTERNOON = "☀️ Buổi chiều"
SLOT_EVENING   = "🌙 Buổi tối"

# Số tour tối đa mỗi buổi (sáng + chiều)
TOURS_PER_SLOT = 1

# ─────────────────────────────────────────────────────────────────────────────
# Haversine — copy nhỏ gọn, tránh circular import với ThuatToanDeXuat
# ─────────────────────────────────────────────────────────────────────────────
def _dist(lat1, lon1, lat2, lon2) -> float:
    """Khoảng cách chim bay (km). Trả 9999 nếu thiếu tọa độ."""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return 9999.0
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
# ─────────────────────────────────────────────────────────────────────────────
# Đánh giá quy mô tour để quyết định có ghép thêm điểm không
# ─────────────────────────────────────────────────────────────────────────────
def is_big_tour(tour_name: str) -> bool:
    if not tour_name: return False
    name_lower = tour_name.lower()
    keywords = ["khu du lịch", "bà nà", "bana", "sun world", "vinpearl", "công viên", "safari", "núi", "đảo", "rừng", "quốc gia", "hills", "ngũ hành sơn", "sơn trà", "biển", "suối", "resort"]
    return any(kw in name_lower for kw in keywords)

# ─────────────────────────────────────────────────────────────────────────────
# Helper: chọn quán ăn gần midpoint giữa tour trước và tour sau
# ─────────────────────────────────────────────────────────────────────────────
def _pick_food_midpoint(
    prev_tour: Optional[dict],
    next_tour: Optional[dict],
    food_pool: list[dict],
    used_food_names: set,
    ideal_price: float = 100_000,
    preferred_slot: Optional[str] = None,
) -> Optional[dict]:
    """
    Chọn quán ăn nằm gần MIDPOINT giữa tour trước và tour sau.

    - Dùng pick_food_for_slot() từ ThuatToanDeXuat (midpoint + distance scoring).
    - Lọc thêm preferred_slot: ưu tiên quán có best_time phù hợp buổi.
    - used_food_names: set[str] tên quán đã dùng HÔM NAY → tránh lặp trong ngày.
    - Nếu tất cả đều đã dùng, bỏ filter để tránh trả None.
    """
    if not food_pool:
        return None

    # Thử chọn có filter buổi trước
    preferred = [
        f for f in food_pool
        if not preferred_slot or f.get("best_time") == preferred_slot
    ] or food_pool  # fallback toàn pool nếu không có quán phù hợp buổi

    results = pick_food_for_slot(
        preferred,
        prev_tour=prev_tour,
        next_tour=next_tour,
        ideal_price=ideal_price,
        used_names=used_food_names,
        top_k=1,
    )

    if results:
        return results[0]

    # Fallback: bỏ filter used_names (tránh trả None)
    results = pick_food_for_slot(
        food_pool,
        prev_tour=prev_tour,
        next_tour=next_tour,
        ideal_price=ideal_price,
        used_names=set(),
        top_k=1,
    )
    return results[0] if results else None


# ─────────────────────────────────────────────────────────────────────────────
# Tách pool tours theo best_time
# ─────────────────────────────────────────────────────────────────────────────
def _split_tours(tours: list[dict]) -> dict[str, list[dict]]:
    pools: dict[str, list[dict]] = {
        SLOT_MORNING:   [],
        SLOT_AFTERNOON: [],
        SLOT_EVENING:   [],   # tour ban đêm (ít gặp, nhưng có: chợ đêm, bar...)
    }
    for t in tours:
        slot = t.get("best_time", SLOT_AFTERNOON)
        if slot not in pools:
            slot = SLOT_AFTERNOON
        pools[slot].append(t)
    return pools


# ─────────────────────────────────────────────────────────────────────────────
# Hàm chính
# ─────────────────────────────────────────────────────────────────────────────
def build_itinerary(
    hotels:   list[dict],
    tours:    list[dict],
    foods:    list[dict],
    num_days: int,
    ideal_price: float = 100_000,
) -> list[dict]:
    """
    Trả về danh sách ngày, mỗi ngày gồm 3 slot (sáng/chiều/tối).
    Mỗi slot có list items (tour + food ghép theo midpoint).

    Gọi sau apply_recommendation_algorithm() để tours/foods đã sorted.

    Food được chọn theo midpoint giữa tour hiện tại và tour kế tiếp:
      - Food Sáng  → midpoint(tour_Sáng,  tour_Chiều)
      - Food Chiều → midpoint(tour_Chiều, tour_Tối)   [tour_Tối có thể None]
      - Food Tối   → gần tour_Tối nếu có, hoặc chọn theo best_time=evening

    used_food_names reset mỗi ngày để tránh lặp quán trong cùng 1 ngày,
    nhưng cho phép tái sử dụng quán ngon qua các ngày khác nhau.
    """
    if not tours and not foods:
        return []

    num_days = max(1, num_days)

    # Deep-copy nhẹ để không mutate list gốc
    tour_pools = _split_tours([dict(t) for t in tours])
    all_foods  = [dict(f) for f in foods]   # pool toàn bộ, không chia theo buổi

   used_tour_names: set = set()
    used_food_names: set = set()  # Đưa hẳn ra ngoài để KHÔNG lặp lại quán ngon giữa các ngày
    
    hotel_lat, hotel_lng = None, None
    if hotels:
        hotel_lat = float(hotels[0].get("lat", 0) or 0)
        hotel_lng = float(hotels[0].get("lng", 0) or 0)
    def _next_tour(slot_key: str, curr_lat: float, curr_lng: float, peek: bool = False) -> Optional[dict]:
        """Lấy tour chưa dùng từ slot đúng. Kiểm tra khoảng cách đường chim bay <= 13km"""
        for try_slot in [slot_key, SLOT_MORNING, SLOT_AFTERNOON, SLOT_EVENING]:
            pool = tour_pools.get(try_slot, [])
            for t in pool:
                name = t.get("name")
                if name not in used_tour_names:
                    # Kiểm tra khoảng cách di chuyển từ điểm hiện tại
                    if curr_lat is not None and curr_lng is not None:
                        d = _dist(curr_lat, curr_lng, t.get("lat"), t.get("lng"))
                        if d > 13: continue
                    if not peek:
                        used_tour_names.add(name)
                    return t
        return None

    itinerary = []

    for day_num in range(1, num_days + 1):
        slots = []
        
        # Bắt đầu ngày mới từ khách sạn
        curr_lat, curr_lng = hotel_lat, hotel_lng

        def update_curr(item):
            nonlocal curr_lat, curr_lng
            if item and item.get("lat") and item.get("lng"):
                curr_lat = float(item["lat"])
                curr_lng = float(item["lng"])

        skip_afternoon = False

        # ── SÁNG ───────────────────
        tour_m = _next_tour(SLOT_MORNING, curr_lat, curr_lng)
        morning_items = []
        if tour_m:
            tour_m["item_type"] = "tour"
            morning_items.append(tour_m)
            update_curr(tour_m)

            if is_big_tour(tour_m.get("name")):
                skip_afternoon = True
                tour_m["note"] = "Dành trọn thời gian (Sáng & Chiều)"
            else:
                # Lọc food <= 13km chim bay từ điểm hiện tại (~20km lái xe)
                nearby_foods = [f for f in all_foods if curr_lat is None or _dist(curr_lat, curr_lng, f.get("lat"), f.get("lng")) <= 13]
                peek_tour_a = _next_tour(SLOT_AFTERNOON, curr_lat, curr_lng, peek=True)
                
                food_m = _pick_food_midpoint(
                    prev_tour=tour_m,
                    next_tour=peek_tour_a,
                    food_pool=nearby_foods,
                    used_food_names=used_food_names,
                    ideal_price=ideal_price,
                    preferred_slot=SLOT_MORNING,
                )
                if food_m:
                    km = _dist(tour_m.get("lat"), tour_m.get("lng"), food_m.get("lat"), food_m.get("lng"))
                    food_m["item_type"] = "food"
                    food_m["note"] = f"Gần đây ~{km:.1f} km" if km < 9999 else "Gần khu vực"
                    morning_items.append(food_m)
                    used_food_names.add(food_m.get("name", ""))
                    update_curr(food_m)

        if morning_items:
            slots.append({"slot": SLOT_MORNING, "items": morning_items})

        # ── CHIỀU ──────────────────
        afternoon_items = []
        if not skip_afternoon:
            tour_a = _next_tour(SLOT_AFTERNOON, curr_lat, curr_lng)
            if tour_a:
                tour_a["item_type"] = "tour"
                afternoon_items.append(tour_a)
                update_curr(tour_a)

                if is_big_tour(tour_a.get("name")):
                    tour_a["note"] = "Dành trọn thời gian Chiều"
                else:
                    nearby_foods = [f for f in all_foods if curr_lat is None or _dist(curr_lat, curr_lng, f.get("lat"), f.get("lng")) <= 13]
                    peek_tour_e = _next_tour(SLOT_EVENING, curr_lat, curr_lng, peek=True)
                    
                    food_a = _pick_food_midpoint(
                        prev_tour=tour_a,
                        next_tour=peek_tour_e,
                        food_pool=nearby_foods,
                        used_food_names=used_food_names,
                        ideal_price=ideal_price,
                        preferred_slot=SLOT_AFTERNOON,
                    )
                    if food_a:
                        km = _dist(tour_a.get("lat"), tour_a.get("lng"), food_a.get("lat"), food_a.get("lng"))
                        food_a["item_type"] = "food"
                        food_a["note"] = f"Gần đây ~{km:.1f} km" if km < 9999 else "Gần khu vực"
                        afternoon_items.append(food_a)
                        used_food_names.add(food_a.get("name", ""))
                        update_curr(food_a)

        if afternoon_items:
            slots.append({"slot": SLOT_AFTERNOON, "items": afternoon_items})

        # ── TỐI ────────────────────────────────────
        tour_e = _next_tour(SLOT_EVENING, curr_lat, curr_lng)
        evening_items = []
        if tour_e:
            tour_e["item_type"] = "tour"
            evening_items.append(tour_e)
            update_curr(tour_e)

        nearby_foods = [f for f in all_foods if curr_lat is None or _dist(curr_lat, curr_lng, f.get("lat"), f.get("lng")) <= 13]
        food_e = _pick_food_midpoint(
            prev_tour=tour_e,
            next_tour=None,
            food_pool=nearby_foods,
            used_food_names=used_food_names,
            ideal_price=ideal_price,
            preferred_slot=SLOT_EVENING,
        )
        if food_e:
            food_e["item_type"] = "food"
            food_e.pop("note", None)
            evening_items.append(food_e)
            used_food_names.add(food_e.get("name", ""))
            update_curr(food_e)

        if evening_items:
            slots.append({"slot": SLOT_EVENING, "items": evening_items})

        itinerary.append({"day": day_num, "slots": slots})

    return itinerary


# ─────────────────────────────────────────────────────────────────────────────
# Tích hợp vào plan_trip response — gọi từ main.py
# ─────────────────────────────────────────────────────────────────────────────
def attach_itinerary(plan: dict, num_days: int) -> dict:
    """
    Nhận `plan` dict (chứa hotels/tours/foods) sau apply_recommendation_algorithm,
    thêm key 'itinerary' vào và trả về plan đã mở rộng.

    Dùng thay cho việc gọi build_itinerary thủ công trong main.py:

        from itinerary_builder import attach_itinerary
        plan = attach_itinerary(plan, num_days)
    """
    hotels = plan.get("hotels", [])
    tours  = plan.get("tours",  [])
    foods  = plan.get("foods",  [])

    plan["itinerary"] = build_itinerary(hotels, tours, foods, num_days)
    return plan
