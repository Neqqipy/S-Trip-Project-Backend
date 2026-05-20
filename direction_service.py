from serpapi import GoogleSearch

# Mapping chế độ di chuyển SerpAPI
TRAVEL_MODES = {
    "driving":  {"mode": "0", "label": "Ô tô",    "icon": "🚗"},
    "walking":  {"mode": "2", "label": "Đi bộ",   "icon": "🚶"},
    "cycling":  {"mode": "1", "label": "Xe đạp",  "icon": "🚲"},
    "transit":  {"mode": "3", "label": "Xe buýt", "icon": "🚌"},
}

# Ước tính xe máy dựa vào thời gian ô tô (×0.85) — SerpAPI không có mode xe máy
MOTORBIKE_FACTOR = 0.85


def get_directions_one_mode(api_key, origin, destination, mode_key):
    """Lấy chỉ đường 1 chế độ, trả về dict chuẩn."""
    meta = TRAVEL_MODES[mode_key]
    params = {
        "engine": "google_maps_directions",
        "start_addr": origin,
        "end_addr": destination,
        "travel_mode": meta["mode"],
        "hl": "vi",
        "api_key": api_key,
    }
    try:
        data = GoogleSearch(params).get_dict()
        routes = data.get("directions", [])
        if not routes:
            return None
        best = routes[0]
        return {
            "mode":     mode_key,
            "label":    meta["label"],
            "icon":     meta["icon"],
            "distance": best.get("distance", "N/A"),
            "duration": best.get("duration", "N/A"),
            "distance_m": _parse_meters(best.get("distance", "")),
            "duration_s": _parse_seconds(best.get("duration", "")),
        }
    except Exception as e:
        print(f"[Direction {mode_key}] Lỗi: {e}")
        return None


def get_all_modes_directions(api_key, origin, destination):
    """
    Lấy chỉ đường cho TẤT CẢ phương tiện: ô tô, xe máy, xe đạp, đi bộ, xe buýt.
    Xe máy được ước tính từ thời gian ô tô × 0.85.

    Trả về list các dict:
    [
      { mode, label, icon, distance, duration, distance_m, duration_s },
      ...
    ]
    """
    results = []

    # Ô tô — lấy trước để tính xe máy
    car = get_directions_one_mode(api_key, origin, destination, "driving")
    if car:
        results.append(car)

        # Xe máy — ước tính từ ô tô
        moto_s = int(car["duration_s"] * MOTORBIKE_FACTOR) if car["duration_s"] else None
        results.append({
            "mode":       "motorbike",
            "label":      "Xe máy",
            "icon":       "🏍️",
            "distance":   car["distance"],
            "duration":   _format_seconds(moto_s) if moto_s else car["duration"],
            "distance_m": car["distance_m"],
            "duration_s": moto_s,
            "estimated":  True,  # đánh dấu là ước tính
        })

    # Các mode còn lại
    for mode_key in ["cycling", "walking", "transit"]:
        r = get_directions_one_mode(api_key, origin, destination, mode_key)
        if r:
            results.append(r)

    return results


def get_route_legs_directions(api_key, markers):
    """
    Lấy thông tin di chuyển cho TOÀN BỘ lộ trình (nhiều điểm).
    markers: list of { name, lat, lng }
    Trả về list các leg:
    [
      {
        from: "Tên điểm A",
        to:   "Tên điểm B",
        modes: [ { mode, label, icon, distance, duration, ... }, ... ]
      },
      ...
    ]
    """
    legs = []
    for i in range(len(markers) - 1):
        a = markers[i]
        b = markers[i + 1]
        # Dùng tọa độ nếu có, fallback về tên
        origin      = f"{a['lat']},{a['lng']}" if a.get('lat') and a.get('lng') else a['name']
        destination = f"{b['lat']},{b['lng']}" if b.get('lat') and b.get('lng') else b['name']
        modes = get_all_modes_directions(api_key, origin, destination)
        legs.append({
            "from":  a.get("name", f"Điểm {i}"),
            "to":    b.get("name", f"Điểm {i+1}"),
            "modes": modes,
        })
    return legs


# ── Helpers ───────────────────────────────────────────────────

def _parse_meters(distance_str):
    """'1,2 km' → 1200 (int meters). '500 m' → 500."""
    if not distance_str:
        return 0
    s = str(distance_str).replace(",", ".").lower()  # Fix: SerpAPI đôi khi trả int
    try:
        if "km" in s:
            return int(float(s.replace("km", "").strip()) * 1000)
        elif "m" in s:
            return int(float(s.replace("m", "").strip()))
    except Exception:
        pass
    return 0


def _parse_seconds(duration_str):
    """'1 giờ 20 phút' → 4800 (int seconds). '25 phút' → 1500."""
    if not duration_str:
        return 0
    duration_str = str(duration_str)  # Fix: đảm bảo là string
    import re
    total = 0
    h = re.search(r'(\d+)\s*(giờ|h|hour)', duration_str, re.IGNORECASE)
    m = re.search(r'(\d+)\s*(phút|min|minute)', duration_str, re.IGNORECASE)
    if h:
        total += int(h.group(1)) * 3600
    if m:
        total += int(m.group(1)) * 60
    return total


def _format_seconds(total_s):
    """4800 → '1 giờ 20 phút'"""
    if not total_s:
        return "N/A"
    h = total_s // 3600
    m = (total_s % 3600) // 60
    if h > 0 and m > 0:
        return f"{h} giờ {m} phút"
    elif h > 0:
        return f"{h} giờ"
    else:
        return f"{m} phút"


def print_route_summary(data):
    """In kết quả thô từ 1 lần gọi SerpAPI"""
    if not data or "directions" not in data:
        print("Không tìm thấy dữ liệu đường đi.")
        return
    routes = data.get("directions", [])
    for i, route in enumerate(routes):
        print(f"=== Tuyến đường {i+1}: {route.get('title')} ===")
        print(f"📍 Từ: {data.get('search_parameters', {}).get('start_addr')}")
        print(f"🏁 Đến: {data.get('search_parameters', {}).get('end_addr')}")
        print(f"📏 Khoảng cách: {route.get('distance')}")
        print(f"⏱️ Thời gian: {route.get('duration')}")
        print("-" * 40)


def print_all_modes(legs):
    """In toàn bộ lộ trình với nhiều phương tiện"""
    for i, leg in enumerate(legs):
        print(f"\n{'='*50}")
        print(f"Chặng {i+1}: {leg['from']} → {leg['to']}")
        print(f"{'='*50}")
        for m in leg["modes"]:
            est = " (ước tính)" if m.get("estimated") else ""
            print(f"  {m['icon']} {m['label']:10s} | {m['distance']:>10s} | {m['duration']}{est}")