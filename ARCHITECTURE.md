# 📁 S-Trip Backend - Chi tiết Cấu Trúc File

## 🎯 Overview

```
Backend/
├── main.py                          # Entry point Flask app
├── requirements.txt                 # Python dependencies
├── package.json                     # Node dependencies
├── README.md                        # Setup guide (bạn đang đọc)
├── .env.example                     # Template environment variables
├── .env                             # Actual config (⚠️ .gitignore)
│
├── 🛫 SERVICE MODULES
│   ├── flight_services.py           # ✈️ Chuyến bay
│   ├── hotel_services.py            # 🏨 Khách sạn
│   ├── direction_service.py         # 🗺️ Hướng dẫn & khoảng cách
│   ├── transport_service.py         # 🚗 Phương tiện di chuyển
│   ├── weather_service.py           # 🌤️ Thời tiết
│   ├── itinerary_builder.py         # 📅 Xây dựng lịch trình
│   ├── ThuatToanDeXuat.py           # 🧠 Thuật toán gợi ý
│   └── auth_routes.py               # 🔓 OAuth & authentication
│
├── 🎨 UTILITY MODULES
│   ├── Photo.py                     # 📸 Xử lý ảnh
│   ├── Maps_service.py              # 🗺️ Google Maps helper
│
└── 💾 DATA FILES
    ├── hotel_img_cache.json         # Cache ảnh khách sạn
    └── __pycache__/                 # Compiled Python (.gitignore)
```

---

## 📊 File Details

### 🔴 MAIN FILES (Bắt buộc)

#### **main.py** (1600+ lines)
- **Chức năng chính:**
  - Khởi tạo Flask app
  - CORS configuration cho frontend
  - Session management (30 days)
  - OAuth initialization

- **Key Routes:**
  - `GET /` → Health check
  - `GET /api/plan-trip` → Main travel planner endpoint
  - `POST /api/chat-gemini` → AI chat
  - `GET /api/reviews` → Place reviews
  - `POST /api/trip/save` → Save itinerary to Supabase
  - `GET /api/saved-places` → Favorite places

- **Key Functions:**
  - `get_real_activities()` → Fetch from Google Local via SerpAPI
  - `_guess_best_time()` → Recommend best time (morning/afternoon/evening)
  - `to_proxy_url()` → Convert Google image URLs to proxy endpoints
  - `proxy_image()` → Image proxy with caching

- **Imports:**
  ```python
  from flight_services import get_smart_flight_recommendations
  from hotel_services import get_smart_hotel_recommendations
  from direction_service import get_all_modes_directions
  from transport_service import decide_transport
  from auth_routes import auth_bp, init_oauth
  from itinerary_builder import build_itinerary
  from ThuatToanDeXuat import apply_recommendation_algorithm
  ```

---

#### **requirements.txt**
Định nghĩa Python packages:

```
flask==3.0.0                          # Web framework
flask-cors==4.0.0                     # CORS support
python-dotenv==1.0.0                  # Load .env variables
google-generativeai==0.8.3            # Gemini AI
google-search-results==2.4.2          # SerpAPI wrapper
bcrypt                                # Password hashing
authlib                               # OAuth library
supabase                              # Supabase Python client
```

**Cài đặt:**
```bash
pip install -r requirements.txt
```

---

#### **package.json**
Node.js dependencies:

```json
{
  "dependencies": {
    "puppeteer-core": "^25.0.4"       // Headless browser (nếu cần)
  }
}
```

**Cài đặt:**
```bash
npm install
```

---

#### **.env.example** (140+ lines)
Template cho environment variables với:
- Hướng dẫn điền từng key
- API endpoints để lấy keys
- Chia thành sections (Flask, APIs, Database, OAuth, Email)
- Checklist bắt buộc vs optional

**Dùng:**
```bash
cp .env.example .env
# Mở .env và điền các giá trị
```

---

### 🛫 SERVICE MODULES

#### **flight_services.py**
Xử lý tìm kiếm và gợi ý chuyến bay

**Key Functions:**
- `get_smart_flight_recommendations(api_key, origin, dest, budget, days, passengers, departure_date)`
  - Tìm chuyến bay từ SerpAPI
  - Lọc theo ngân sách
  - Trả về danh sách với giá, thời gian, hãng

- `resolve_airport(location)`
  - Map tỉnh/thành phố → IATA code
  - Trả về: `{"iata": "SGN", "note": "..."}`
  - VD: "TP. Hồ Chí Minh" → "SGN"

- `get_effective_iata(origin_iata, dest_iata)`
  - Tìm hub trung gian nếu cần
  - VD: "Bạc Liêu" (CAH) → "SGN" (hub) → "DAD"

- `is_route_operated(origin_iata, dest_iata)`
  - Kiểm tra route có chuyến bay không

**Cấu trúc Return:**
```python
{
    "airline": "Vietnam Airlines",
    "price": "2,500,000 VND",
    "departure_time": "14:00",
    "arrival_time": "15:30",
    "duration": "1h 30m",
    "stops": 0
}
```

---

#### **hotel_services.py**
Đề xuất khách sạn theo ngân sách & location

**Key Functions:**
- `get_smart_hotel_recommendations(api_key, location, budget, days, passengers, departure_date, tours=[], foods=[])`
  - Tìm khách sạn từ SerpAPI
  - Lọc theo budget (budget/num_days)
  - Ưu tiên gần trung tâm (dựa vào tọa độ tours + foods)
  - Trả về: name, rating, price, thumbnail, lat/lng

**Cấu trúc Return:**
```python
{
    "name": "Dalat Palace Heritage Hotel",
    "rating": "4.5",
    "price": "500,000 - 800,000 VND/night",
    "thumbnail": "/api/proxy-image?url=...",
    "lat": 10.912,
    "lng": 106.932,
    "review_count": 245
}
```

---

#### **direction_service.py**
Tính khoảng cách & thời gian giữa 2 điểm

**Key Functions:**
- `get_all_modes_directions(api_key, origin, destination)`
  - Trả về: driving, transit, walking
  - Mỗi mode có: distance_m, distance_text, duration_s, duration_text

**Cấu trúc Return:**
```python
{
    "driving": {
        "distance_m": 312000,
        "distance_text": "312 km",
        "duration_s": 18720,
        "duration_text": "5h 12m"
    },
    "transit": { ... },
    "walking": { ... }
}
```

---

#### **transport_service.py**
Quyết định phương tiện tối ưu

**Key Functions:**
- `decide_transport(origin, destination, distance_m, flight_available, real_flights, ...)`
  - Logic:
    - `distance_m > 150km` + `flight_available` → Gợi ý bay
    - `distance_m < 150km` → Gợi ý xe
    - Trả về: type, duration, price, tips

**Cấu trúc Return:**
```python
[
    {
        "type": "flight",
        "title": "✈️ Máy bay (nhanh nhất)",
        "duration": "1h 30m",
        "price": "2,500,000 VND",
        "best_for": "Di chuyển nhanh, xa"
    },
    {
        "type": "car",
        "title": "🚗 Xe (linh hoạt)",
        "duration": "5h 12m",
        "price": "1,000,000 VND"
    }
]
```

---

#### **weather_service.py**
Lấy thông tin thời tiết

**Key Functions:**
- `get_weather(api_key, location, lang="vi")`
  - Lấy từ SerpAPI weather engine
  - Trả về: temperature, condition, humidity, wind_speed

**Cấu trúc Return:**
```python
{
    "success": True,
    "location": "Đà Lạt",
    "temperature": "22°C",
    "condition": "Mây nhẹ",
    "humidity": "75%",
    "wind_speed": "5 km/h"
}
```

---

#### **itinerary_builder.py**
Xây dựng lịch trình chi tiết theo ngày/buổi

**Key Functions:**
- `build_itinerary(hotels, tours, foods, num_days)`
  - Chia tour, food theo buổi (morning/afternoon/evening)
  - Gán vào từng ngày theo logic
  - Trả về: danh sách activities theo ngày

**Cấu trúc Return:**
```python
[
    {
        "day": 1,
        "date": "2026-06-01",
        "activities": [
            {
                "slot": "🌅 Buổi sáng",
                "items": [{"name": "...", "type": "tour"}]
            },
            {
                "slot": "☀️ Buổi chiều",
                "items": [...]
            }
        ]
    }
]
```

---

#### **ThuatToanDeXuat.py**
Thuật toán gợi ý & ranking

**Key Functions:**
- `apply_recommendation_algorithm(hotels, tours, foods, budget)`
  - Ranking/filtering dựa trên:
    - Budget constraints
    - Rating & popularity
    - Distance from center
  - Trả về: hotels, tours, foods (sorted & filtered)

---

#### **auth_routes.py**
Quản lý authentication

**Key Functions:**
- `init_oauth(app)` → Khởi tạo Google OAuth
- Routes:
  - `GET /auth/login` → Redirect to Google
  - `GET /auth/callback` → OAuth callback
  - `GET /auth/logout` → Logout

**Session Management:**
- Store `user_id` in Flask session
- 30 days persistent session
- HttpOnly cookies (CSRF safe)

---

### 🎨 UTILITY MODULES

#### **Photo.py**
Xử lý ảnh từ SerpAPI

**Key Functions:**
- Image URL validation
- Proxy URL generation
- Fallback placeholders

---

#### **Maps_service.py**
Google Maps helpers

**Key Functions:**
- Generate embed URLs
- Static map URLs
- Place ID processing

---

#### **gemini_intent.py**
AI Intent Recognition (tùy chọn)

**Chức năng:**
- Parse user messages
- Extract intent (search, save, share)
- Prepare data for AI processing

---

### 💾 DATA FILES

#### **saved_places_db.json**
Local JSON cache cho địa điểm yêu thích
```json
{
  "user_id": [
    {
      "id": 1,
      "name": "Đà Lạt",
      "rating": 4.5,
      "saved_at": 1234567890
    }
  ]
}
```

#### **hotel_img_cache.json**
Cache ảnh khách sạn (tránh re-fetch từ SerpAPI)
```json
{
  "hotel_name_location": "https://cached-image-url.jpg",
  ...
}
```

---

## 🔗 Dependencies Flow

```
main.py
├── flight_services.py
│   └── SerpAPI (flights search)
├── hotel_services.py
│   └── SerpAPI (hotels search)
├── direction_service.py
│   └── SerpAPI (directions)
├── transport_service.py
│   ├── flight_services output
│   ├── hotel_services output
│   └── direction_service output
├── itinerary_builder.py
│   ├── hotels + tours + foods
│   └── Time slot assignment
├── ThuatToanDeXuat.py
│   └── Ranking & filtering
├── auth_routes.py
│   ├── Google OAuth
│   └── Supabase auth
└── weather_service.py
    └── SerpAPI (weather)
```

---

## 📝 Adding New Features

### Example: Thêm endpoint mới

1. **Tạo function trong service module:**
   ```python
   # new_feature.py
   def get_something(api_key, param):
       # Logic here
       return result
   ```

2. **Import & Route trong main.py:**
   ```python
   from new_feature import get_something
   
   @app.route("/api/new-endpoint")
   def new_endpoint():
       result = get_something(SERPAPI_KEY, param)
       return jsonify(result)
   ```

3. **Test:**
   ```bash
   curl http://localhost:5000/api/new-endpoint
   ```

---

## ✅ Testing Checklist

- [ ] `.env` filled with all required keys
- [ ] `pip install -r requirements.txt` completed
- [ ] `python main.py` runs without errors
- [ ] `http://localhost:5000/` returns health check
- [ ] API endpoints respond (use curl or Postman)
- [ ] Database connected (check Supabase logs)

---

**Version:** 1.0.0  
**Last Updated:** 2026-05-25  
**Maintainer:** S-Trip Team
