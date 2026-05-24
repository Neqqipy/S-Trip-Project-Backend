# 🌍 S-Trip Backend · AI Travel Planner

**Backend API cho ứng dụng lên kế hoạch du lịch thông minh với AI**

Dự án: **SMART TOURISM SYSTEM** | Môn học: **CTT009 - COMPUTATIONAL THINKING**

Được xây dựng bằng **Flask**, tích hợp **Google Maps**, **SerpAPI**, **Gemini AI**, và **Supabase**.

---

## 🚀 Quick Start - Hướng dẫn nhanh

### 1️⃣ Cài đặt Python & Pip

Đảm bảo máy bạn có **Python 3.8+** (tải từ [python.org](https://www.python.org/downloads/))

```bash
# Kiểm tra version
python --version
```

### 2️⃣ Clone & Setup Environment

```bash
# Clone project
git clone <repository-url>
cd Backend

# Tạo virtual environment (cô lập dependencies)
python -m venv venv

# Kích hoạt virtual environment
# Trên Windows:
venv\Scripts\activate
# Trên macOS/Linux:
source venv/bin/activate
```

### 3️⃣ Cài đặt Dependencies

```bash
# Cài Python packages từ requirements.txt
pip install -r requirements.txt

# (Nếu cần) Cài Node packages
npm install
```

### 4️⃣ Cấu hình Environment Variables

```bash
# Copy template thành file thực
cp .env.example .env
```

Mở file `.env` và điền các API keys (hướng dẫn lấy keys ở bên dưới 👇)

### 5️⃣ Khởi động Server

```bash
python main.py

# ✅ Server chạy tại http://localhost:5000
# Test: curl http://localhost:5000/
```

---

## 📁 Cấu trúc thư mục & Chức năng file

### 🔧 Core Files

| File | Chức năng |
|------|----------|
| **main.py** | Entry point chính - định nghĩa tất cả Flask routes |
| **requirements.txt** | Danh sách Python dependencies (pip install) |
| **package.json** | Node.js dependencies (npm install) |
| **.env** | Environment variables - **KHÔNG commit lên Git** |
| **.env.example** | Template cho .env - **hướng dẫn điền keys** |

### 🛫 Service Modules (Core Logic)

| File | Chức năng | Dependencies |
|------|----------|---------|
| **flight_services.py** | Tìm chuyến bay, giải phóng IATA airports, kiểm tra route | SerpAPI, requests |
| **hotel_services.py** | Đề xuất khách sạn theo ngân sách, địa điểm, ngày | SerpAPI, requests |
| **direction_service.py** | Tính khoảng cách & thời gian (driving, transit, walking) | SerpAPI |
| **transport_service.py** | Quyết định phương tiện tối ưu (máy bay/xe) | Logic từ flight/hotel/direction |
| **weather_service.py** | Lấy dữ liệu thời tiết theo địa điểm | SerpAPI, OpenWeather API |
| **itinerary_builder.py** | Xây dựng lịch trình chi tiết theo ngày/buổi | Logic scheduling |
| **ThuatToanDeXuat.py** | Thuật toán gợi ý thông minh (recommendation) | numpy/pandas nếu có |
| **auth_routes.py** | OAuth Google, Supabase auth, session management | authlib, supabase |
| **gemini_intent.py** | Intent recognition & AI processing | google-generativeai |

### 📸 Utility Modules

| File | Chức năng |
|------|----------|
| **Photo.py** | Xử lý ảnh từ SerpAPI, proxy images |
| **Maps_service.py** | Helpers cho Google Maps embed URLs |

### 💾 Data Files (Local Cache)

| File | Chức năng |
|------|----------|
| **saved_places_db.json** | Cache địa điểm yêu thích (JSON local) |
| **hotel_img_cache.json** | Cache ảnh khách sạn (tránh re-fetch) |

---

## 🔑 Environment Variables (.env)

### Cách tạo .env

```bash
cp .env.example .env
```

Sau đó mở `.env` và điền các keys (xem hướng dẫn bên dưới)

### 📋 Các biến cần cấu hình

#### Flask & Server
```
SECRET_KEY=your_secret_here           # Session secret (tạo random 32 bytes)
FLASK_ENV=development                 # development hoặc production
HTTPS=false                            # true nếu HTTPS (Codespaces/Deploy)
```

#### Frontend CORS
```
FRONTEND_URL=http://localhost:3000    # URL frontend dev
```

#### AI & APIs
```
GEMINI_API_KEY=AIzaSy...              # Google Gemini
SERPAPI_KEY=45d84e6f3c...             # SerpAPI (Google Search/Maps)
GOOGLE_MAPS_API_KEY=AIzaSy...         # Google Maps Embed API
OPENWEATHER_KEY=3ec67bda...           # OpenWeather (thời tiết)
```

#### Database & Auth
```
SUPABASE_URL=https://xxx.supabase.co  # Supabase project URL
SUPABASE_SERVICE_ROLE_KEY=sb_secret...# Service role key

GOOGLE_CLIENT_ID=222656962799-...     # Google OAuth
GOOGLE_CLIENT_SECRET=GOCSPX-...       # Google OAuth
```

#### Email (tùy chọn)
```
MAIL_EMAIL=your@gmail.com             # Gmail hoặc email khác
MAIL_PASSWORD=password                # App password (không password chính)
```

---

## 🔐 Hướng dẫn lấy API Keys

### 1️⃣ **Google Gemini** (AI Chat)

1. Vào [ai.google.dev](https://ai.google.dev)
2. Nhấn **"Get API Key"** → **"Create API key in new project"**
3. Sao chép key → Dán vào `.env`:
   ```
   GEMINI_API_KEY=AIzaSy...
   ```

### 2️⃣ **SerpAPI** (Google Search/Maps)

1. Đăng ký tại [serpapi.com](https://serpapi.com)
2. Vào Dashboard → Copy API key
3. Dán vào `.env`:
   ```
   SERPAPI_KEY=45d84e6f3c...
   ```

### 3️⃣ **Google Maps API**

1. Vào [Google Cloud Console](https://console.cloud.google.com)
2. Tạo project mới → Chọn project
3. Vào **APIs & Services** → **Credentials**
4. Bật **Maps Embed API** (Enable APIs and Services)
5. Tạo **API Key** (Create Credentials → API Key)
6. Dán vào `.env`:
   ```
   GOOGLE_MAPS_API_KEY=AIzaSy...
   ```

### 4️⃣ **Supabase** (Database)

1. Vào [supabase.com](https://supabase.com) → Sign up
2. Tạo **New Project**
3. Vào **Settings** → **API** → Copy:
   - `PROJECT_URL` → `SUPABASE_URL`
   - `service_role` (bấm "Reveal") → `SUPABASE_SERVICE_ROLE_KEY`
4. Dán vào `.env`:
   ```
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=sb_secret...
   ```

### 5️⃣ **Google OAuth** (Đăng nhập)

1. Vào [Google Cloud Console](https://console.cloud.google.com)
2. **OAuth consent screen** → Configure
3. **Credentials** → **Create OAuth 2.0 Client ID** (Web application)
4. Authorized redirect URIs: `http://localhost:5000/auth/callback`
5. Download JSON → Lấy Client ID & Secret
6. Dán vào `.env`:
   ```
   GOOGLE_CLIENT_ID=222656962799-...
   GOOGLE_CLIENT_SECRET=GOCSPX-...
   ```

### 6️⃣ **OpenWeather API** (Thời tiết - tùy chọn)

1. Vào [openweathermap.org](https://openweathermap.org/api)
2. Sign up → API keys
3. Dán vào `.env`:
   ```
   OPENWEATHER_KEY=3ec67bda...
   ```

---

## 💾 Database Setup (Supabase)

Tạo các bảng này trong **Supabase SQL Editor**:

### Trips (Lưu lịch trình)
```sql
CREATE TABLE trips (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    location TEXT,
    origin TEXT,
    days INT DEFAULT 3,
    start_date TEXT,
    plan JSONB DEFAULT '{}',
    daily_plans JSONB DEFAULT '[]',
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
);
CREATE INDEX idx_trips_user_id ON trips(user_id);
```

### Search History (Lịch sử tìm kiếm)
```sql
CREATE TABLE search_history (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    location TEXT,
    origin TEXT,
    budget INT,
    days INT,
    passengers INT,
    departure_date TEXT,
    searched_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
);
CREATE INDEX idx_search_history_user_id ON search_history(user_id);
```

### Saved Places (Địa điểm yêu thích)
```sql
CREATE TABLE saved_places (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    location TEXT DEFAULT '',
    rating TEXT DEFAULT '',
    thumbnail TEXT DEFAULT '',
    type TEXT DEFAULT 'default',
    saved_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
);
CREATE INDEX idx_saved_places_user_id ON saved_places(user_id);
```

---

## 📡 API Endpoints

### 🗺️ Travel Planning
- `GET /api/plan-trip?location=Đà+Lạt&origin=TPHCM&budget=5000000&days=3` → Plan đầy đủ
- `GET /api/activities?location=Đà+Lạt&type=Quán+cà+phê` → Danh sách hoạt động
- `GET /api/directions?origin=TPHCM&destination=Đà+Lạt` → Khoảng cách & thời gian

### 🌡️ Thông tin địa điểm
- `GET /api/weather?location=Đà+Lạt` → Thời tiết
- `GET /api/reviews?place=Địa+điểm` → Reviews
- `GET /api/images?place=Địa+điểm` → Ảnh
- `GET /api/province-images?place=Đà+Lạt` → Ảnh tỉnh thành

### 🗺️ Maps
- `GET /api/map-embed-url?place_id=ChIJ...` → URL nhúng iframe
- `GET /api/static-map?lat=10.8&lng=106.6` → Ảnh bản đồ

### 👤 User Features (cần đăng nhập)
- `POST /api/trip/save` → Lưu lịch trình
- `GET /api/my-trips` → Danh sách lịch trình
- `GET /api/search-history` → Lịch sử tìm kiếm
- `POST /api/saved-places` → Lưu địa điểm yêu thích
- `GET /api/saved-places` → Lấy danh sách yêu thích

### 🤖 AI Features
- `POST /api/chat-gemini` → Chat với AI
- `GET /api/ai-specialties-tips?location=Đà+Lạt` → Gợi ý đặc sản

---

## 🛠️ Development & Testing

### Chạy với Debug Mode
```python
# Trong main.py (dòng cuối cùng):
app.run(port=5000, debug=True)  # Hot reload enabled
```

### Test Endpoints với curl

```bash
# ✅ Health check
curl http://localhost:5000/

# ✅ Plan trip
curl "http://localhost:5000/api/plan-trip?location=Đà+Lạt&budget=5000000"

# ✅ Thời tiết
curl "http://localhost:5000/api/weather?location=Đà+Lạt"

# ✅ AI tips
curl "http://localhost:5000/api/ai-specialties-tips?location=Đà+Lạt"
```

### Test với Postman
1. Import Postman Collection (nếu có)
2. Set environment variables
3. Run requests

---

## 📦 Dependencies

### Python Packages (requirements.txt)
```
flask==3.0.0                # Web framework
flask-cors==4.0.0          # CORS support
python-dotenv==1.0.0       # .env loader
google-generativeai==0.8.3 # Gemini AI
google-search-results      # SerpAPI client
bcrypt                     # Password hashing
authlib                    # OAuth
supabase                   # Supabase Python client
```

### Node Packages (package.json)
```
puppeteer-core^25.0.4      # Headless browser
```

---

## 🚀 Deployment

### Heroku
```bash
# Tạo runtime.txt
echo "python-3.11.5" > runtime.txt

# Tạo Procfile
echo "web: python main.py" > Procfile

# Push
git add .
git commit -m "Deploy to Heroku"
git push heroku main
```

### Railway / Render
1. Connect GitHub repo
2. Set environment variables trong dashboard
3. Auto-deploy on push

### GitHub Codespaces
```bash
# Set trong .env:
HTTPS=true
FRONTEND_URL=https://your-username-3000.app.github.dev
```

---

## 🐛 Troubleshooting

| Lỗi | Giải pháp |
|-----|----------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| `SERPAPI_KEY` không hoạt động | Kiểm tra key hợp lệ tại serpapi.com |
| CORS error | Kiểm tra `FRONTEND_URL` trong `.env` |
| Supabase connection failed | Kiểm tra URL & Service Role Key |
| Port 5000 đã dùng | `python main.py --port 5001` |

---

## 📚 Tài liệu thêm

- [Flask Documentation](https://flask.palletsprojects.com/)
- [SerpAPI Docs](https://serpapi.com/docs)
- [Google Gemini](https://ai.google.dev/docs)
- [Supabase](https://supabase.com/docs)

---

**Tác giả:** S-Trip Development Team  
**License:** MIT  
**Contact:** Hãy tạo issue hoặc liên hệ support

---

**Last Updated:** 2026-05-25