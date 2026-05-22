from serpapi import GoogleSearch
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 🗺️ MAP TÊN TỈNH CŨ (63) → TÊN TỈNH MỚI (34) — hiệu lực từ 12/6/2025
# Dùng để chuẩn hoá input từ frontend trước khi resolve sân bay.
# Tỉnh nào không có trong map = không bị sáp nhập → giữ nguyên tên.
# ---------------------------------------------------------------------------
PROVINCE_MERGE_MAP: dict[str, str] = {
    # ── Miền Bắc ──────────────────────────────────────────────────────────
    "Hà Giang":         "Tuyên Quang",      # Hà Giang + Tuyên Quang → Tuyên Quang
    "Yên Bái":          "Lào Cai",          # Yên Bái + Lào Cai → Lào Cai
    "Bắc Kạn":          "Thái Nguyên",      # Bắc Kạn + Thái Nguyên → Thái Nguyên
    "Vĩnh Phúc":        "Phú Thọ",          # Vĩnh Phúc + Phú Thọ → Phú Thọ
    "Bắc Giang":        "Hòa Bình",         # Bắc Giang + Hòa Bình → Hòa Bình
    "Hải Dương":        "Hải Phòng",        # Hải Dương + Hải Phòng → Hải Phòng
    "Thái Bình":        "Hải Phòng",        # Thái Bình + Hải Phòng → Hải Phòng
    "Hưng Yên":         "Hà Nội",           # Hưng Yên + Hà Nội → Hà Nội
    "Bắc Ninh":         "Hà Nội",           # Bắc Ninh + Hà Nội → Hà Nội
    "Hà Nam":           "Ninh Bình",        # Hà Nam + Ninh Bình → Ninh Bình
    "Nam Định":         "Ninh Bình",        # Nam Định + Ninh Bình → Ninh Bình
    # ── Miền Trung ────────────────────────────────────────────────────────
    "Quảng Bình":       "Quảng Trị",        # Quảng Bình + Quảng Trị → Quảng Trị
    "Quảng Nam":        "Đà Nẵng",          # ✅ Quảng Nam → Đà Nẵng (DAD)
    "Kon Tum":          "Quảng Ngãi",       # Kon Tum + Quảng Ngãi → Quảng Ngãi
    "Bình Định":        "Gia Lai",          # Bình Định + Gia Lai → Gia Lai
    "Phú Yên":          "Đắk Lắk",          # Phú Yên + Đắk Lắk → Đắk Lắk
    "Ninh Thuận":       "Khánh Hòa",        # Ninh Thuận + Khánh Hòa → Khánh Hòa
    # ── Miền Nam ──────────────────────────────────────────────────────────
    "Bà Rịa - Vũng Tàu":  "TP. Hồ Chí Minh",  # ✅ BR-VT → SGN
    "Bà Rịa–Vũng Tàu":    "TP. Hồ Chí Minh",  # alias dấu gạch ngang khác
    "Bà Rịa Vũng Tàu":    "TP. Hồ Chí Minh",  # alias không dấu ngăn cách
    "Vũng Tàu":            "TP. Hồ Chí Minh",  # tên thành phố phổ biến
    "Bình Dương":          "TP. Hồ Chí Minh",  # ✅ Bình Dương → SGN
    "Bình Phước":          "Đồng Nai",          # Bình Phước + Đồng Nai → Đồng Nai
    "Long An":             "Tây Ninh",          # Long An + Tây Ninh → Tây Ninh
    "Đắk Nông":            "Đắk Lắk",           # Đắk Nông + Đắk Lắk → Đắk Lắk
    "Hậu Giang":           "Cần Thơ",           # Hậu Giang + Cần Thơ → Cần Thơ
    "Sóc Trăng":           "Cần Thơ",           # Sóc Trăng + Cần Thơ → Cần Thơ
    "Tiền Giang":          "Bến Tre",           # Tiền Giang + Bến Tre + Vĩnh Long → Bến Tre
    "Vĩnh Long":           "Bến Tre",
    "Trà Vinh":            "Đồng Tháp",         # Trà Vinh + Đồng Tháp → Đồng Tháp
    "An Giang":            "Kiên Giang",        # An Giang + Kiên Giang → Kiên Giang
    "Bạc Liêu":            "Cà Mau",            # Bạc Liêu + Cà Mau → Cà Mau
}


def normalize_province(name: str) -> str:
    """
    Chuẩn hoá tên tỉnh cũ (63 tỉnh) → tên tỉnh mới (34 tỉnh).
    Hiệu lực từ 12/6/2025 theo Nghị quyết Quốc hội.

    - Nếu có trong PROVINCE_MERGE_MAP → trả tên tỉnh mới (tỉnh sáp nhập).
    - Nếu không có → giữ nguyên (tỉnh không bị sáp nhập hoặc đã là tên mới).
    """
    return PROVINCE_MERGE_MAP.get(name.strip(), name.strip())


# ---------------------------------------------------------------------------
# 🗺️ BẢNG IATA ĐẦY ĐỦ CÁC SÂN BAY VIỆT NAM (22 thành phố)
# ---------------------------------------------------------------------------
CITY_TO_IATA = {
    # Miền Bắc
    "Hà Nội": "HAN",
    "Điện Biên Phủ": "DIN",
    "Nà Sản": "SQH",          # Sơn La
    "Đồng Hới": "VDH",        # Quảng Bình (nay thuộc Quảng Trị)
    # Miền Trung
    "Huế": "HUI",
    "Thừa Thiên Huế": "HUI",
    "Thừa Thiên - Huế": "HUI",
    "Đà Nẵng": "DAD",
    "Chu Lai": "VCL",         # Quảng Nam / Tam Kỳ (nay thuộc Đà Nẵng)
    "Quy Nhơn": "UIH",
    "Tuy Hòa": "TBB",         # Phú Yên (nay thuộc Đắk Lắk)
    "Buôn Ma Thuột": "BMV",
    "Pleiku": "PXU",
    "Nha Trang": "CXR",
    "Đà Lạt": "DLI",
    "Phan Thiết": "PHH",       # Bình Thuận
    # Miền Nam
    "TP. Hồ Chí Minh": "SGN",
    "Hồ Chí Minh": "SGN",
    "Sài Gòn": "SGN",
    "Cần Thơ": "VCA",
    "Rạch Giá": "VKG",
    "Cà Mau": "CAH",
    "Côn Đảo": "VCS",
    "Phú Quốc": "PQC",
}

# ---------------------------------------------------------------------------
# 🔀 THÀNH PHỐ KHÔNG CÓ SÂN BAY → GỢI Ý THAY THẾ
# ---------------------------------------------------------------------------
_NO_AIRPORT_NEAREST = {
    # Tây Bắc
    "Sapa":        ("HAN", "Hà Nội", "Sapa không có sân bay. Bay vào Hà Nội (HAN) rồi đi xe khoảng 4–5 giờ."),
    "Lai Châu":    ("HAN", "Hà Nội", "Lai Châu không có sân bay. Bay vào Hà Nội (HAN) rồi di chuyển tiếp."),
    "Hà Giang":    ("HAN", "Hà Nội", "Hà Giang (nay thuộc Tuyên Quang) không có sân bay. Bay vào Hà Nội (HAN) rồi đi xe khoảng 5–6 giờ."),
    "Cao Bằng":    ("HAN", "Hà Nội", "Cao Bằng không có sân bay. Bay vào Hà Nội (HAN) rồi di chuyển ~6 giờ xe."),
    "Lạng Sơn":    ("HAN", "Hà Nội", "Lạng Sơn không có sân bay. Bay vào Hà Nội (HAN) rồi đi xe ~2 giờ."),
    "Bắc Ninh":    ("HAN", "Hà Nội", "Bắc Ninh (nay thuộc Hà Nội) không có sân bay riêng. Bay vào Hà Nội (HAN) rồi đi xe ~30 phút."),
    # Đông Bắc / Vịnh Hạ Long
    "Hạ Long":     ("HAN", "Hà Nội", "Hạ Long không có sân bay dân dụng thương mại. Bay vào Hà Nội (HAN) rồi đi xe ~2.5 giờ."),
    "Quảng Ninh":  ("HAN", "Hà Nội", "Quảng Ninh không có chuyến bay thương mại. Bay vào Hà Nội (HAN) rồi di chuyển tiếp."),
    # Bắc Trung Bộ
    "Vinh":        ("VII", "Vinh",   "Vinh có sân bay Vinh (VII)."),
    "Hà Tĩnh":     ("VII", "Vinh",   "Hà Tĩnh không có sân bay. Bay vào Vinh (VII) rồi di chuyển tiếp."),
    "Quảng Trị":   ("HUI", "Huế",    "Quảng Trị (nay sáp nhập thêm Quảng Bình) không có sân bay. Bay vào Huế (HUI) rồi đi xe ~1 giờ."),
    # Nam Trung Bộ
    "Hội An":      ("DAD", "Đà Nẵng","Hội An không có sân bay. Bay vào Đà Nẵng (DAD) rồi đi xe ~30 phút."),
    "Mỹ Sơn":      ("DAD", "Đà Nẵng","Mỹ Sơn không có sân bay. Bay vào Đà Nẵng (DAD)."),
    "Phan Rang":    ("CXR", "Nha Trang","Phan Rang (nay thuộc Khánh Hòa) không có sân bay. Sân bay Cam Ranh (CXR) gần nhất ~1 giờ."),
    "Ninh Thuận":   ("CXR", "Nha Trang","Ninh Thuận (nay thuộc Khánh Hòa) không có sân bay. Bay vào Nha Trang (CXR)."),
    # Tây Nguyên
    "Kon Tum":     ("PXU", "Pleiku", "Kon Tum (nay thuộc Quảng Ngãi) không có sân bay. Bay vào Pleiku (PXU) rồi đi xe ~50 phút."),
    "Gia Lai":     ("PXU", "Pleiku", "Gia Lai (nay sáp nhập thêm Bình Định) không có sân bay riêng. Bay vào Pleiku (PXU)."),
    "Đắk Nông":    ("BMV", "Buôn Ma Thuột","Đắk Nông (nay thuộc Đắk Lắk) không có sân bay. Bay vào Buôn Ma Thuột (BMV) rồi di chuyển tiếp."),
    # Đông Nam Bộ
    "Bà Rịa - Vũng Tàu": ("SGN", "TP. Hồ Chí Minh","Bà Rịa - Vũng Tàu (nay thuộc TP.HCM) không có sân bay dân dụng. Bay vào TP.HCM (SGN) rồi đi xe/tàu cao tốc ~2 giờ."),
    "Bà Rịa–Vũng Tàu":   ("SGN", "TP. Hồ Chí Minh","Bà Rịa - Vũng Tàu (nay thuộc TP.HCM) không có sân bay dân dụng. Bay vào TP.HCM (SGN)."),
    "Vũng Tàu":    ("SGN", "TP. Hồ Chí Minh","Vũng Tàu (nay thuộc TP.HCM) không có sân bay dân dụng. Bay vào TP.HCM (SGN) rồi đi xe/tàu cao tốc ~2 giờ."),
    "Bà Rịa":      ("SGN", "TP. Hồ Chí Minh","Bà Rịa không có sân bay. Bay vào TP.HCM (SGN) rồi di chuyển tiếp."),
    "Bình Dương":  ("SGN", "TP. Hồ Chí Minh","Bình Dương (nay thuộc TP.HCM) không có sân bay. Bay vào TP.HCM (SGN) rồi đi xe ~40 phút."),
    "Đồng Nai":    ("SGN", "TP. Hồ Chí Minh","Đồng Nai không có sân bay. Bay vào TP.HCM (SGN)."),
    "Tây Ninh":    ("SGN", "TP. Hồ Chí Minh","Tây Ninh không có sân bay. Bay vào TP.HCM (SGN) rồi đi xe ~2 giờ."),
    # Đồng bằng sông Cửu Long
    "Mỹ Tho":      ("SGN", "TP. Hồ Chí Minh","Mỹ Tho không có sân bay. Bay vào TP.HCM (SGN) rồi đi xe ~1.5 giờ."),
    "Bến Tre":     ("SGN", "TP. Hồ Chí Minh","Bến Tre không có sân bay. Bay vào TP.HCM (SGN) rồi đi xe ~2 giờ."),
    "Vĩnh Long":   ("VCA", "Cần Thơ","Vĩnh Long (nay thuộc Bến Tre) không có sân bay. Bay vào Cần Thơ (VCA) rồi đi xe ~30 phút."),
    "Sóc Trăng":   ("VCA", "Cần Thơ","Sóc Trăng (nay thuộc Cần Thơ) không có sân bay dân dụng. Bay vào Cần Thơ (VCA) rồi đi xe ~1 giờ."),
    "Bạc Liêu":    ("CAH", "Cà Mau", "Bạc Liêu (nay thuộc Cà Mau) không có sân bay. Sân bay Cà Mau (CAH) gần nhất."),
    "Kiên Giang":  ("PQC", "Phú Quốc","Kiên Giang: Bay vào Phú Quốc (PQC) hoặc Rạch Giá (VKG)."),
    "Long An":     ("SGN", "TP. Hồ Chí Minh","Long An (nay thuộc Tây Ninh) không có sân bay. Bay vào TP.HCM (SGN)."),
    "Tiền Giang":  ("SGN", "TP. Hồ Chí Minh","Tiền Giang (nay thuộc Bến Tre) không có sân bay. Bay vào TP.HCM (SGN) rồi đi xe ~1.5 giờ."),
}

# Thêm biến thể tên không dấu / alias thường gặp
_ALIAS = {
    "ho chi minh": "SGN", "hcm": "SGN", "tphcm": "SGN", "saigon": "SGN",
    "hanoi": "HAN", "ha noi": "HAN",
    "da nang": "DAD", "danang": "DAD",
    "nha trang": "CXR", "khanh hoa": "CXR", "khánh hòa": "CXR",
    "da lat": "DLI", "dalat": "DLI", "lam dong": "DLI", "lâm đồng": "DLI",
    "hue": "HUI", "thua thien hue": "HUI", "thừa thiên huế": "HUI",
    "phu quoc": "PQC", "phú quốc": "PQC",
    "can tho": "VCA", "cần thơ": "VCA",
    "quy nhon": "UIH", "binh dinh": "UIH", "bình định": "UIH",
    "buon ma thuot": "BMV", "ban me thuot": "BMV",
    "pleiku": "PXU", "gia lai": "PXU",
    "con dao": "VCS", "côn đảo": "VCS",
    "rach gia": "VKG", "rạch giá": "VKG",
    "ca mau": "CAH", "cà mau": "CAH",
    "vinh": "VII", "nghệ an": "VII", "nghe an": "VII",
    "dong hoi": "VDH", "quảng bình": "VDH", "quang binh": "VDH",
    "chu lai": "VCL", "tam ky": "VCL", "hội an": "DAD",
    "tuyhoa": "TBB", "tuy hoa": "TBB", "phú yên": "TBB", "phu yen": "TBB",
    "dien bien": "DIN", "điện biên": "DIN",
    "phan thiet": "PHH", "bình thuận": "PHH",
    # ── Tên tỉnh mới (34 tỉnh) — alias bổ sung sau sáp nhập 12/6/2025 ──
    "quảng nam": "DAD",         # Quảng Nam → Đà Nẵng
    "quang nam": "DAD",
    "bà rịa vũng tàu": "SGN",   # BR-VT → TP.HCM
    "ba ria vung tau": "SGN",
    "bình dương": "SGN",        # Bình Dương → TP.HCM
    "binh duong": "SGN",
    "đắk nông": "BMV",          # Đắk Nông → Buôn Ma Thuột (Đắk Lắk)
    "dak nong": "BMV",
    "ninh thuận": "CXR",        # Ninh Thuận → Khánh Hòa
    "ninh thuan": "CXR",
    "kon tum": "PXU",           # Kon Tum → Quảng Ngãi (sân bay gần nhất là Pleiku)
    "bình định": "UIH",         # Bình Định → Gia Lai (sân bay Quy Nhơn vẫn hoạt động)
    "binh dinh": "UIH",
    "phú yên": "TBB",           # Phú Yên → Đắk Lắk (sân bay Tuy Hòa vẫn hoạt động)
    "phu yen": "TBB",
    "quảng bình": "VDH",        # Quảng Bình → Quảng Trị (sân bay Đồng Hới vẫn hoạt động)
    "quang binh": "VDH",
}


# ---------------------------------------------------------------------------
# ✈️ BẢNG TUYẾN BAY THỰC TẾ TẠI VIỆT NAM (chỉ các tuyến có khai thác thương mại)
# ---------------------------------------------------------------------------
_OPERATED_ROUTES: set[frozenset] = {
    # Hub SGN (TP.HCM)
    frozenset({"SGN", "HAN"}), frozenset({"SGN", "DAD"}), frozenset({"SGN", "HUI"}),
    frozenset({"SGN", "CXR"}), frozenset({"SGN", "DLI"}), frozenset({"SGN", "PQC"}),
    frozenset({"SGN", "VCA"}), frozenset({"SGN", "VCS"}), frozenset({"SGN", "BMV"}),
    frozenset({"SGN", "PXU"}), frozenset({"SGN", "UIH"}), frozenset({"SGN", "VDH"}),
    frozenset({"SGN", "VII"}), frozenset({"SGN", "VCL"}), frozenset({"SGN", "TBB"}),
    frozenset({"SGN", "DIN"}), frozenset({"SGN", "VKG"}), frozenset({"SGN", "CAH"}),
    frozenset({"SGN", "PHH"}),
    # Hub HAN (Hà Nội)
    frozenset({"HAN", "DAD"}), frozenset({"HAN", "HUI"}), frozenset({"HAN", "CXR"}),
    frozenset({"HAN", "DLI"}), frozenset({"HAN", "PQC"}), frozenset({"HAN", "VCA"}),
    frozenset({"HAN", "BMV"}), frozenset({"HAN", "PXU"}), frozenset({"HAN", "UIH"}),
    frozenset({"HAN", "VDH"}), frozenset({"HAN", "VII"}), frozenset({"HAN", "VCL"}),
    frozenset({"HAN", "TBB"}), frozenset({"HAN", "DIN"}), frozenset({"HAN", "VKG"}),
    frozenset({"HAN", "CAH"}), frozenset({"HAN", "VCS"}),
    # Hub DAD (Đà Nẵng)
    frozenset({"DAD", "CXR"}), frozenset({"DAD", "PQC"}), frozenset({"DAD", "HUI"}),
    frozenset({"DAD", "VII"}), frozenset({"DAD", "UIH"}), frozenset({"DAD", "VCA"}),
    frozenset({"DAD", "BMV"}), frozenset({"DAD", "DIN"}), frozenset({"DAD", "VDH"}),
    # Hub HUI (Huế)
    frozenset({"HUI", "SGN"}), frozenset({"HUI", "HAN"}),
    # Tuyến nội vùng còn thiếu
    frozenset({"CXR", "HAN"}), frozenset({"CXR", "SGN"}),
    frozenset({"VCA", "HAN"}), frozenset({"VCA", "DAD"}), frozenset({"VCA", "SGN"}),
    frozenset({"UIH", "SGN"}), frozenset({"UIH", "HAN"}), frozenset({"UIH", "DAD"}),
    frozenset({"TBB", "SGN"}), frozenset({"TBB", "HAN"}),
    frozenset({"VCL", "SGN"}), frozenset({"VCL", "HAN"}), frozenset({"VCL", "DAD"}),
    frozenset({"BMV", "SGN"}), frozenset({"BMV", "HAN"}), frozenset({"BMV", "DAD"}),
    frozenset({"PXU", "SGN"}), frozenset({"PXU", "HAN"}),
    frozenset({"DLI", "SGN"}), frozenset({"DLI", "HAN"}),
    frozenset({"VDH", "SGN"}), frozenset({"VDH", "HAN"}),
    frozenset({"VII", "SGN"}), frozenset({"VII", "HAN"}),
    frozenset({"VCS", "SGN"}), frozenset({"VCS", "HAN"}),
    frozenset({"PQC", "HAN"}), frozenset({"PQC", "SGN"}),
    frozenset({"CAH", "SGN"}), frozenset({"CAH", "HAN"}),
    frozenset({"VKG", "SGN"}), frozenset({"VKG", "HAN"}),
    frozenset({"DIN", "HAN"}),
}

def is_route_operated(iata_a: str, iata_b: str) -> bool:
    """Trả True nếu tuyến bay này có khai thác thương mại thực tế."""
    if not iata_a or not iata_b:
        return False
    return frozenset({iata_a.upper(), iata_b.upper()}) in _OPERATED_ROUTES

# ---------------------------------------------------------------------------
# 🔀 MAPPING SÂN BAY NHỎ → HUB LỚN
# ---------------------------------------------------------------------------
_IATA_HUB_CANDIDATES: dict[str, list[str]] = {
    # Miền Nam
    "CAH": ["VCA", "SGN"],          # Cà Mau → Cần Thơ hoặc SGN
    "VCA": ["SGN", "HAN"],
    "VKG": ["PQC", "SGN"],          # Rạch Giá → Phú Quốc hoặc SGN
    "PQC": ["SGN", "HAN"],
    # Miền Trung - Nam
    "PHH": ["SGN", "HAN"],
    "DLI": ["SGN", "HAN"],
    "BMV": ["SGN", "HAN", "DAD"],
    "PXU": ["SGN", "HAN", "DAD"],
    "UIH": ["SGN", "DAD", "HAN"],
    "TBB": ["CXR", "SGN", "HAN"],   # Tuy Hòa → Nha Trang (CXR) gần hơn
    "VCL": ["DAD", "SGN", "HAN"],   # Chu Lai → Đà Nẵng
    # Miền Bắc
    "DIN": ["HAN"],
    "SQH": ["HAN"],
    "VDH": ["HUI", "HAN", "DAD"],   # Đồng Hới → Huế hoặc HAN
    "VII": ["HAN", "DAD"],
}

# Giữ lại để không break import cũ từ main.py
IATA_TO_HUB: dict[str, str] = {k: v[0] for k, v in _IATA_HUB_CANDIDATES.items()}


def get_effective_iata(iata: str, dest_iata: str | None = None) -> str:
    """
    Trả về IATA thực sự dùng để tìm vé máy bay, xét cả hướng đi.

    Logic:
    1. Nếu sân bay hiện tại CÓ tuyến bay trực tiếp đến dest → dùng luôn.
    2. Nếu không → thử lần lượt các hub ưu tiên, chọn hub đầu tiên
       có tuyến trực tiếp đến dest (hoặc ít nhất là hub lớn nhất).
    3. Nếu không có trong _IATA_HUB_CANDIDATES → trả nguyên iata.
    """
    if not iata:
        return iata

    candidates = _IATA_HUB_CANDIDATES.get(iata.upper())
    if not candidates:
        return iata

    if dest_iata and is_route_operated(iata, dest_iata):
        return iata

    if dest_iata:
        for hub in candidates:
            if is_route_operated(hub, dest_iata):
                return hub

    return candidates[0]


# ---------------------------------------------------------------------------
# ✈️ TỈNH SÁP NHẬP NHƯNG VẪN GIỮ SÂN BAY RIÊNG ĐANG KHAI THÁC VÀ FIX CHO TỈNH KHÔNG CÓ SÂN BAY
# ---------------------------------------------------------------------------
_KEEP_LOCAL_AIRPORT: dict[str, dict] = {
    # Tên tỉnh cũ (lowercase)  → {iata, airport_city, no_airport, note}
    # ── CÓ SÂN BAY RIÊNG VẪN ĐANG KHAI THÁC ───────────────────────────────
    "quảng nam": {
        "iata": "VCL",
        "airport_city": "Chu Lai (Quảng Nam)",
        "no_airport": False,
        "note": "Quảng Nam (nay thuộc Đà Nẵng) vẫn có sân bay Chu Lai (VCL) đang khai thác. "
                "Nếu không có chuyến VCL, có thể bay vào Đà Nẵng (DAD) rồi di chuyển ~1 giờ.",
    },
    "tam kỳ": {
        "iata": "VCL",
        "airport_city": "Chu Lai (Quảng Nam)",
        "no_airport": False,
        "note": "Tam Kỳ gần sân bay Chu Lai (VCL) nhất. Bay vào VCL rồi đi xe ~30 phút.",
    },
    "quảng bình": {
        "iata": "VDH",
        "airport_city": "Đồng Hới (Quảng Bình)",
        "no_airport": False,
        "note": "Quảng Bình (nay thuộc Quảng Trị) vẫn có sân bay Đồng Hới (VDH) đang khai thác.",
    },
    "đồng hới": {
        "iata": "VDH",
        "airport_city": "Đồng Hới (Quảng Bình)",
        "no_airport": False,
        "note": "Sân bay Đồng Hới (VDH) đang khai thác.",
    },
    "bình định": {
        "iata": "UIH",
        "airport_city": "Quy Nhơn (Bình Định)",
        "no_airport": False,
        "note": "Bình Định (nay thuộc Gia Lai) vẫn có sân bay Phù Cát - Quy Nhơn (UIH) đang khai thác.",
    },
    "phú yên": {
        "iata": "TBB",
        "airport_city": "Tuy Hòa (Phú Yên)",
        "no_airport": False,
        "note": "Phú Yên (nay thuộc Đắk Lắk) vẫn có sân bay Tuy Hòa (TBB) đang khai thác.",
    },
    "tuy hòa": {
        "iata": "TBB",
        "airport_city": "Tuy Hòa (Phú Yên)",
        "no_airport": False,
        "note": "Sân bay Tuy Hòa (TBB) đang khai thác.",
    },
    "ninh thuận": {
        "iata": "CXR",
        "airport_city": "Cam Ranh (Khánh Hòa)",
        "no_airport": False,
        "note": "Ninh Thuận (nay thuộc Khánh Hòa). Sân bay Cam Ranh (CXR) gần nhất, cách Phan Rang ~60km.",
    },
    # ── FIX: CÁC TỈNH KHÔNG CÓ SÂN BAY (Bypass Normalize) ─────────────────
    "vũng tàu": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Vũng Tàu không có sân bay dân dụng. Bay vào TP.HCM (SGN) rồi đi xe khách ~2 giờ hoặc tàu cao tốc ~1.5 giờ từ bến Bạch Đằng.",
    },
    "bình dương": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Bình Dương (nay thuộc TP.HCM) không có sân bay. Bay vào TP.HCM (SGN) rồi đi xe ~40 phút.",
    },
    "đồng nai": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Đồng Nai không có sân bay dân dụng. Bay vào TP.HCM (SGN) rồi đi xe ~45 phút.",
    },
    "bà rịa": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Bà Rịa không có sân bay. Bay vào TP.HCM (SGN) rồi di chuyển tiếp ~1.5 giờ.",
    },
    "bắc ninh": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Bắc Ninh không có sân bay riêng. Bay vào Hà Nội (HAN) rồi đi xe ~30 phút.",
    },
    "hưng yên": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Hưng Yên không có sân bay riêng. Bay vào Hà Nội (HAN).",
    },
    "hải dương": {
        "iata": "HAN", 
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Hải Dương không có sân bay riêng. Bay vào Hà Nội (HAN) rồi đi xe.",
    },
    "thái bình": {
        "iata": "HAN", 
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Thái Bình không có sân bay riêng. Bay vào Hà Nội (HAN).",
    },
    "vĩnh phúc": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Vĩnh Phúc không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "bắc kạn": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Bắc Kạn không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "bắc giang": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Bắc Giang không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "hà giang": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Hà Giang không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "yên bái": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Yên Bái không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "hà nam": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Hà Nam không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "nam định": {
        "iata": "HAN",
        "airport_city": "Hà Nội",
        "no_airport": True,
        "note": "Nam Định không có sân bay. Bay vào Hà Nội (HAN).",
    },
    "bình phước": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Bình Phước không có sân bay. Bay vào TP.HCM (SGN).",
    },
    "long an": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Long An không có sân bay. Bay vào TP.HCM (SGN).",
    },
    "tiền giang": {
        "iata": "SGN",
        "airport_city": "TP. Hồ Chí Minh",
        "no_airport": True,
        "note": "Tiền Giang không có sân bay. Bay vào TP.HCM (SGN).",
    },
    "vĩnh long": {
        "iata": "VCA",
        "airport_city": "Cần Thơ",
        "no_airport": True,
        "note": "Vĩnh Long không có sân bay. Bay vào Cần Thơ (VCA).",
    },
    "trà vinh": {
        "iata": "VCA",
        "airport_city": "Cần Thơ",
        "no_airport": True,
        "note": "Trà Vinh không có sân bay. Bay vào Cần Thơ (VCA).",
    },
    "an giang": {
        "iata": "VCA",
        "airport_city": "Cần Thơ",
        "no_airport": True,
        "note": "An Giang không có sân bay. Bay vào Cần Thơ (VCA).",
    },
    "hậu giang": {
        "iata": "VCA",
        "airport_city": "Cần Thơ",
        "no_airport": True,
        "note": "Hậu Giang không có sân bay. Bay vào Cần Thơ (VCA).",
    },
    "sóc trăng": {
        "iata": "VCA",
        "airport_city": "Cần Thơ",
        "no_airport": True,
        "note": "Sóc Trăng không có sân bay. Bay vào Cần Thơ (VCA).",
    },
    "bạc liêu": {
        "iata": "CAH",
        "airport_city": "Cà Mau",
        "no_airport": True,
        "note": "Bạc Liêu không có sân bay. Bay vào Cà Mau (CAH).",
    },
}


def resolve_airport(city_name: str) -> dict:
    """
    Phân giải tên thành phố → mã IATA sân bay.

    Bước ĐẦU TIÊN: kiểm tra _KEEP_LOCAL_AIRPORT — các tỉnh đã sáp nhập
    nhưng vẫn còn sân bay riêng đang khai thác thương mại. Nếu match →
    trả IATA sân bay địa phương, KHÔNG normalize_province về tỉnh mới.

    Bước HAI: chuẩn hoá tên tỉnh cũ → tên tỉnh mới (34 tỉnh)
    theo PROVINCE_MERGE_MAP (hiệu lực từ 12/6/2025).
    Sau đó mới resolve sân bay theo tên mới.

    Trả về dict:
      {
        "iata":         str,   # mã IATA sân bay gần nhất
        "airport_city": str,   # tên thành phố thực có sân bay đó
        "no_airport":   bool,  # True nếu thành phố không có sân bay riêng
        "note":         str,   # ghi chú hướng dẫn
      }
    """
    raw = city_name.strip()
    raw_lower = raw.lower()

    # ✅ Bước -1: Tỉnh sáp nhập nhưng vẫn còn sân bay riêng đang khai thác
    # → KHÔNG normalize, resolve thẳng về IATA địa phương cho chính xác
    if raw_lower in _KEEP_LOCAL_AIRPORT:
        info = _KEEP_LOCAL_AIRPORT[raw_lower]
        print(f"[resolve_airport] '{raw}' → {info['iata']} no_airport={info['no_airport']} (bypass normalize)")
        return {
            "iata":         info["iata"],
            "airport_city": info["airport_city"],
            "no_airport":   info["no_airport"],
            "note":         info["note"],
        }

    # ✅ Bước 0: Chuẩn hoá tên tỉnh cũ → mới (34 tỉnh, từ 12/6/2025)
    name = normalize_province(raw)
    name_lower = name.lower()

    # 1. Match chính xác trong CITY_TO_IATA
    if name in CITY_TO_IATA:
        return {"iata": CITY_TO_IATA[name], "airport_city": name, "no_airport": False, "note": ""}

    # 2. Match không phân biệt hoa thường
    for city, iata in CITY_TO_IATA.items():
        if city.lower() == name_lower:
            return {"iata": iata, "airport_city": city, "no_airport": False, "note": ""}

    # 3. Match alias / viết không dấu
    if name_lower in _ALIAS:
        iata = _ALIAS[name_lower]
        return {"iata": iata, "airport_city": name, "no_airport": False, "note": ""}

    # 4. Match một phần (VD: "Khánh Hòa" → "Nha Trang")
    for city, iata in CITY_TO_IATA.items():
        if city.lower() in name_lower or name_lower in city.lower():
            return {"iata": iata, "airport_city": city, "no_airport": False, "note": ""}

    # 5. Thành phố không có sân bay → gợi ý thay thế
    for city, (iata, airport_city, note) in _NO_AIRPORT_NEAREST.items():
        if city.lower() in name_lower or name_lower in city.lower():
            return {"iata": iata, "airport_city": airport_city, "no_airport": True, "note": note}

    # 6. Hoàn toàn không nhận ra → trả cờ lỗi
    return {
        "iata": None,
        "airport_city": None,
        "no_airport": True,
        "note": f"Không tìm thấy sân bay cho '{city_name}'. Vui lòng kiểm tra lại tên thành phố."
    }


# ---------------------------------------------------------------------------
# 🗺️ TỌA ĐỘ SÂN BAY (để tính khoảng cách IATA → IATA)
# ---------------------------------------------------------------------------
_IATA_COORDS: dict[str, tuple[float, float]] = {
    "HAN": (21.221,  105.807), "DAD": (16.044,  108.199),
    "SGN": (10.818,  106.652), "HUI": (16.401,  107.703),
    "CXR": (11.998,  109.219), "DLI": (11.750,  108.367),
    "PQC": (10.170,  103.993), "VCA": (10.085,  105.712),
    "VCS": ( 8.731,  106.633), "BMV": (12.668,  108.120),
    "PXU": (14.004,  108.017), "UIH": (13.955,  109.042),
    "VCL": (15.403,  108.706), "VDH": (17.515,  106.591),
    "VII": (18.737,  105.671), "TBB": (13.050,  109.334),
    "DIN": (21.397,  103.008), "VKG": (10.052,  105.133),
    "CAH": ( 9.177,  105.177), "PHH": (10.999,  108.096),
    "SQH": (21.218,  104.033),
}

# Ngưỡng tối thiểu (km đường chim bay) để tìm vé máy bay.
# Dưới ngưỡng này → bỏ qua, tiết kiệm API call.
_MIN_FLIGHT_DISTANCE_KM = 150


def _iata_distance_km(iata_a: str, iata_b: str) -> float | None:
    """Tính khoảng cách km giữa 2 sân bay theo tọa độ. Trả None nếu không có tọa độ."""
    import math
    ca = _IATA_COORDS.get(iata_a.upper())
    cb = _IATA_COORDS.get(iata_b.upper())
    if not ca or not cb:
        return None
    lat1, lon1 = math.radians(ca[0]), math.radians(ca[1])
    lat2, lon2 = math.radians(cb[0]), math.radians(cb[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_smart_flight_recommendations(
    api_key, departure_id, arrival_id, max_total_budget,
    num_days, passengers, departure_date=None
):
    """
    Tìm vé máy bay phù hợp ngân sách.

    departure_id / arrival_id: mã IATA (str) hoặc None.
    Trả về list các chuyến bay, hoặc [] nếu không có / lỗi.
    """
    if not departure_id or not arrival_id:
        print("[Flight] Thiếu mã IATA — bỏ qua tìm kiếm vé.")
        return []

    if departure_id.upper() == arrival_id.upper():
        print(f"[Flight] departure == arrival ({departure_id}) — không cần bay.")
        return []

    # Bỏ qua tuyến quá gần — không kinh tế, không thực tế, tránh tốn API
    dist_km = _iata_distance_km(departure_id, arrival_id)
    if dist_km is not None and dist_km < _MIN_FLIGHT_DISTANCE_KM:
        print(f"[Flight] Tuyến {departure_id.upper()}→{arrival_id.upper()} quá gần ({dist_km:.0f} km < {_MIN_FLIGHT_DISTANCE_KM} km) — bỏ qua.")
        return []

    # Kiểm tra tuyến có khai thác thực tế không — tránh gọi API vô ích
    if not is_route_operated(departure_id, arrival_id):
        print(f"[Flight] Tuyến {departure_id.upper()}→{arrival_id.upper()} không có khai thác thương mại — bỏ qua.")
        return []

    try:
        outbound_dt = datetime.strptime(departure_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        outbound_dt = datetime.now() + timedelta(days=1)
        print(f"[Flight] departure_date không hợp lệ ('{departure_date}'), dùng ngày mai: {outbound_dt.strftime('%Y-%m-%d')}")

    def _fetch_flights_for_date(dt: datetime) -> list:
        """Gọi SerpAPI cho một ngày cụ thể, trả về list chuyến bay đã parse (hoặc [])."""
        params = {
            "engine":        "google_flights",
            "departure_id":  departure_id.upper(),
            "arrival_id":    arrival_id.upper(),
            "outbound_date": dt.strftime("%Y-%m-%d"),
            "type":          "2",
            "currency":      "VND",
            "hl":            "vi",
            "gl":            "vn",
            "adults":        passengers,
            "api_key":       api_key,
        }
        print(f"[Flight] Tìm {departure_id.upper()}→{arrival_id.upper()} ngày {dt.strftime('%Y-%m-%d')}")
        try:
            results = GoogleSearch(params).get_dict()
            if "error" in results:
                print(f"[Flight] ❌ SerpAPI error: {results['error']}")
                return []
            best  = results.get("best_flights", [])
            other = results.get("other_flights", [])
            raw   = best + other or results.get("flights", [])
            if not raw:
                return []

            parsed = []
            for f in raw:
                price = f.get("price", 0)
                if price <= 0:
                    continue
                leg = f.get("flights", [{}])[0]
                dur = f.get("total_duration", 0)
                h, m = divmod(dur, 60)
                parsed.append({
                    "airline":       leg.get("airline", ""),
                    "price":         price,
                    "thumbnail":     leg.get("airline_logo", ""),
                    "duration":      f"{h}h{m}m" if m else f"{h}h",
                    "duration_mins": dur,
                    "ticket_class":  leg.get("travel_class", "Phổ thông"),
                    "stops":         "Bay thẳng" if len(f.get("flights", [])) - 1 == 0 else f"{len(f.get('flights', [])) - 1} điểm dừng",
                    "departure":     leg.get("departure_airport", {}).get("time", ""),
                    "arrival":       leg.get("arrival_airport", {}).get("time", ""),
                    "booking_token": f.get("booking_token", ""),  # ← THÊM
                })

            parsed.sort(key=lambda x: (x["price"], x.get("duration_mins", 9999)))
            seen, final = {}, []
            for f in parsed:
                if f["airline"] not in seen:
                    seen[f["airline"]] = True
                    final.append(f)
                if len(final) == 2:
                    break
            if len(final) < 2:
                for f in parsed:
                    if f not in final:
                        final.append(f)
                    if len(final) == 2:
                        break
            return final[:2]

        except Exception as e:
            print(f"[Flight] Lỗi không mong đợi: {e}")
            return []

    try:
        # Chỉ tìm đúng ngày yêu cầu — không fallback sang ngày khác để tránh tốn thêm API
        flights = _fetch_flights_for_date(outbound_dt)
        if flights:
            return flights

        print(f"[Flight] ❌ Không có vé ngày {outbound_dt.strftime('%Y-%m-%d')} cho {departure_id.upper()}→{arrival_id.upper()}")

        # ---------------------------------------------------------------------------
        # 🔀 FALLBACK HUB: thử hub thay thế khi tuyến thực tế không có vé
        # ---------------------------------------------------------------------------
        dep_upper = departure_id.upper()
        arr_upper = arrival_id.upper()

        # Hub fallback cho arrival (bay vào hub gần điểm đến)
        arr_hubs = [h for h in _IATA_HUB_CANDIDATES.get(arr_upper, [])
                    if h != arr_upper and h != dep_upper and is_route_operated(dep_upper, h)]
        for hub in arr_hubs:
            print(f"[Flight] 🔀 Thử fallback arrival hub: {dep_upper} → {hub} (thay vì {arr_upper})")
            fallback = _fetch_flights_for_date_iata(dep_upper, hub, outbound_dt, passengers, api_key)
            if fallback:
                for f in fallback:
                    f["hub_fallback"] = hub
                    f["hub_fallback_note"] = f"Không có vé thẳng đến {arr_upper}. Đây là vé đến {hub} (hub gần nhất)."
                return fallback

        # Hub fallback cho departure (bay từ hub gần điểm xuất phát)
        dep_hubs = [h for h in _IATA_HUB_CANDIDATES.get(dep_upper, [])
                    if h != dep_upper and h != arr_upper and is_route_operated(h, arr_upper)]
        for hub in dep_hubs:
            print(f"[Flight] 🔀 Thử fallback departure hub: {hub} → {arr_upper} (thay vì {dep_upper})")
            fallback = _fetch_flights_for_date_iata(hub, arr_upper, outbound_dt, passengers, api_key)
            if fallback:
                for f in fallback:
                    f["hub_fallback"] = hub
                    f["hub_fallback_note"] = f"Không có vé thẳng từ {dep_upper}. Đây là vé từ {hub} (hub gần nhất)."
                return fallback

        print(f"[Flight] ❌ Không tìm được vé kể cả qua hub fallback — trả về []")
        return []

    except Exception as e:
        print(f"[Flight] Lỗi không mong đợi: {e}")
        return []


# ---------------------------------------------------------------------------
# 🔧 HELPER NỘI BỘ: GỌI SERPAPI CHO CẶP IATA BẤT KỲ (dùng trong hub fallback)
# ---------------------------------------------------------------------------

def _fetch_flights_for_date_iata(
    departure_id: str, arrival_id: str, dt: "datetime", passengers: int, api_key: str
) -> list:
    """
    Gọi SerpAPI cho cặp IATA + ngày cụ thể.
    Tách riêng để tái sử dụng trong logic hub fallback.
    Trả về list chuyến bay đã parse (tối đa 2), hoặc [].
    """
    params = {
        "engine":        "google_flights",
        "departure_id":  departure_id.upper(),
        "arrival_id":    arrival_id.upper(),
        "outbound_date": dt.strftime("%Y-%m-%d"),
        "type":          "2",
        "currency":      "VND",
        "hl":            "vi",
        "gl":            "vn",
        "adults":        passengers,
        "api_key":       api_key,
    }
    print(f"[Flight][FallbackHelper] {departure_id.upper()}→{arrival_id.upper()} ngày {dt.strftime('%Y-%m-%d')}")
    try:
        results = GoogleSearch(params).get_dict()
        if "error" in results:
            print(f"[Flight][FallbackHelper] ❌ SerpAPI error: {results['error']}")
            return []
        best  = results.get("best_flights", [])
        other = results.get("other_flights", [])
        raw   = best + other or results.get("flights", [])
        if not raw:
            return []
        parsed = []
        for f in raw:
            price = f.get("price", 0)
            if price <= 0:
                continue
            leg = f.get("flights", [{}])[0]
            dur = f.get("total_duration", 0)
            h, m = divmod(dur, 60)
            parsed.append({
                "airline":       leg.get("airline", ""),
                "price":         price,
                "thumbnail":     leg.get("airline_logo", ""),
                "duration":      f"{h}h{m}m" if m else f"{h}h",
                "duration_mins": dur,
                "ticket_class":  leg.get("travel_class", "Phổ thông"),
                "stops":         "Bay thẳng" if len(f.get("flights", [])) - 1 == 0 else f"{len(f.get('flights', [])) - 1} điểm dừng",
                "departure":     leg.get("departure_airport", {}).get("time", ""),
                "arrival":       leg.get("arrival_airport", {}).get("time", ""),
                "booking_token": f.get("booking_token", ""),
            })
        parsed.sort(key=lambda x: (x["price"], x.get("duration_mins", 9999)))
        seen, final = {}, []
        for f in parsed:
            if f["airline"] not in seen:
                seen[f["airline"]] = True
                final.append(f)
            if len(final) == 2:
                break
        if len(final) < 2:
            for f in parsed:
                if f not in final:
                    final.append(f)
                if len(final) == 2:
                    break
        return final[:2]
    except Exception as e:
        print(f"[Flight][FallbackHelper] Lỗi: {e}")
        return []


# ---------------------------------------------------------------------------
# 🔀 TÌM HUB TRANSIT TỐT NHẤT CHO TUYẾN KHÔNG CÓ BAY THẲNG
# ---------------------------------------------------------------------------

def get_transit_hub(origin_iata: str, dest_iata: str) -> str | None:
    """
    Tìm hub trung gian để transit khi không có bay thẳng origin→dest.

    Ưu tiên: SGN → HAN → DAD
    Điều kiện: hub phải có tuyến đến cả 2 đầu.
    """
    if not origin_iata or not dest_iata:
        return None
    for hub in ["SGN", "HAN", "DAD"]:
        if hub in (origin_iata, dest_iata):
            continue
        if is_route_operated(origin_iata, hub) and is_route_operated(hub, dest_iata):
            return hub
    return None


# ---------------------------------------------------------------------------
# ✈️ TÌM VÉ NHIỀU CHẶNG (KHI KHÔNG CÓ BAY THẲNG)
# ---------------------------------------------------------------------------

def get_multi_leg_flights(
    api_key, origin_iata, dest_iata, max_total_budget,
    num_days, passengers, departure_date=None
) -> dict:
    """
    Tự động tìm vé cho tuyến KHÔNG có bay thẳng bằng cách:
    1. Xác định hub transit tốt nhất (SGN / HAN / DAD)
    2. Tìm vé chặng 1: origin → hub
    3. Tìm vé chặng 2: hub → dest
    4. Trả về dict gồm hub, leg1_flights, leg2_flights

    Trả về {} nếu không tìm được hub phù hợp.
    """
    hub = get_transit_hub(origin_iata, dest_iata)
    if not hub:
        print(f"[MultiLeg] Không tìm được hub transit cho {origin_iata}→{dest_iata}")
        return {}

    print(f"[MultiLeg] Transit hub: {origin_iata} → {hub} → {dest_iata}")

    leg1 = get_smart_flight_recommendations(
        api_key, origin_iata, hub,
        max_total_budget, num_days, passengers, departure_date
    )
    leg2 = get_smart_flight_recommendations(
        api_key, hub, dest_iata,
        max_total_budget, num_days, passengers, departure_date
    )

    return {
        "hub":          hub,
        "leg1_flights": leg1,
        "leg2_flights": leg2,
    }