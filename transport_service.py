"""
transport_service.py
────────────────────
Xử lý TOÀN BỘ trường hợp di chuyển giữa 2 tỉnh bất kỳ trong Việt Nam.

Logic động theo khoảng cách + đặc điểm địa lý:
  < 50 km    → Nội vùng: taxi/grab/xe máy/xe buýt
  50–200 km  → Gần: xe khách + tàu hỏa (nếu có tuyến)
  200–500 km → Trung: xe khách + tàu hỏa + bay (nếu có sân bay)
  > 500 km   → Xa: bay là ưu tiên, tàu/xe là phương án kinh tế

Đặc biệt:
  - Đảo: luôn ưu tiên tàu cao tốc / bay
  - Tuyến có _COMBINED_ROUTES sẵn → dùng route chi tiết đó
  - Tỉnh không có sân bay → tính xe trung chuyển đến hub gần nhất
  - Tàu hỏa: tra bảng tuyến trực tiếp, nếu không có thì tính qua hub đa tầng
"""

from __future__ import annotations
import re
import math
import copy
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# 1. LOGO
# ────────────────────────────────────────────────────────────────────────────
LOGO_TRAIN = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcROTXAH8wZ9NbmMZzNOmrGx-_lhRI3DQyegiQ&s"
LOGO_BUS   = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRd3OEZ_0ypNdhf_eOTEs9Nejef-qIzou_qVg&s"

# ────────────────────────────────────────────────────────────────────────────
# 2. NORMALIZE TÊN TỈNH
# ────────────────────────────────────────────────────────────────────────────
_PROVINCE_ALIAS: dict[str, str] = {
    # Miền Bắc
    "hà nội":                "hà nội",
    "thủ đô hà nội":         "hà nội",
    "bắc ninh":             "bắc ninh",
    "hưng yên":             "hưng yên",
    "hải phòng":             "hải phòng",
    "hải dương":             "hải dương",
    "thái bình":             "thái bình",
    "quảng ninh":            "quảng ninh",
    "hạ long":               "quảng ninh",
    "vĩnh phúc":             "vĩnh phúc",
    "phú thọ":               "phú thọ",
    "thái nguyên":           "thái nguyên",
    "bắc kạn":               "bắc kạn",
    "bắc giang":             "bắc giang",
    "hòa bình":              "hòa bình",
    "lạng sơn":              "lạng sơn",
    "cao bằng":              "cao bằng",
    "hà giang":              "hà giang",
    "tuyên quang":           "tuyên quang",
    "lào cai":               "lào cai",
    "sapa":                  "lào cai",
    "yên bái":               "yên bái",
    "hà nam":                "hà nam",
    "nam định":              "nam định",
    "ninh bình":             "ninh bình",
    "sơn la":                "sơn la",
    "điện biên":             "điện biên",
    "điện biên phủ":         "điện biên",
    "lai châu":              "lai châu",
    "mộc châu":              "sơn la",
    # Miền Trung
    "thanh hóa":             "thanh hóa",
    "nghệ an":               "vinh",
    "vinh":                  "vinh",
    "hà tĩnh":               "hà tĩnh",
    "quảng bình":            "quảng bình",
    "đồng hới":              "quảng bình",
    "quảng trị":             "quảng trị",
    "đông hà":               "quảng trị",
    "thừa thiên huế":        "huế",
    "thừa thiên - huế":      "huế",
    "huế":                   "huế",
    "quảng nam":             "quảng nam",
    "tam kỳ":                "quảng nam",
    "hội an":                "hội an",
    "đà nẵng":               "đà nẵng",
    "kon tum":               "quảng ngãi",
    "quảng ngãi":            "quảng ngãi",
    "bình định":             "bình định",
    "quy nhơn":              "quy nhơn",
    "phú yên":               "phú yên",
    "tuy hòa":               "phú yên",
    "khánh hòa":             "nha trang",
    "nha trang":             "nha trang",
    "ninh thuận":            "nha trang",
    "phan rang":             "nha trang",
    "bình thuận":            "phan thiết",
    "phan thiết":            "phan thiết",
    "gia lai":               "gia lai",
    "pleiku":                "gia lai",
    "đắk lắk":               "buôn ma thuột",
    "buôn ma thuột":         "buôn ma thuột",
    "đắk nông":              "buôn ma thuột",
    "lâm đồng":              "đà lạt",
    "đà lạt":                "đà lạt",
    # Miền Nam
    "hồ chí minh":           "hồ chí minh",
    "tp. hồ chí minh":       "hồ chí minh",
    "tp.hồ chí minh":        "hồ chí minh",
    "sài gòn":               "hồ chí minh",
    "hcm":                   "hồ chí minh",
    "bình dương":            "bình dương",
    "bà rịa - vũng tàu":     "vũng tàu",
    "bà rịa–vũng tàu":       "vũng tàu",
    "bà rịa vũng tàu":       "vũng tàu",
    "bà rịa":                "vũng tàu",
    "vũng tàu":              "vũng tàu",
    "đồng nai":              "đồng nai",
    "biên hòa":              "đồng nai",
    "bình phước":            "bình phước",
    "long an":               "long an",
    "tây ninh":              "tây ninh",
    "tiền giang":            "tiền giang",
    "mỹ tho":                "tiền giang",
    "vĩnh long":             "vĩnh long",
    "bến tre":               "bến tre",
    "trà vinh":              "trà vinh",
    "đồng tháp":             "đồng tháp",
    "an giang":              "an giang",
    "long xuyên":            "an giang",
    "châu đốc":              "an giang",
    "kiên giang":            "kiên giang",
    "rạch giá":              "kiên giang",
    "phú quốc":              "phú quốc",
    "cần thơ":               "cần thơ",
    "hậu giang":             "hậu giang",
    "sóc trăng":             "sóc trăng",
    "bạc liêu":              "bạc liêu",
    "cà mau":                "cà mau",
    # Đảo
    "côn đảo":               "côn đảo",
    "lý sơn":                "lý sơn",
    "cù lao chàm":           "cù lao chàm",
    "phú quý":               "phú quý",
    "cát bà":                "cát bà",
    "cô tô":                 "cô tô",
    "bạch long vĩ":          "bạch long vĩ",
}

_AIRPORT_ALIAS: dict[str, str] = {
    "sgn": "hồ chí minh", "tân sơn nhất": "hồ chí minh", "tan son nhat": "hồ chí minh", "sân bay tân sơn nhất": "hồ chí minh",
    "han": "hà nội", "nội bài": "hà nội", "noi bai": "hà nội", "sân bay nội bài": "hà nội",
    "dad": "đà nẵng", "sân bay đà nẵng": "đà nẵng", "da nang": "đà nẵng",
    "hui": "huế", "phú bài": "huế", "phu bai": "huế", "sân bay phú bài": "huế",
    "cxr": "nha trang", "cam ranh": "nha trang", "sân bay cam ranh": "nha trang", "khanh hoa": "nha trang",
    "dli": "đà lạt", "liên khương": "đà lạt", "lien khuong": "đà lạt", "lam dong": "đà lạt",
    "pqc": "phú quốc", "phu quoc": "phú quốc",
    "vca": "cần thơ", "can tho": "cần thơ",
    "vcs": "côn đảo", "con dao": "côn đảo",
    "uih": "quy nhơn", "phù cát": "quy nhơn", "phu cat": "quy nhơn", "quy nhon": "quy nhơn", "binh dinh": "bình định",
    "bmv": "buôn ma thuột", "buon ma thuot": "buôn ma thuột", "ban me thuot": "buôn ma thuột", "dak lak": "buôn ma thuột",
    "pxu": "gia lai", "pleiku": "gia lai",
    "vcl": "quảng nam", "chu lai": "quảng nam",
    "tbb": "phú yên", "tuy hoa": "phú yên", "phu yen": "phú yên",
    "vdh": "quảng bình", "dong hoi": "quảng bình", "quang binh": "quảng bình",
    "vii": "vinh", "nghe an": "vinh", "din": "điện biên", "dien bien": "điện biên", "dien bien phu": "điện biên",
    "hph": "hải phòng", "cat bi": "hải phòng", "hai phong": "hải phòng",
    "thd": "thanh hóa", "thanh hoa": "thanh hóa", "tho xuan": "thanh hóa",
    "vkg": "kiên giang", "rach gia": "kiên giang", "kien giang": "kiên giang",
    "cah": "cà mau", "ca mau": "cà mau",
    "phh": "phan thiết", "phan thiet": "phan thiết", "binh thuan": "phan thiết",
    "vdo": "quảng ninh", "van don": "quảng ninh", "quang ninh": "quảng ninh", "ha long": "quảng ninh",
    "ho chi minh": "hồ chí minh", "hcm": "hồ chí minh", "ha noi": "hà nội", "hue": "huế",
    "sapa": "lào cai", "sa pa": "lào cai", "vung tau": "vũng tàu", "ba ria": "vũng tàu", "ba ria vung tau": "vũng tàu",
    "ninh binh": "ninh bình", "phan rang": "nha trang", "ca mau": "cà mau", "bien hoa": "đồng nai",
}

def _norm(s: str) -> str:
    s = s.lower().strip()
    for p in ["tp. ", "tp.", "tỉnh ", "thành phố ", "thành phố", "sân bay ", "san bay ", "airport "]:
        s = s.replace(p, "").strip()
    if s in _AIRPORT_ALIAS:
        return _AIRPORT_ALIAS[s]
    return _PROVINCE_ALIAS.get(s, s)

# ────────────────────────────────────────────────────────────────────────────
# 3. BẢNG SÂN BAY 63 TỈNH CHI TIẾT
# ────────────────────────────────────────────────────────────────────────────
_PROVINCE_INFO: dict[str, dict] = {
    # MIỀN BẮC
    "hà nội":        {"iata": "HAN", "hub": None,         "hub_km": 0,   "train": "Hà Nội"},
    "hải phòng":     {"iata": "HPH", "hub": None,         "hub_km": 0,   "train": "Hải Phòng"},
    "quảng ninh":    {"iata": "VDO", "hub": "hà nội",     "hub_km": 160, "train": None},
    "hải dương":     {"iata": None,  "hub": "hà nội",     "hub_km": 60,  "train": None},
    "hưng yên":      {"iata": None,  "hub": "hà nội",     "hub_km": 50,  "train": None},
    "bắc ninh":      {"iata": None,  "hub": "hà nội",     "hub_km": 30,  "train": None},
    "vĩnh phúc":     {"iata": None,  "hub": "hà nội",     "hub_km": 50,  "train": None},
    "phú thọ":       {"iata": None,  "hub": "hà nội",     "hub_km": 80,  "train": "Việt Trì"},
    "thái nguyên":   {"iata": None,  "hub": "hà nội",     "hub_km": 80,  "train": None},
    "bắc giang":     {"iata": None,  "hub": "hà nội",     "hub_km": 50,  "train": None},
    "lạng sơn":      {"iata": None,  "hub": "hà nội",     "hub_km": 150, "train": "Đồng Đăng"},
    "cao bằng":      {"iata": None,  "hub": "hà nội",     "hub_km": 280, "train": None},
    "hà giang":      {"iata": None,  "hub": "hà nội",     "hub_km": 320, "train": None},
    "lào cai":       {"iata": None,  "hub": "hà nội",     "hub_km": 300, "train": "Lào Cai"},
    "yên bái":       {"iata": None,  "hub": "hà nội",     "hub_km": 180, "train": "Yên Bái"},
    "tuyên quang":   {"iata": None,  "hub": "hà nội",     "hub_km": 130, "train": None},
    "bắc kạn":       {"iata": None,  "hub": "hà nội",     "hub_km": 160, "train": None},
    "thái bình":     {"iata": None,  "hub": "hà nội",     "hub_km": 110, "train": None},
    "nam định":      {"iata": None,  "hub": "hà nội",     "hub_km": 90,  "train": "Nam Định"},
    "hà nam":        {"iata": None,  "hub": "hà nội",     "hub_km": 60,  "train": "Phủ Lý"},
    "ninh bình":     {"iata": None,  "hub": "hà nội",     "hub_km": 100, "train": "Ninh Bình"},
    "hòa bình":      {"iata": None,  "hub": "hà nội",     "hub_km": 70,  "train": None},
    "sơn la":        {"iata": None,  "hub": "hà nội",     "hub_km": 320, "train": None},
    "điện biên":     {"iata": "DIN", "hub": "hà nội",     "hub_km": 480, "train": None},
    "lai châu":      {"iata": None,  "hub": "hà nội",     "hub_km": 450, "train": None},
    # MIỀN TRUNG
    "thanh hóa":     {"iata": "THD", "hub": "hà nội",     "hub_km": 150, "train": "Thanh Hóa"},
    "vinh":          {"iata": "VII", "hub": None,          "hub_km": 0,   "train": "Vinh"},
    "hà tĩnh":       {"iata": None,  "hub": "vinh",        "hub_km": 50,  "train": "Yên Trung"},
    "quảng bình":    {"iata": "VDH", "hub": None,          "hub_km": 0,   "train": "Đồng Hới"},
    "quảng trị":     {"iata": "VDH", "hub": None,          "hub_km": 0,   "train": "Đông Hà"},
    "huế":           {"iata": "HUI", "hub": None,          "hub_km": 0,   "train": "Huế"},
    "đà nẵng":       {"iata": "DAD", "hub": None,          "hub_km": 0,   "train": "Đà Nẵng"},
    "quảng nam":     {"iata": "VCL", "hub": "đà nẵng",     "hub_km": 65,  "train": "Tam Kỳ",  "needs_transfer": True,  "transfer_km": 30},
    "tam kỳ":        {"iata": "VCL", "hub": "đà nẵng",     "hub_km": 60,  "train": "Tam Kỳ",  "needs_transfer": True,  "transfer_km": 25},
    "hội an":        {"iata": None,  "hub": "đà nẵng",     "hub_km": 30,  "train": None},
    "quảng ngãi":    {"iata": "VCL", "hub": "đà nẵng",     "hub_km": 60,  "train": "Quảng Ngãi"},
    "quy nhơn":      {"iata": "UIH", "hub": None,          "hub_km": 0,   "train": "Diêu Trì"},
    "bình định":     {"iata": "UIH", "hub": None,          "hub_km": 0,   "train": "Diêu Trì"},
    "phú yên":       {"iata": "TBB", "hub": None,          "hub_km": 0,   "train": "Tuy Hòa"},
    "tuy hòa":       {"iata": "TBB", "hub": None,          "hub_km": 0,   "train": "Tuy Hòa"},
    "buôn ma thuột": {"iata": "BMV", "hub": "hồ chí minh", "hub_km": 350, "train": None},
    "nha trang":     {"iata": "CXR", "hub": None,          "hub_km": 0,   "train": "Nha Trang"},
    "phan thiết":    {"iata": None,  "hub": "hồ chí minh", "hub_km": 200, "train": "Mương Mán"},
    "gia lai":       {"iata": "PXU", "hub": "đà nẵng",     "hub_km": 200, "train": None},
    "đà lạt":        {"iata": "DLI", "hub": "hồ chí minh", "hub_km": 300, "train": None},
    # MIỀN NAM
    "hồ chí minh":   {"iata": "SGN", "hub": None,          "hub_km": 0,   "train": "Sài Gòn"},
    "bình dương":    {"iata": None,  "hub": "hồ chí minh", "hub_km": 40,  "train": None},
    "vũng tàu":      {"iata": None,  "hub": "hồ chí minh", "hub_km": 90,  "train": None},
    "đồng nai":      {"iata": None,  "hub": "hồ chí minh", "hub_km": 35,  "train": None},
    "bình phước":    {"iata": None,  "hub": "đồng nai",    "hub_km": 80,  "train": None},
    "long an":       {"iata": None,  "hub": "hồ chí minh", "hub_km": 50,  "train": None},
    "tây ninh":      {"iata": None,  "hub": "hồ chí minh", "hub_km": 100, "train": None},
    "tiền giang":    {"iata": None,  "hub": "hồ chí minh", "hub_km": 70,  "train": None},
    "vĩnh long":     {"iata": None,  "hub": "cần thơ",     "hub_km": 40,  "train": None},
    "bến tre":       {"iata": None,  "hub": "hồ chí minh", "hub_km": 85,  "train": None},
    "trà vinh":      {"iata": None,  "hub": "cần thơ",     "hub_km": 90,  "train": None},
    "đồng tháp":     {"iata": None,  "hub": "hồ chí minh", "hub_km": 165, "train": None},
    "an giang":      {"iata": None,  "hub": "cần thơ",     "hub_km": 60,  "train": None},
    "kiên giang":    {"iata": "VKG", "hub": "hồ chí minh", "hub_km": 250, "train": None},
    "phú quốc":      {"iata": "PQC", "hub": "hồ chí minh", "hub_km": 400, "train": None, "island": True},
    "cần thơ":       {"iata": "VCA", "hub": None,          "hub_km": 0,   "train": None},
    "hậu giang":     {"iata": None,  "hub": "cần thơ",     "hub_km": 20,  "train": None},
    "sóc trăng":     {"iata": None,  "hub": "cần thơ",     "hub_km": 60,  "train": None},
    "bạc liêu":      {"iata": None,  "hub": "cà mau",      "hub_km": 60,  "train": None},
    "cà mau":        {"iata": "CAH", "hub": "cần thơ",     "hub_km": 180, "train": None},
    # ĐẢO
    "côn đảo":       {"iata": "VCS", "hub": "hồ chí minh", "hub_km": 400, "train": None, "island": True},
    "lý sơn":        {"iata": None,  "hub": "quảng ngãi",  "hub_km": 30,  "train": None, "island": True},
    "cù lao chàm":   {"iata": None,  "hub": "hội an",      "hub_km": 15,  "train": None, "island": True},
    "phú quý":       {"iata": None,  "hub": "phan thiết",  "hub_km": 120, "train": None, "island": True},
    "cát bà":        {"iata": None,  "hub": "hải phòng",   "hub_km": 50,  "train": None, "island": True},
    "cô tô":         {"iata": None,  "hub": "quảng ninh",  "hub_km": 100, "train": None, "island": True},
    "bạch long vĩ":  {"iata": None,  "hub": "hải phòng",   "hub_km": 130, "train": None, "island": True},
}

def _get_pinfo(place: str) -> dict:
    return _PROVINCE_INFO.get(_norm(place), {})

# ────────────────────────────────────────────────────────────────────────────
# 4. TUYẾN TÀU HỎA
# ────────────────────────────────────────────────────────────────────────────
_TRAIN_ROUTES: dict[frozenset, dict] = {
    frozenset({"hà nội", "hồ chí minh"}):  {"duration": "~30–33 giờ", "price_range": "900.000–2.000.000 VNĐ",  "tips": "Đặt trước qua dsvn.vn; ngồi mềm ~900k, giường nằm ~1.5–2M."},
    frozenset({"hà nội", "đà nẵng"}):       {"duration": "~16–18 giờ", "price_range": "450.000–1.050.000 VNĐ",  "tips": "Tàu SE1/SE3 ban đêm tiết kiệm 1 đêm khách sạn."},
    frozenset({"hà nội", "huế"}):           {"duration": "~13–14 giờ", "price_range": "380.000–900.000 VNĐ",    "tips": "Tàu SE7/SE9 qua đèo Hải Vân ban ngày."},
    frozenset({"hà nội", "vinh"}):          {"duration": "~5–6 giờ",   "price_range": "200.000–450.000 VNĐ",    "tips": "Nhiều chuyến/ngày."},
    frozenset({"hà nội", "thanh hóa"}):     {"duration": "~3–4 giờ",   "price_range": "130.000–320.000 VNĐ",    "tips": "Tàu SE/TN nhanh và đúng giờ."},
    frozenset({"hà nội", "ninh bình"}):     {"duration": "~2–2,5 giờ", "price_range": "80.000–200.000 VNĐ",     "tips": "Tàu nhanh từ ga Hà Nội."},
    frozenset({"hà nội", "lào cai"}):       {"duration": "~8 giờ",     "price_range": "260.000–580.000 VNĐ",    "tips": "Tàu đêm SP1/SP3 tiện lợi."},
    frozenset({"hà nội", "hải phòng"}):     {"duration": "~2 giờ",     "price_range": "65.000–130.000 VNĐ",     "tips": "Nhanh hơn xe buýt giờ cao điểm."},
    frozenset({"hà nội", "quy nhơn"}):      {"duration": "~20–22 giờ", "price_range": "580.000–1.300.000 VNĐ",  "tips": "Ga Diêu Trì cách TT Quy Nhơn ~10km."},
    frozenset({"hà nội", "nha trang"}):     {"duration": "~25–27 giờ", "price_range": "700.000–1.550.000 VNĐ",  "tips": "Tàu SE đêm."},
    frozenset({"hà nội", "quảng ngãi"}):    {"duration": "~18–20 giờ", "price_range": "490.000–1.100.000 VNĐ",  "tips": "Giường nằm 6 chỗ."},
    frozenset({"hà nội", "quảng trị"}):     {"duration": "~11–12 giờ", "price_range": "320.000–720.000 VNĐ",    "tips": "Tàu qua ga Đông Hà."},
    frozenset({"hà nội", "quảng bình"}):    {"duration": "~10 giờ",    "price_range": "320.000–780.000 VNĐ",    "tips": "Ga Đồng Hới."},
    frozenset({"hà nội", "phú yên"}):       {"duration": "~24 giờ",    "price_range": "750.000–1.550.000 VNĐ",  "tips": "Ga Tuy Hòa."},
    frozenset({"hồ chí minh", "nha trang"}):{"duration": "~7–8 giờ",   "price_range": "320.000–780.000 VNĐ",    "tips": "Tàu SE ban đêm."},
    frozenset({"hồ chí minh", "đà nẵng"}):  {"duration": "~17–19 giờ", "price_range": "520.000–1.180.000 VNĐ",  "tips": "Nên chọn giường nằm khoang 4 người."},
    frozenset({"hồ chí minh", "phan thiết"}):{"duration": "~4 giờ",    "price_range": "105.000–260.000 VNĐ",    "tips": "Tàu SPT1/SPT3 từ ga Mương Mán."},
    frozenset({"hồ chí minh", "huế"}):      {"duration": "~20–22 giờ", "price_range": "580.000–1.300.000 VNĐ",  "tips": "Tàu SE/TN ban đêm."},
    frozenset({"hồ chí minh", "vinh"}):     {"duration": "~26–28 giờ", "price_range": "780.000–1.550.000 VNĐ",  "tips": "Hành trình rất dài."},
    frozenset({"hồ chí minh", "quy nhơn"}): {"duration": "~11–12 giờ", "price_range": "350.000–780.000 VNĐ",    "tips": "Ga Diêu Trì cách trung tâm Quy Nhơn ~10km."},
    frozenset({"hồ chí minh", "quảng ngãi"}):{"duration":"~14–16 giờ","price_range": "420.000–940.000 VNĐ",    "tips": "Tàu SE tiết kiệm."},
    frozenset({"hồ chí minh", "quảng trị"}):{"duration": "~22–24 giờ", "price_range": "650.000–1.430.000 VNĐ",  "tips": "Ga Đông Hà."},
    frozenset({"hồ chí minh", "quảng bình"}):{"duration":"~22 giờ",    "price_range": "650.000–1.430.000 VNĐ",  "tips": "Ga Đồng Hới."},
    frozenset({"hồ chí minh", "phú yên"}):  {"duration": "~10 giờ",    "price_range": "325.000–720.000 VNĐ",    "tips": "Ga Tuy Hòa. Tàu đêm."},
    frozenset({"hồ chí minh", "hà tĩnh"}):  {"duration": "~26–28 giờ", "price_range": "750.000–1.630.000 VNĐ",  "tips": "Tàu dừng ga Yên Trung."},
    frozenset({"hồ chí minh", "ninh bình"}):{"duration": "~30–32 giờ", "price_range": "880.000–1.820.000 VNĐ",  "tips": "Cân nhắc máy bay."},
    frozenset({"đà nẵng", "huế"}):          {"duration": "~2,5 giờ",   "price_range": "80.000–200.000 VNĐ",     "tips": "Tàu qua đèo Hải Vân cực đẹp."},
    frozenset({"đà nẵng", "nha trang"}):    {"duration": "~10–11 giờ", "price_range": "260.000–650.000 VNĐ",    "tips": "Tàu đêm SE tiết kiệm chi phí."},
    frozenset({"đà nẵng", "quy nhơn"}):     {"duration": "~5–6 giờ",   "price_range": "155.000–365.000 VNĐ",    "tips": "Tàu SE qua ga Diêu Trì."},
    frozenset({"đà nẵng", "quảng ngãi"}):   {"duration": "~3–4 giờ",   "price_range": "105.000–235.000 VNĐ",    "tips": "Nhiều chuyến/ngày."},
    frozenset({"đà nẵng", "quảng trị"}):    {"duration": "~2–2,5 giờ", "price_range": "65.000–170.000 VNĐ",     "tips": "Ga Đông Hà."},
    frozenset({"đà nẵng", "vinh"}):         {"duration": "~8–9 giờ",   "price_range": "260.000–585.000 VNĐ",    "tips": "Tàu đêm."},
    frozenset({"đà nẵng", "thanh hóa"}):    {"duration": "~11–12 giờ", "price_range": "340.000–755.000 VNĐ",    "tips": "Giường nằm khoang 6 người."},
    frozenset({"huế", "vinh"}):             {"duration": "~6–7 giờ",   "price_range": "195.000–455.000 VNĐ",    "tips": "Tàu đêm."},
    frozenset({"huế", "quảng trị"}):        {"duration": "~1–1,5 giờ", "price_range": "40.000–105.000 VNĐ",     "tips": "Ga Đông Hà."},
    frozenset({"huế", "thanh hóa"}):        {"duration": "~9–10 giờ",  "price_range": "275.000–610.000 VNĐ",    "tips": "Giường nằm thoải mái."},
    frozenset({"huế", "nha trang"}):        {"duration": "~13–14 giờ", "price_range": "390.000–885.000 VNĐ",    "tips": "Tàu đêm."},
    frozenset({"huế", "quy nhơn"}):         {"duration": "~8–9 giờ",   "price_range": "245.000–560.000 VNĐ",    "tips": "Ga Diêu Trì."},
    frozenset({"nha trang", "quy nhơn"}):   {"duration": "~5–6 giờ",   "price_range": "155.000–365.000 VNĐ",    "tips": "Ghế ngồi mềm điều hoà."},
    frozenset({"nha trang", "phan thiết"}): {"duration": "~3–3,5 giờ", "price_range": "90.000–220.000 VNĐ",     "tips": "Ghế ngồi phù hợp."},
    frozenset({"nha trang", "vinh"}):       {"duration": "~18–20 giờ", "price_range": "545.000–1.210.000 VNĐ",  "tips": "Nên chọn giường nằm."},
    frozenset({"vinh", "quảng trị"}):       {"duration": "~4,5–5 giờ", "price_range": "145.000–325.000 VNĐ",    "tips": "Tàu SE nhiều chuyến/ngày."},
    frozenset({"vinh", "thanh hóa"}):       {"duration": "~2–2,5 giờ", "price_range": "72.000–170.000 VNĐ",     "tips": "Nhiều chuyến/ngày."},
    frozenset({"phan thiết", "hồ chí minh"}):{"duration":"~4 giờ",     "price_range": "105.000–260.000 VNĐ",    "tips": "Tàu SPT1/SPT3 ga Mương Mán."},
}

_TRAIN_NODE_ALIAS = {
    "bình định": "quy nhơn",
    "khánh hòa": "nha trang",
    "lâm đồng": "đà lạt",
    "thừa thiên huế": "huế",
    "bình thuận": "phan thiết",
    "phú yên": "tuy hòa",
    "nghệ an": "vinh",
}

def _find_train(o: str, d: str) -> Optional[dict]:
    o_node = _TRAIN_NODE_ALIAS.get(_norm(o), _norm(o))
    d_node = _TRAIN_NODE_ALIAS.get(_norm(d), _norm(d))
    return _TRAIN_ROUTES.get(frozenset({o_node, d_node}))

def _find_train_via_hub(o: str, d: str) -> Optional[tuple[dict, str, str]]:
    po = _get_pinfo(o)
    pd = _get_pinfo(d)

    # 1. Các hub tiềm năng cho Điểm Xuất Phát (O)
    hubs_o = []
    if po.get("train"): hubs_o.append(_norm(o))
    if po.get("hub"): hubs_o.append(po["hub"])
    if not po.get("train"): hubs_o.extend(["hồ chí minh", "đà nẵng", "hà nội"])

    # 2. Các hub tiềm năng cho Điểm Đến (D)
    hubs_d = []
    if pd.get("train"): hubs_d.append(_norm(d))
    if pd.get("hub"): hubs_d.append(pd["hub"])
    if not pd.get("train"): hubs_d.extend(["hồ chí minh", "đà nẵng", "hà nội"])

    # 3. Quét tổ hợp hub — bỏ nếu chặng xe cuối dài hơn khoảng cách thẳng origin→dest
    direct_dist = _estimate_distance(o, d)
    for h_o in hubs_o:
        for h_d in hubs_d:
            if h_o == h_d: continue
            node_o = _TRAIN_NODE_ALIAS.get(h_o, h_o)
            node_d = _TRAIN_NODE_ALIAS.get(h_d, h_d)
            if node_o != node_d:
                t = _TRAIN_ROUTES.get(frozenset({node_o, node_d}))
                if t:
                    # Kiểm tra chặng xe cuối (hub_d → d) không vô lý
                    if _norm(d) != h_d:
                        last_leg_km = _estimate_distance(h_d, d)
                        if last_leg_km != 999 and last_leg_km > direct_dist * 0.8:
                            continue  # Hub này đi vòng, bỏ qua
                    return t, h_o, h_d
    return None

# ────────────────────────────────────────────────────────────────────────────
# 5. HELPER: GIÁ XE & THỜI GIAN
# ────────────────────────────────────────────────────────────────────────────
def _bus_duration(km: float) -> str:
    h = int(km / 60)
    m = int((km / 60 - h) * 60)
    return f"~{h} giờ {m:02d} phút" if m else f"~{h} giờ"

def _bus_price(km: float) -> str:
    lo = max(80_000, int(km * 1_500 / 1_000) * 1_000)
    hi = max(120_000, int(km * 2_200 / 1_000) * 1_000)
    return f"{lo:,}–{hi:,} VNĐ".replace(",", ".")

def _transfer_cost_km(km: int) -> tuple[int, int, str, str]:
    if km <= 30:   rate_lo, rate_hi = 4_000, 6_500
    elif km <= 80: rate_lo, rate_hi = 3_200, 5_000
    else:          rate_lo, rate_hi = 2_500, 3_800
    lo = max(80_000, int(km * rate_lo / 1_000) * 1_000)
    hi = max(120_000, int(km * rate_hi / 1_000) * 1_000)
    return lo, hi, f"~{lo:,}–{hi:,} VNĐ".replace(",", "."), f"~{max(1, round(km/50))} giờ ({km} km)"

def _parse_price_range(s: str) -> tuple[int, int]:
    nums = re.findall(r"[\d]+(?:\.[\d]+)*", s)
    parsed = [int(n.replace(".", "")) for n in nums if n.replace(".", "").isdigit()]
    if len(parsed) >= 2: return parsed[0], parsed[1]
    if len(parsed) == 1: return parsed[0], parsed[0]
    return 0, 0

# ────────────────────────────────────────────────────────────────────────────
# 6. TUYẾN KẾT HỢP
# ────────────────────────────────────────────────────────────────────────────
_COMBINED_ROUTES: dict[frozenset, list[dict]] = {
    frozenset({"hà nội", "lào cai"}): [
        {"label":"🚆 Tàu đêm + 🚗 Xe lên Sapa","type":"combined","duration":"~9–10 giờ","price_range":"500.000–900.000 VNĐ","tips":"Sáng đến Lào Cai đi xe lên Sapa.","recommended":True,
         "legs":[{"step":1,"icon":"🚆","mode":"train","label":"Tàu đêm Hà Nội → Lào Cai","duration":"~8 giờ","price_range":"260.000–580.000 VNĐ","tips":"Tàu SP1/SP3."},
                 {"step":2,"icon":"🚗","mode":"car","label":"Xe từ ga Lào Cai → Sapa","duration":"~1 giờ (~38 km)","price_range":"200.000–320.000 VNĐ","tips":"Limousine."}]},
    ],
    frozenset({"hà nội", "hội an"}): [
        {"label":"✈️ Bay HAN → DAD + 🚗 Xe vào Hội An","type":"combined","duration":"~2,5–3 giờ","price_range":"Vé bay + 100.000–200.000 VNĐ","tips":"Nhanh nhất.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"Máy bay Hà Nội (HAN) → Đà Nẵng (DAD)","duration":"~1 giờ 20 phút","price_range":"Xem vé","tips":"Nhiều chuyến/ngày."},
                 {"step":2,"icon":"🚗","mode":"car","label":"Taxi/Grab sân bay Đà Nẵng → Hội An","duration":"~40 phút","price_range":"100.000–200.000 VNĐ","tips":"Grab."}]},
    ],
    frozenset({"hồ chí minh", "hội an"}): [
        {"label":"✈️ Bay SGN → DAD + 🚗 Xe vào Hội An","type":"combined","duration":"~2,5–3 giờ","price_range":"Vé bay + 100.000–200.000 VNĐ","tips":"Nhanh nhất.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"Máy bay TP.HCM (SGN) → Đà Nẵng (DAD)","duration":"~1 giờ 20 phút","price_range":"Xem vé","tips":"Nhiều chuyến/ngày."},
                 {"step":2,"icon":"🚗","mode":"car","label":"Taxi/Grab sân bay Đà Nẵng → Hội An","duration":"~40 phút","price_range":"100.000–200.000 VNĐ","tips":"Grab."}]},
    ],
    frozenset({"hồ chí minh", "vũng tàu"}): [
        {"label":"🚢 Tàu cao tốc TP.HCM → Vũng Tàu","type":"combined","duration":"~2 giờ","price_range":"320.000–450.000 VNĐ/người","tips":"Từ bến Bạch Đằng.","recommended":True,
         "legs":[{"step":1,"icon":"🚌","mode":"bus","label":"Đến bến Bạch Đằng","duration":"~20 phút","price_range":"40.000–100.000 VNĐ","tips":"Bến tàu Bạch Đằng."},
                 {"step":2,"icon":"🚢","mode":"ferry","label":"Tàu cao tốc Côn Đảo Express","duration":"~2 giờ","price_range":"320.000–450.000 VNĐ","tips":"Nên đặt trước."},
                 {"step":3,"icon":"🚗","mode":"car","label":"Grab cảng Vũng Tàu → khách sạn","duration":"~10 phút","price_range":"50.000 VNĐ","tips":"Cảng ngay trung tâm."}]},
    ],
    frozenset({"hồ chí minh", "đà lạt"}): [
        {"label":"✈️ Bay SGN → DLI + 🚗 Xe vào trung tâm","type":"combined","duration":"~1,5–2 giờ","price_range":"Vé bay + 80.000–150.000 VNĐ","tips":"Nhanh nhất.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"Máy bay TP.HCM (SGN) → Đà Lạt (DLI)","duration":"~50 phút","price_range":"Xem vé","tips":"Nhiều chuyến."},
                 {"step":2,"icon":"🚗","mode":"car","label":"Taxi sân bay Liên Khương → Đà Lạt","duration":"~30 phút","price_range":"80.000–150.000 VNĐ","tips":"Bus hoặc Grab."}]},
    ],
    frozenset({"hồ chí minh", "phú quốc"}): [
        {"label":"✈️ Bay thẳng SGN → PQC","type":"combined","duration":"~1 giờ 10 phút","price_range":"Xem chuyến bay","tips":"Nhanh và tiện nhất.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"Bay SGN → PQC","duration":"~1 giờ","price_range":"Xem vé","tips":"Nhiều chuyến."}]},
    ],
    frozenset({"đà nẵng", "phú quốc"}): [
        {"label":"✈️ Bay thẳng DAD → PQC","type":"combined","duration":"~1 giờ 20 phút","price_range":"Xem chuyến bay","tips":"VietJet/VNA.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"Bay DAD → PQC","duration":"~1h20m","price_range":"Xem vé","tips":"Bay thẳng."}]},
    ],
    frozenset({"hà nội", "côn đảo"}): [
        {"label":"✈️ Bay HAN → SGN + SGN → VCS","type":"combined","duration":"~4–5 giờ","price_range":"Giá 2 chặng bay","tips":"Không có bay thẳng.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"HAN → SGN","duration":"~2h","price_range":"Xem vé","tips":"Chuyến nối."},
                 {"step":2,"icon":"✈️","mode":"flight","label":"SGN → VCS","duration":"~50m","price_range":"Xem vé","tips":"VASCO."}]},
    ],
    frozenset({"h hồ chí minh", "côn đảo"}): [
        {"label":"✈️ Bay SGN → VCS (thẳng)","type":"combined","duration":"~50 phút","price_range":"Xem chuyến bay","tips":"Hành lý 7kg.","recommended":True,
         "legs":[{"step":1,"icon":"✈️","mode":"flight","label":"SGN → VCS","duration":"~50m","price_range":"Xem vé","tips":"VASCO."}]},
    ],
    frozenset({"hải phòng", "cát bà"}): [
        {"label":"🚢 Phà Hải Phòng → Cát Bà","type":"combined","duration":"~1 giờ","price_range":"120.000–200.000 VNĐ","tips":"Bến Bính hoặc bến Gót.","recommended":True,
         "legs":[{"step":1,"icon":"🚢","mode":"ferry","label":"Phà ra đảo Cát Bà","duration":"~1h","price_range":"130.000 VNĐ","tips":"Phà chạy nhiều chuyến."}]},
    ],
    frozenset({"quảng ngãi", "lý sơn"}): [
        {"label":"🚢 Tàu cao tốc Sa Kỳ → Lý Sơn","type":"combined","duration":"~30 phút","price_range":"200.000–280.000 VNĐ","tips":"Cách TT Quảng Ngãi 30km.","recommended":True,
         "legs":[{"step":1,"icon":"🚌","mode":"bus","label":"Xe TT Quảng Ngãi → Cảng Sa Kỳ","duration":"~30m","price_range":"100.000 VNĐ","tips":"Taxi."},
                 {"step":2,"icon":"🚢","mode":"ferry","label":"Tàu cao tốc ra Lý Sơn","duration":"~30m","price_range":"230.000 VNĐ","tips":"Đặt vé."}]},
    ],
    frozenset({"hội an", "cù lao chàm"}): [
        {"label":"🚢 Tàu cao tốc Hội An → Cù Lao Chàm","type":"combined","duration":"~30 phút","price_range":"380.000–520.000 VNĐ","tips":"Thường đi theo tour.","recommended":True,
         "legs":[{"step":1,"icon":"🚢","mode":"ferry","label":"Tàu từ bến Cửa Đại","duration":"~30m","price_range":"430.000 VNĐ","tips":"Nên đi tour."}]},
    ],
    frozenset({"phan thiết", "phú quý"}): [
        {"label":"🚢 Tàu cao tốc Phan Thiết → Phú Quý","type":"combined","duration":"~2,5 giờ","price_range":"380.000 VNĐ","tips":"Check lịch sóng.","recommended":True,
         "legs":[{"step":1,"icon":"🚢","mode":"ferry","label":"Tàu cao tốc Phú Quý","duration":"~2.5h","price_range":"380.000 VNĐ","tips":"Đặt vé trước."}]},
    ],
}

def _find_combined(o: str, d: str) -> list[dict]:
    return _COMBINED_ROUTES.get(frozenset({_norm(o), _norm(d)}), [])

# ────────────────────────────────────────────────────────────────────────────
# 7. BUILD THẺ TÀU (TÍNH LẠI CHUẨN KHOẢNG CÁCH XE TRUNG CHUYỂN TỪ TỌA ĐỘ)
# ────────────────────────────────────────────────────────────────────────────
def _build_train_option(o: str, d: str, dist_str: str, preferred: bool = True) -> Optional[dict]:
    t = _find_train(o, d)
    if not t: return None
    return {
        "label": "Tàu hỏa (Đường sắt Việt Nam)", "type": "train", "duration": t["duration"],
        "price_range": t["price_range"], "distance": dist_str, "ticket_type": "Ngồi mềm/Giường nằm",
        "thumbnail": LOGO_TRAIN, "tips": t["tips"], "recommended": preferred,
    }

def _build_train_via_hub_option(o: str, d: str, dist_str: str) -> Optional[dict]:
    result = _find_train_via_hub(o, d)
    if not result: return None
    t, hub_o, hub_d = result
    po = _get_pinfo(o)
    pd = _get_pinfo(d)
    legs = []
    step = 1
    total_lo = total_hi = 0

    if _norm(o) != hub_o:
        km = po.get("hub_km", 60)
        # Nếu hub tàu khác với hub mặc định (ví dụ Vĩnh Long -> HCM thay vì Cần Thơ)
        if po.get("hub") != hub_o and hub_o != _norm(o):
            dist = _estimate_distance(o, hub_o)
            if dist != 999: km = dist
        lo, hi, ps, ds = _transfer_cost_km(km)
        total_lo += lo; total_hi += hi
        legs.append({"step": step, "icon": "🚗", "mode": "car",
                     "label": f"Xe từ {o.title()} → Ga {hub_o.title()}",
                     "duration": ds, "price_range": ps, "tips": "Di chuyển ra ga.", "distance": f"~{km} km"})
        step += 1

    legs.append({"step": step, "icon": "🚆", "mode": "train",
                 "label": f"Tàu hỏa ({hub_o.title()} → {hub_d.title()})",
                 "duration": t["duration"], "price_range": t["price_range"], "tips": t["tips"], "distance": dist_str})
    step += 1

    if _norm(d) != hub_d:
        km = pd.get("hub_km", 60)
        if pd.get("hub") != hub_d and hub_d != _norm(d):
            dist = _estimate_distance(d, hub_d)
            if dist != 999: km = dist
        lo, hi, ps, ds = _transfer_cost_km(km)
        total_lo += lo; total_hi += hi
        legs.append({"step": step, "icon": "🚗", "mode": "car",
                     "label": f"Xe từ Ga {hub_d.title()} → {d.title()}",
                     "duration": ds, "price_range": ps, "tips": "Về trung tâm địa phương.", "distance": f"~{km} km"})

    t_lo, t_hi = _parse_price_range(t["price_range"])
    total_price = f"{t_lo + total_lo:,}–{t_hi + total_hi:,} VNĐ".replace(",", ".")

    return {
        "label": f"Xe trung chuyển + Tàu hỏa ({hub_o.title()} → {hub_d.title()})",
        "type": "combined", "duration": f"Tàu {t['duration']} + xe",
        "price_range": total_price, "distance": dist_str, "ticket_type": "Giường nằm",
        "thumbnail": LOGO_TRAIN, "tips": "Bao gồm giá xe trung chuyển ước tính.",
        "recommended": False, "legs": legs,
    }

# ────────────────────────────────────────────────────────────────────────────
# 8. BUILD THẺ MÁY BAY
# ────────────────────────────────────────────────────────────────────────────

def _transfer_flight_label(o_iata: str, d_iata: str, needs_origin_transfer: bool, needs_dest_transfer: bool) -> str:
    """
    Tạo tiêu đề đúng theo thứ tự thực tế của hành trình:
      - Đi xe trước rồi bay   → "Xe trung chuyển + Máy bay (HAN → HUI)"
      - Bay đến rồi mới xe    → "Máy bay + Xe trung chuyển (HAN → HUI)"
      - Cả hai đầu đều có xe  → "Xe trung chuyển + Máy bay + Xe trung chuyển (HAN → HUI)"
      - Không có xe           → "Máy bay (HAN → HUI)"
    """
    route = f"({o_iata} → {d_iata})"
    if needs_origin_transfer and needs_dest_transfer:
        return f"Xe trung chuyển + Máy bay + Xe trung chuyển {route}"
    if needs_origin_transfer:
        return f"Xe trung chuyển + Máy bay {route}"
    if needs_dest_transfer:
        return f"Máy bay + Xe trung chuyển {route}"
    return f"Máy bay {route}"
def _build_flight_options(
    o: str, d: str, origin_iata: str, dest_iata: str, real_flights: list,
    needs_origin_transfer: bool, needs_dest_transfer: bool,
    origin_hub_km: int, dest_hub_km: int, dist_str: str,
) -> list[dict]:
    options = []
    if not origin_iata or not dest_iata: return options

    o_iata, d_iata = origin_iata.upper(), dest_iata.upper()
    po, pd = _get_pinfo(o), _get_pinfo(d)

    if real_flights:
        # Trường hợp 3 ngày không có vé — không render thẻ máy bay, bỏ qua
        if len(real_flights) == 1 and real_flights[0].get("no_flights_note"):
            print(f"[Transport] {real_flights[0]['no_flights_note']}")
            return options  # trả về rỗng, không thêm thẻ máy bay

        # Lọc bỏ entry no_flights_note nếu lẫn vào
        valid_flights = [f for f in real_flights if not f.get("no_flights_note") and f.get("price", 0) > 0]

        if not needs_origin_transfer and not needs_dest_transfer:
            for i, f in enumerate(valid_flights[:3]):
                alt_note = f.get("alt_date_note", "")
                tips = f"{f['stops']} • {f['departure']}-{f['arrival']}."
                if alt_note:
                    tips = f"⚠️ {alt_note} | {tips}"
                options.append({
                    "label": f"Máy bay {f['airline']} ({o_iata} → {d_iata})", "type": "flight",
                    "duration": f["duration"], "price_range": f"{int(f['price']):,} VNĐ".replace(",", "."),
                    "distance": dist_str, "ticket_type": f"Hạng {f['ticket_class']}",
                    "thumbnail": f.get("thumbnail", ""), "tips": tips,
                    "recommended": (i == 0),
                    **({"alt_date": f["alt_date"], "alt_date_note": alt_note} if alt_note else {}),
                })
        else:
            for i, f in enumerate(valid_flights[:2]):
                legs = []
                step = 1
                total_extra = 0
                if needs_origin_transfer:
                    lo, hi, ps, ds = _transfer_cost_km(origin_hub_km)
                    total_extra += (lo + hi) // 2
                    legs.append({"step": step, "icon": "🚗", "mode": "car", "label": f"Xe ra sân bay {o_iata}", "duration": ds, "price_range": ps, "tips": "Từ trung tâm.", "distance": f"~{origin_hub_km} km"})
                    step += 1
                legs.append({"step": step, "icon": "✈️", "mode": "flight", "label": f"Bay {f['airline']}", "duration": f["duration"], "price_range": f"{int(f['price']):,} VNĐ".replace(",", "."), "tips": f"{f['departure']} → {f['arrival']}.", "distance": dist_str, "thumbnail": f.get("thumbnail", "")})
                step += 1
                if needs_dest_transfer:
                    lo, hi, ps, ds = _transfer_cost_km(dest_hub_km)
                    total_extra += (lo + hi) // 2
                    legs.append({"step": step, "icon": "🚗", "mode": "car", "label": f"Xe từ {d_iata} về đích", "duration": ds, "price_range": ps, "tips": "Taxi/Grab.", "distance": f"~{dest_hub_km} km"})

                alt_note = f.get("alt_date_note", "")
                options.append({
                    "label": _transfer_flight_label(o_iata, d_iata, needs_origin_transfer, needs_dest_transfer),
                    "type": "combined",
                    "duration": f"Bay {f['duration']} + xe", "price_range": f"~{(int(f['price']) + total_extra):,} VNĐ".replace(",", "."),
                    "distance": dist_str, "ticket_type": f"Hạng {f['ticket_class']}", "thumbnail": f.get("thumbnail", ""),
                    "tips": f"⚠️ {alt_note} | Giá gộp vé và xe." if alt_note else "Giá gộp vé và xe.",
                    "recommended": (i == 0), "legs": legs,
                    **({"alt_date": f["alt_date"], "alt_date_note": alt_note} if alt_note else {}),
                })
    else:
        # Ước tính giá tham khảo theo khoảng cách
        dist_km = _estimate_distance(o, d)
        if dist_km < 300:
            est_price = "400.000–900.000 VNĐ"
            est_duration = "~1 giờ"
        elif dist_km < 600:
            est_price = "600.000–1.500.000 VNĐ"
            est_duration = "~1–1,5 giờ"
        else:
            est_price = "800.000–2.000.000 VNĐ"
            est_duration = "~1,5–2 giờ"

        vj_url  = f"https://www.vietjetair.com/vi/booking?orig={o_iata}&dest={d_iata}"
        vna_url = f"https://www.vietnamairlines.com/vn/vi/booking/book-flight?journeyType=OW&org={o_iata}&des={d_iata}"
        bb_url  = f"https://www.bambooairways.com/vn-vi/dat-ve?departureCode={o_iata}&arrivalCode={d_iata}"

        legs = []
        step = 1
        if needs_origin_transfer:
            lo, hi, ps, ds = _transfer_cost_km(origin_hub_km)
            legs.append({"step": step, "icon": "🚗", "mode": "car",
                         "label": f"Xe ra sân bay {o_iata}",
                         "duration": ds, "price_range": ps, "tips": "Từ trung tâm.",
                         "distance": f"~{origin_hub_km} km"})
            step += 1

        legs.append({"step": step, "icon": "✈️", "mode": "flight",
                     "label": f"Chuyến bay {o_iata} → {d_iata}",
                     "duration": est_duration, "price_range": est_price,
                     "distance": dist_str,
                     "tips": f"Tra vé: VietJet · Vietnam Airlines · Bamboo"})
        step += 1

        if needs_dest_transfer:
            lo, hi, ps, ds = _transfer_cost_km(dest_hub_km)
            legs.append({"step": step, "icon": "🚗", "mode": "car",
                         "label": f"Xe từ {d_iata} về đích",
                         "duration": ds, "price_range": ps, "tips": "Taxi/Grab.",
                         "distance": f"~{dest_hub_km} km"})

        label = _transfer_flight_label(o_iata, d_iata, needs_origin_transfer, needs_dest_transfer)
        options.append({
            "label": label, "type": "flight",
            "duration": est_duration, "price_range": est_price,
            "distance": dist_str, "ticket_type": "Phổ thông",
            "thumbnail": "", "recommended": True, "legs": legs,
            "tips": f"Không lấy được giá thực — giá ước tính. Tra trực tiếp: VietJet ({vj_url}) · VNA ({vna_url}) · Bamboo ({bb_url})",
            "booking_links": [
                {"name": "VietJet Air", "url": vj_url},
                {"name": "Vietnam Airlines", "url": vna_url},
                {"name": "Bamboo Airways", "url": bb_url},
            ],
        })
    return options

# ────────────────────────────────────────────────────────────────────────────
# 9. BUILD THẺ XE KHÁCH / NỘI BỘ
# ────────────────────────────────────────────────────────────────────────────
def _build_bus_option(distance_km: float, driving_duration_text: Optional[str], dist_str: str, preferred: bool = False) -> dict:
    duration = driving_duration_text or _bus_duration(distance_km)
    price_range = _bus_price(distance_km) if distance_km < 900 else "350.000–600.000 VNĐ"

    # Ước tính giờ khởi hành phổ biến theo thời gian hành trình
    hours = distance_km / 60
    if hours <= 5:
        depart_info = "Nhiều chuyến/ngày • Sáng & chiều tối"
    elif hours <= 10:
        depart_info = "Chuyến ban ngày & chuyến đêm"
    else:
        depart_info = "Chủ yếu chuyến đêm (xuất phát 18:00–22:00)"

    # Số điểm dừng nghỉ ước tính
    stops = max(1, int(hours / 4))
    stop_note = f"~{stops} điểm dừng nghỉ dọc đường" if stops > 1 else "~1 điểm dừng nghỉ dọc đường"

    legs = [
        {"step": 1, "icon": "🚌", "mode": "bus",
         "label": "Xe khách giường nằm",
         "duration": duration,
         "price_range": price_range,
         "distance": dist_str,
         "tips": f"{depart_info} • {stop_note}"},
    ]

    return {
        "label": "Xe khách (Phương Trang / Hoàng Long)", "type": "bus",
        "duration": duration,
        "price_range": price_range,
        "distance": dist_str, "ticket_type": "Giường nằm", "thumbnail": LOGO_BUS,
        "tips": f"Đặt vé qua Vexere.com. {depart_info}. {stop_note}.",
        "recommended": preferred, "legs": legs,
    }

def _build_local_options(distance_km: float, dist_str: str) -> list[dict]:
    return [
        {"label": "🚗 Grab / Taxi","type":"local","duration": _bus_duration(distance_km),"price_range": f"~{max(30_000, int(distance_km * 10_000)):,} VNĐ".replace(",","."),"distance":dist_str,"tips":"Grab Car.","recommended":True},
        {"label": "🏍️ Xe máy","type":"local","duration": _bus_duration(distance_km * 0.85),"price_range":"20k-50k Xăng","distance":dist_str,"tips":"Linh hoạt.","recommended":False},
    ]

# ────────────────────────────────────────────────────────────────────────────
# 10. HÀM CHÍNH DECIDE_TRANSPORT
# ────────────────────────────────────────────────────────────────────────────
def _inject_real_flights_into_combined(combined: list[dict], real_flights: list) -> list[dict]:
    if not real_flights: return combined
    res = []
    for card in combined:
        card = copy.deepcopy(card)
        legs = card.get("legs", [])
        flight_idx = 0
        total_p = 0
        has_real = False
        for l in legs:
            if l.get("mode") == "flight" and flight_idx < len(real_flights):
                f = real_flights[flight_idx]
                l["price_range"] = f"{int(f['price']):,} VNĐ".replace(",", ".")
                if f.get("duration"): l["duration"] = f["duration"]
                total_p += int(f["price"])
                has_real = True; flight_idx += 1
        if has_real: card["price_range"] = f"~{total_p:,} VNĐ".replace(",", ".")
        res.append(card)
    return res

def _enforce_4_card_priority(options: list[dict]) -> list[dict]:
    def _is_flight(o): return o.get("type") == "flight" or any(l.get("mode") == "flight" for l in o.get("legs", []))
    def _is_train(o): return o.get("type") == "train" or any(l.get("mode") == "train" for l in o.get("legs", []))
    def _is_bus(o): return o.get("type") == "bus"

    flights = [o for o in options if _is_flight(o) and not _is_train(o)]
    trains  = [o for o in options if _is_train(o)]
    buses   = [o for o in options if _is_bus(o)]
    others  = [o for o in options if not _is_flight(o) and not _is_train(o) and not _is_bus(o)]

    result = flights[:2]
    if trains: result.append(trains[0])
    if buses: result.append(buses[0])
    for i, c in enumerate(result): c["recommended"] = (i == 0)
    
    extras = trains[1:] + buses[1:] + others + flights[2:]
    while len(result) < 4 and extras: result.append(extras.pop(0))
    return result

def decide_transport(origin: str, destination: str, distance_m: Optional[float], driving_duration_text: Optional[str], flight_available: bool, origin_info: dict, dest_info: dict, real_flights: list = None, effective_origin_iata: str = None, effective_dest_iata: str = None) -> dict:
    if real_flights is None: real_flights = []
    distance_km = (distance_m / 1000 if distance_m and distance_m > 10 else _estimate_distance(origin, destination))
    dist_str = f"~{distance_km:.0f} km" if distance_km < 900 else "Hành trình dài"

    # Khoảng cách riêng cho từng phương tiện
    dist_str_flight = dist_str  # Máy bay: khoảng cách chim bay (ngắn nhất)
    road_km = distance_km * 1.25
    dist_str_road = f"~{road_km:.0f} km" if distance_km < 900 else "Hành trình dài"   # Xe/bus: đường bộ ~25% dài hơn
    rail_km = distance_km * 1.3
    dist_str_rail = f"~{rail_km:.0f} km" if distance_km < 900 else "Hành trình dài"   # Tàu: đường ray ~30% dài hơn

    po, pd = _get_pinfo(origin), _get_pinfo(destination)
    origin_iata = effective_origin_iata or origin_info.get("iata") or po.get("iata", "")
    dest_iata   = effective_dest_iata or dest_info.get("iata") or pd.get("iata", "")

    needs_origin_transfer = origin_info.get("no_airport", False) or (not po.get("iata") and po.get("hub"))
    needs_dest_transfer   = dest_info.get("no_airport", False) or (not pd.get("iata") and pd.get("hub"))
    origin_hub_km = po.get("hub_km", 60)
    dest_hub_km   = pd.get("hub_km", 60)

    options = []
    primary_mode, note = "bus", ""

    # 1. HÀNH TRÌNH ĐẢO
    if po.get("island") or pd.get("island") or _is_island(origin) or _is_island(destination):
        c = _find_combined(origin, destination)
        if c: return {"mode": "combined", "distance_km": round(distance_km,1), "options": _inject_real_flights_into_combined(c, real_flights), "note": "Hành trình đảo."}
        options.append({"label":"🚢 Tàu cao tốc","type":"ferry","duration":"Tùy tuyến","price_range":"300.000 VNĐ","tips":"Liên hệ bến tàu","recommended":True})
        return {"mode": "combined", "distance_km": round(distance_km,1), "options": options, "note": "Hành trình đảo."}

    combined = _find_combined(origin, destination)

    # 2. RẤT GẦN (< 50km)
    if distance_km < 50:
        options = _build_local_options(distance_km, dist_str_road)
        note = "Rất gần."
        
    # 3. GẦN (50 - 200km): KHÔNG HIỂN THỊ MÁY BAY NỮA
    elif distance_km < 200:
        if combined: options += combined
        t_opt = _build_train_option(origin, destination, dist_str_rail, preferred=not combined)
        if t_opt: options.append(t_opt)
        else:
            ht_opt = _build_train_via_hub_option(origin, destination, dist_str_rail)
            if ht_opt: options.append(ht_opt)
        
        options.append(_build_bus_option(distance_km, driving_duration_text, dist_str_road))
        note = "Khoảng cách gần — Tàu hỏa hoặc xe khách là tối ưu."

    # 4. TRUNG BÌNH (200 - 500km): ĐƯỢC PHÉP ĐI MÁY BAY
    elif distance_km < 500:
        if combined: options += combined
        t_opt = _build_train_option(origin, destination, dist_str_rail, preferred=not combined)
        if t_opt: options.append(t_opt)
        else:
            ht_opt = _build_train_via_hub_option(origin, destination, dist_str_rail)
            if ht_opt: options.append(ht_opt)
        
        if origin_iata and dest_iata:
            options = _build_flight_options(origin, destination, origin_iata, dest_iata, real_flights, needs_origin_transfer, needs_dest_transfer, origin_hub_km, dest_hub_km, dist_str_flight) + options
        options.append(_build_bus_option(distance_km, driving_duration_text, dist_str_road))
        note = "Khoảng cách trung bình."

    # 5. XA (> 500km): ƯU TIÊN MÁY BAY
    else:
        if origin_iata and dest_iata:
            options += _build_flight_options(origin, destination, origin_iata, dest_iata, real_flights, needs_origin_transfer, needs_dest_transfer, origin_hub_km, dest_hub_km, dist_str_flight)
        if combined: options += combined
        t_opt = _build_train_option(origin, destination, dist_str_rail, preferred=not options)
        if t_opt: options.append(t_opt)
        else:
            ht_opt = _build_train_via_hub_option(origin, destination, dist_str_rail)
            if ht_opt: options.append(ht_opt)
        options.append(_build_bus_option(distance_km, driving_duration_text, dist_str_road))
        note = "Hành trình xa — Ưu tiên máy bay."

    options = _enforce_4_card_priority(options)
    
    return {"mode": "flight" if distance_km > 500 else "train", "distance_km": round(distance_km,1), "options": options, "note": note}

# ────────────────────────────────────────────────────────────────────────────
# 11. HELPER GEO
# ────────────────────────────────────────────────────────────────────────────
_PROVINCE_COORDS: dict[str, tuple[float, float]] = {
    "hà nội":        (21.028, 105.834),   "hải phòng":     (20.844, 106.688),
    "quảng ninh":    (21.006, 107.293),   "hải dương":     (20.940, 106.331),
    "hưng yên":      (20.646, 106.051),   "bắc ninh":      (21.186, 106.076),
    "vĩnh phúc":     (21.361, 105.575),   "phú thọ":       (21.368, 105.201),
    "thái nguyên":   (21.593, 105.848),   "bắc giang":     (21.272, 106.194),
    "lạng sơn":      (21.853, 106.761),   "cao bằng":      (22.666, 106.258),
    "hà giang":      (22.824, 104.984),   "lào cai":       (22.480, 103.975),
    "yên bái":       (21.722, 104.911),   "tuyên quang":   (21.823, 105.218),
    "bắc kạn":       (22.147, 105.834),   "thái bình":     (20.450, 106.342),
    "nam định":      (20.420, 106.168),   "hà nam":        (20.583, 105.920),
    "ninh bình":     (20.258, 105.975),   "hòa bình":      (20.813, 105.338),
    "sơn la":        (21.327, 103.914),   "điện biên":     (21.386, 103.023),
    "lai châu":      (22.396, 103.458),   "thanh hóa":     (19.807, 105.776),
    "vinh":          (18.679, 105.682),   "hà tĩnh":       (18.355, 105.888),
    "quảng bình":    (17.469, 106.600),   "quảng trị":     (16.750, 107.185),
    "huế":           (16.468, 107.596),   "đà nẵng":       (16.054, 108.202),
    "hội an":        (15.880, 108.335),   "quảng nam":     (15.573, 108.474),
    "quảng ngãi":    (15.121, 108.806),   "quy nhơn":      (13.782, 109.219),
    "phú yên":       (13.095, 109.093),   "nha trang":     (12.238, 109.197),
    "ninh thuận":    (11.565, 108.988),   "phan thiết":    (10.928, 108.102),
    "kon tum":       (14.350, 108.000),   "gia lai":       (13.983, 108.000),
    "buôn ma thuột": (12.667, 108.050),   "đắk nông":      (12.000, 107.690),
    "đà lạt":        (11.940, 108.458),   "hồ chí minh":   (10.823, 106.630),
    "bình dương":    (11.164, 106.653),   "đồng nai":      (11.073, 107.167),
    "vũng tàu":      (10.346, 107.084),   "tây ninh":      (11.310, 106.098),
    "bình phước":    (11.752, 106.723),   "long an":       (10.696, 106.243),
    "tiền giang":    (10.360, 106.365),   "bến tre":       (10.243, 106.376),
    "vĩnh long":     (10.240, 105.973),   "trà vinh":      (9.935,  106.345),
    "đồng tháp":     (10.490, 105.688),   "an giang":      (10.522, 105.126),
    "kiên giang":    (10.012, 105.080),   "phú quốc":      (10.289, 103.984),
    "cần thơ":       (10.045, 105.747),   "hậu giang":     (9.757,  105.641),
    "sóc trăng":     (9.602,  105.980),   "bạc liêu":      (9.285,  105.727),
    "cà mau":        (9.177,  105.150),   "côn đảo":       (8.683,  106.617),
    "lý sơn":        (15.374, 109.121),   "cù lao chàm":   (15.944, 108.519),
    "phú quý":       (10.517, 108.933),   "cát bà":        (20.728, 107.047),
    "cô tô":         (20.980, 107.770),   "bạch long vĩ":  (20.133, 107.717),
}

def _haversine(lat1, lon1, lat2, lon2) -> float:
    import math
    R = 6371
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)) * 1.3

def _estimate_distance(o: str, d: str) -> float:
    ko, kd = _norm(o), _norm(d)
    co, cd = _PROVINCE_COORDS.get(ko), _PROVINCE_COORDS.get(kd)
    if co and cd:
        return _haversine(co[0], co[1], cd[0], cd[1])
    t = _find_train(o, d)
    if t:
        m = re.search(r'~(\d+)', t["duration"])
        if m:
            h = int(m.group(1))
            return h * 60  
    return 999  

def _is_island(place: str) -> bool:
    _ISLAND_KEYWORDS = ["phú quốc","côn đảo","lý sơn","cù lao chàm","phú quý",
                        "bạch long vĩ","cô tô","cát bà","vân đồn","thổ chu"]
    p = place.lower().strip()
    return any(k in p for k in _ISLAND_KEYWORDS)

# ────────────────────────────────────────────────────────────────────────────
# BACKWARD COMPAT:
# ────────────────────────────────────────────────────────────────────────────
def _suggest_nearest_airport_drive(destination: str) -> dict:
    pd = _get_pinfo(destination)
    if pd.get("hub"):
        hub = pd["hub"]
        km  = pd.get("hub_km", 60)
        return {
            "airport":    f"Sân bay {hub.title()}",
            "drive_time": f"~{max(1,round(km/50))} giờ",
            "drive_cost": f"~{max(50_000,int(km*2_000/1_000)*1_000):,}–{max(80_000,int(km*3_000/1_000)*1_000):,} VNĐ".replace(",", "."),
            "tips": f"Xe khách / Grab từ {destination.title()} ra sân bay {hub.title()}.",
        }
    return {"airport":"Sân bay gần nhất","drive_time":"Tùy vị trí","drive_cost":"Liên hệ tài xế","tips":"Hỏi khách sạn về xe đưa đón sân bay."}

def get_hotel_coords_fallback(hotel_name, location, api_key):
    return None, None