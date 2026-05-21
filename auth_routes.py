# auth_routes.py
# ================================================================
# 🔐 AUTH + SCHEDULE + PROFILE — Blueprint Flask (Supabase)
# ================================================================
#
# Bảng cần tạo trên Supabase (SQL Editor):
#
# CREATE TABLE users (
#     id            BIGSERIAL PRIMARY KEY,
#     email         TEXT UNIQUE NOT NULL,
#     password_hash TEXT,
#     name          TEXT NOT NULL DEFAULT '',
#     avatar        TEXT DEFAULT '',
#     google_id     TEXT UNIQUE,
#     created_at    TIMESTAMPTZ DEFAULT NOW()
# );
#
# CREATE TABLE schedules (
#     id         BIGSERIAL PRIMARY KEY,
#     user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#     title      TEXT NOT NULL DEFAULT 'Lịch trình',
#     location   TEXT NOT NULL DEFAULT '',
#     days       INT  NOT NULL DEFAULT 3,
#     data_json  JSONB NOT NULL DEFAULT '{}',
#     created_at TIMESTAMPTZ DEFAULT NOW(),
#     updated_at TIMESTAMPTZ DEFAULT NOW()
# );
# CREATE INDEX idx_schedules_user_id ON schedules(user_id);
#
# CREATE TABLE favorites (
#     id         BIGSERIAL PRIMARY KEY,
#     user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#     name       TEXT NOT NULL,
#     location   TEXT DEFAULT '',
#     rating     TEXT DEFAULT '',
#     thumbnail  TEXT DEFAULT '',
#     type       TEXT DEFAULT 'default',
#     created_at TIMESTAMPTZ DEFAULT NOW()
# );
# CREATE INDEX idx_favorites_user_id ON favorites(user_id);
#
# ================================================================

import os, bcrypt, json, time
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from werkzeug.utils import secure_filename
from supabase import create_client, Client as SupabaseClient

auth_bp = Blueprint("auth", __name__)

# ----------------------------------------------------------------
# ⚙️ CONFIG
# ----------------------------------------------------------------
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Thư mục lưu avatar local (fallback khi chưa có cloud storage)
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "avatars")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------------------
# 🔌 SUPABASE CLIENT
# ----------------------------------------------------------------
_sb: SupabaseClient | None = None

def get_sb() -> SupabaseClient:
    global _sb
    if _sb is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_KEY")
        _sb = create_client(url, key)
    return _sb

# ----------------------------------------------------------------
# 🔧 HELPER
# ----------------------------------------------------------------
def _user_to_dict(user: dict) -> dict:
    return {
        "id":         user["id"],
        "email":      user["email"],
        "name":       user["name"],
        "avatar":     user.get("avatar") or "",
        "google_id":  user.get("google_id") or "",
        "created_at": str(user.get("created_at") or ""),
    }

def login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
        return f(*args, **kwargs)
    return decorated

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ----------------------------------------------------------------
# 🔑 EMAIL / PASSWORD AUTH
# ----------------------------------------------------------------

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data     = request.get_json() or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name     = (data.get("name") or "").strip()

    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Email không hợp lệ"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu phải ít nhất 6 ký tự"}), 400
    if not name:
        return jsonify({"success": False, "error": "Vui lòng nhập tên"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        sb  = get_sb()
        # Kiểm tra email đã tồn tại chưa
        existing = sb.table("users").select("id").eq("email", email).execute()
        if existing.data:
            return jsonify({"success": False, "error": "Email đã được sử dụng"}), 409

        res = sb.table("users").insert({
            "email": email, "password_hash": pw_hash, "name": name
        }).execute()
        user = res.data[0]

        session["user_id"] = user["id"]
        session.permanent  = True
        return jsonify({"success": True, "user": _user_to_dict(user)})

    except Exception as e:
        print(f"[register] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json() or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ thông tin"}), 400

    try:
        sb   = get_sb()
        res  = sb.table("users").select("*").eq("email", email).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Email hoặc mật khẩu không đúng"}), 401

        user = res.data[0]
        if not user.get("password_hash"):
            return jsonify({"success": False, "error": "Tài khoản này dùng đăng nhập Google"}), 401

        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return jsonify({"success": False, "error": "Email hoặc mật khẩu không đúng"}), 401

        session["user_id"] = user["id"]
        session.permanent  = True
        return jsonify({"success": True, "user": _user_to_dict(user)})

    except Exception as e:
        print(f"[login] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "user": None})
    try:
        sb  = get_sb()
        res = sb.table("users").select("*").eq("id", user_id).execute()
        if not res.data:
            session.clear()
            return jsonify({"success": False, "user": None})
        return jsonify({"success": True, "user": _user_to_dict(res.data[0])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ----------------------------------------------------------------
# 🌐 GOOGLE OAUTH
# ----------------------------------------------------------------
_oauth_instance = None

def init_oauth(app):
    global _oauth_instance
    _oauth_instance = OAuth(app)
    _oauth_instance.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    print("✅ Google OAuth khởi tạo OK")
    return _oauth_instance

@auth_bp.route("/api/auth/google")
def google_login():
    if not _oauth_instance:
        return jsonify({"error": "OAuth chưa được khởi tạo"}), 500
    redirect_uri = url_for("auth.google_callback", _external=True)
    session["next_url"] = request.args.get("next", FRONTEND_URL)
    return _oauth_instance.google.authorize_redirect(redirect_uri)

@auth_bp.route("/api/auth/google/callback")
def google_callback():
    if not _oauth_instance:
        return redirect(f"{FRONTEND_URL}?auth_error=oauth_not_init")
    try:
        token     = _oauth_instance.google.authorize_access_token()
        user_info = token.get("userinfo") or _oauth_instance.google.userinfo()

        email     = (user_info.get("email") or "").lower()
        name      = user_info.get("name") or email.split("@")[0]
        avatar    = user_info.get("picture") or ""
        google_id = user_info.get("sub") or ""

        if not email:
            return redirect(f"{FRONTEND_URL}?auth_error=no_email")

        sb = get_sb()
        existing = sb.table("users").select("*").eq("email", email).execute()

        if existing.data:
            user = existing.data[0]
            if not user.get("google_id"):
                sb.table("users").update({"google_id": google_id, "avatar": avatar}).eq("id", user["id"]).execute()
            user_id = user["id"]
        else:
            res = sb.table("users").insert({
                "email": email, "name": name, "avatar": avatar, "google_id": google_id
            }).execute()
            user_id = res.data[0]["id"]

        session["user_id"] = user_id
        session.permanent  = True
        next_url = session.pop("next_url", FRONTEND_URL)
        return redirect(f"{next_url}?auth_success=1")

    except Exception as e:
        print(f"[Google OAuth Error] {e}")
        return redirect(f"{FRONTEND_URL}?auth_error=oauth_failed")


# ----------------------------------------------------------------
# 💾 SCHEDULE API
# ----------------------------------------------------------------

@auth_bp.route("/api/schedules", methods=["GET"])
@login_required_api
def get_schedules():
    user_id = session["user_id"]
    try:
        sb  = get_sb()
        res = sb.table("schedules").select("id,title,location,days,data_json,created_at,updated_at").eq("user_id", user_id).order("updated_at", desc=True).execute()
        return jsonify({"success": True, "schedules": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/schedules/<int:schedule_id>", methods=["GET"])
@login_required_api
def get_schedule(schedule_id):
    user_id = session["user_id"]
    try:
        sb  = get_sb()
        res = sb.table("schedules").select("*").eq("id", schedule_id).eq("user_id", user_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy"}), 404
        return jsonify({"success": True, "schedule": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/schedules/save", methods=["POST"])
@login_required_api
def save_schedule():
    user_id = session["user_id"]
    data    = request.get_json() or {}

    schedule_id = data.get("id")
    title       = (data.get("title") or "").strip() or "Lịch trình"
    location    = (data.get("location") or "").strip()
    days        = int(data.get("days") or 3)
    data_json   = data.get("data_json") or {}
    now         = _now_iso()

    if not location:
        return jsonify({"success": False, "error": "Thiếu thông tin điểm đến"}), 400

    try:
        sb = get_sb()
        if schedule_id:
            existing = sb.table("schedules").select("id").eq("id", schedule_id).eq("user_id", user_id).execute()
            if not existing.data:
                return jsonify({"success": False, "error": "Không tìm thấy lịch trình"}), 404
            sb.table("schedules").update({
                "title": title, "location": location, "days": days,
                "data_json": data_json, "updated_at": now
            }).eq("id", schedule_id).eq("user_id", user_id).execute()
            return jsonify({"success": True, "id": schedule_id, "action": "updated"})
        else:
            res = sb.table("schedules").insert({
                "user_id": user_id, "title": title, "location": location,
                "days": days, "data_json": data_json,
                "created_at": now, "updated_at": now
            }).execute()
            return jsonify({"success": True, "id": res.data[0]["id"], "action": "created"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
@login_required_api
def delete_schedule(schedule_id):
    user_id = session["user_id"]
    try:
        sb  = get_sb()
        res = sb.table("schedules").delete().eq("id", schedule_id).eq("user_id", user_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# 👤 ACCOUNT SETTINGS API
# ================================================================

@auth_bp.route("/api/auth/update-avatar", methods=["POST"])
@login_required_api
def update_avatar():
    if 'avatar' not in request.files:
        return jsonify({"success": False, "error": "Không tìm thấy file"}), 400

    file = request.files['avatar']
    if file.filename == '':
        return jsonify({"success": False, "error": "Chưa chọn file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Chỉ chấp nhận file ảnh (png, jpg, jpeg, gif, webp)"}), 400

    user_id  = session["user_id"]
    filename = secure_filename(f"user_{user_id}_{file.filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    avatar_url = f"{request.host_url}static/avatars/{filename}"

    try:
        sb  = get_sb()
        sb.table("users").update({"avatar": avatar_url}).eq("id", user_id).execute()
        res = sb.table("users").select("*").eq("id", user_id).execute()
        return jsonify({"success": True, "user": _user_to_dict(res.data[0])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/update-profile", methods=["POST"])
@login_required_api
def update_profile():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Tên không được để trống"}), 400

    user_id = session["user_id"]
    try:
        sb  = get_sb()
        sb.table("users").update({"name": name}).eq("id", user_id).execute()
        res = sb.table("users").select("*").eq("id", user_id).execute()
        return jsonify({"success": True, "user": _user_to_dict(res.data[0])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/change-password", methods=["POST"])
@login_required_api
def change_password():
    data       = request.get_json() or {}
    current_pw = data.get("current_password") or ""
    new_pw     = data.get("new_password") or ""
    user_id    = session["user_id"]

    if len(new_pw) < 6:
        return jsonify({"success": False, "error": "Mật khẩu mới phải ít nhất 6 ký tự"}), 400

    try:
        sb   = get_sb()
        res  = sb.table("users").select("password_hash").eq("id", user_id).execute()
        user = res.data[0]

        if not user.get("password_hash"):
            return jsonify({"success": False, "error": "Tài khoản Google không thể đổi mật khẩu"}), 400
        if not bcrypt.checkpw(current_pw.encode(), user["password_hash"].encode()):
            return jsonify({"success": False, "error": "Mật khẩu hiện tại không đúng"}), 400

        new_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        sb.table("users").update({"password_hash": new_hash}).eq("id", user_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# ❤️ FAVORITES API
# ================================================================

@auth_bp.route("/api/favorites", methods=["GET"])
@login_required_api
def get_favorites():
    user_id = session["user_id"]
    try:
        sb  = get_sb()
        res = sb.table("favorites").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return jsonify({"success": True, "favorites": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/favorites", methods=["POST"])
@login_required_api
def add_favorite():
    user_id   = session["user_id"]
    data      = request.get_json() or {}
    name      = (data.get("name") or "").strip()
    location  = (data.get("location") or "").strip()
    rating    = str(data.get("rating") or "")
    thumbnail = (data.get("thumbnail") or "").strip()
    fav_type  = (data.get("type") or "default").strip()

    if not name:
        return jsonify({"success": False, "error": "Thiếu tên địa điểm"}), 400

    try:
        sb = get_sb()
        existing = sb.table("favorites").select("id").eq("user_id", user_id).eq("name", name).eq("location", location).execute()
        if existing.data:
            return jsonify({"success": True, "id": existing.data[0]["id"], "duplicate": True})

        res = sb.table("favorites").insert({
            "user_id": user_id, "name": name, "location": location,
            "rating": rating, "thumbnail": thumbnail, "type": fav_type
        }).execute()
        return jsonify({"success": True, "id": res.data[0]["id"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/favorites/<int:fav_id>", methods=["DELETE"])
@login_required_api
def delete_favorite(fav_id):
    user_id = session["user_id"]
    try:
        get_sb().table("favorites").delete().eq("id", fav_id).eq("user_id", user_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/favorites/remove-by-name", methods=["POST"])
@login_required_api
def remove_favorite_by_name():
    user_id  = session["user_id"]
    data     = request.get_json() or {}
    name     = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip()
    try:
        get_sb().table("favorites").delete().eq("user_id", user_id).eq("name", name).eq("location", location).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# 🔍 SEARCH HISTORY API
# ================================================================

@auth_bp.route("/api/search-history", methods=["GET"])
@login_required_api
def get_search_history():
    user_id = session["user_id"]
    try:
        sb  = get_sb()
        res = sb.table("search_history").select("*").eq("user_id", str(user_id)).order("searched_at", desc=True).limit(20).execute()
        return jsonify({"success": True, "history": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/search-history", methods=["POST"])
@login_required_api
def add_search_history():
    user_id  = session["user_id"]
    data     = request.get_json() or {}
    location = (data.get("location") or "").strip()

    if not location:
        return jsonify({"success": False, "error": "Thiếu điểm đến"}), 400

    try:
        sb  = get_sb()
        res = sb.table("search_history").insert({
            "user_id":        str(user_id),
            "location":       location,
            "origin":         data.get("origin", ""),
            "budget":         int(data.get("budget", 0)),
            "days":           int(data.get("days", 3)),
            "passengers":     int(data.get("passengers", 1)),
            "departure_date": data.get("departure_date", ""),
            "searched_at":    int(time.time()),
        }).execute()
        return jsonify({"success": True, "id": res.data[0]["id"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/search-history/<int:history_id>", methods=["DELETE"])
@login_required_api
def delete_search_history(history_id):
    user_id = session["user_id"]
    try:
        get_sb().table("search_history").delete().eq("id", history_id).eq("user_id", str(user_id)).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/search-history/clear", methods=["DELETE"])
@login_required_api
def clear_search_history():
    user_id = session["user_id"]
    try:
        get_sb().table("search_history").delete().eq("user_id", str(user_id)).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500