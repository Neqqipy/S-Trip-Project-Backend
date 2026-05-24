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

import os, bcrypt, json, time, secrets, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from supabase import create_client, Client as SupabaseClient

auth_bp = Blueprint("auth", __name__)

# ----------------------------------------------------------------
# ⚙️ CONFIG
# ----------------------------------------------------------------
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:3000")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------------------
# 🔌 SUPABASE CLIENT — dùng service role key
# ----------------------------------------------------------------
# Kiến trúc: Browser → Flask (kiểm tra session) → Supabase
# Flask đã là người gác cổng nên dùng service role key để bypass RLS,
# không cần tự ký JWT thủ công.
# Lấy service role key tại: Supabase Dashboard → Settings → API → service_role
# ----------------------------------------------------------------
_sb: SupabaseClient | None = None

def get_sb(user_id=None) -> SupabaseClient:
    """
    Trả Supabase client dùng service role key.
    Tham số user_id giữ lại để tương thích với code cũ, không dùng nữa.
    """
    global _sb
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY")
    if _sb is None:
        _sb = create_client(url, key)
    return _sb

# ----------------------------------------------------------------
# 🔧 HELPER
# ----------------------------------------------------------------
def _user_to_dict(user: dict) -> dict:
    return {
        "id":         user["id"],
        "username":   user.get("username") or "",
        "email":      user["email"],
        "name":       user["name"],
        "avatar":     user.get("avatar") or "",
        "google_id":  user.get("google_id") or "",
        "role":       user.get("role") or "user",
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
    username = (data.get("username") or "").strip().lower()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name     = (data.get("name") or "").strip()

    if not username:
        return jsonify({"success": False, "error": "Vui lòng nhập tên đăng nhập"}), 400
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Email không hợp lệ"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu phải ít nhất 6 ký tự"}), 400
    if not name:
        return jsonify({"success": False, "error": "Vui lòng nhập tên hiển thị"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        sb  = get_sb()
        # Kiểm tra username đã tồn tại chưa
        existing_user = sb.table("users").select("id").eq("username", username).execute()
        if existing_user.data:
            return jsonify({"success": False, "error": "Tên đăng nhập đã được sử dụng"}), 409
        # Kiểm tra email đã tồn tại chưa
        existing_email = sb.table("users").select("id").eq("email", email).execute()
        if existing_email.data:
            return jsonify({"success": False, "error": "Email đã được sử dụng"}), 409

        # Tạo token xác nhận email
        verify_token      = secrets.token_urlsafe(32)
        verify_expires_at = int(time.time()) + 24 * 3600  # 24 giờ

        res = sb.table("users").insert({
            "username": username, "email": email, "password_hash": pw_hash, "name": name,
            "email_verified": False,
            "verify_token": verify_token,
            "verify_token_expires": verify_expires_at,
        }).execute()
        user = res.data[0]

        # Gửi email xác nhận (chạy trong try riêng để không block đăng ký nếu mail lỗi)
        email_sent = True
        try:
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            _send_verification_email(email, verify_token, frontend_url)
        except Exception as mail_err:
            email_sent = False
            print(f"[register] Gửi email xác nhận thất bại: {mail_err}")

        # KHÔNG tạo session — yêu cầu xác nhận email trước
        return jsonify({"success": True, "pending_verification": True, "email": email, "email_sent": email_sent})

    except Exception as e:
        print(f"[register] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ thông tin"}), 400

    try:
        sb   = get_sb()
        res  = sb.table("users").select("*").eq("username", username).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Tên đăng nhập hoặc mật khẩu không đúng"}), 401

        user = res.data[0]
        if not user.get("password_hash"):
            return jsonify({"success": False, "error": "Tài khoản này chưa đặt mật khẩu"}), 401

        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return jsonify({"success": False, "error": "Tên đăng nhập hoặc mật khẩu không đúng"}), 401

        # Chặn đăng nhập nếu email chưa được xác nhận
        if not user.get("email_verified", True):  # True là fallback cho tài khoản cũ chưa có field
            return jsonify({"success": False, "error": "Chưa xác nhận email", "pending_verification": True, "email": user.get("email", "")}), 403

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


@auth_bp.route("/api/auth/delete-account", methods=["DELETE"])
@login_required_api
def delete_account():
    """
    Xóa vĩnh viễn tài khoản và toàn bộ dữ liệu liên quan.
    Vì bảng users có ON DELETE CASCADE nên schedules, favorites,
    saved_places, search_history... sẽ bị xóa theo tự động.
    """
    user_id = session["user_id"]
    try:
        sb  = get_sb()
        res = sb.table("users").delete().eq("id", user_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy tài khoản"}), 404
        session.clear()
        return jsonify({"success": True, "message": "Tài khoản đã được xóa vĩnh viễn"})
    except Exception as e:
        print(f"[delete_account] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "user": None})
    try:
        sb  = get_sb(user_id)
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

    # Dùng BACKEND_URL từ .env thay vì url_for()
    # → tránh sai URL khi chạy trên Codespaces / reverse proxy
    backend_url  = os.getenv("BACKEND_URL", "http://localhost:5000")
    redirect_uri = f"{backend_url}/api/auth/google/callback"
    print(f"🔍 redirect_uri: {redirect_uri}")

    return _oauth_instance.google.authorize_redirect(
        redirect_uri,
        prompt="select_account"
    )

@auth_bp.route("/api/auth/google/callback")
def google_callback():
    if not _oauth_instance:
        return redirect(f"{FRONTEND_URL}/#/?auth_error=oauth_not_init")
    try:
        token     = _oauth_instance.google.authorize_access_token()
        user_info = token.get("userinfo") or _oauth_instance.google.userinfo()

        email     = (user_info.get("email") or "").lower()
        name      = user_info.get("name") or email.split("@")[0]
        avatar    = user_info.get("picture") or ""
        google_id = user_info.get("sub") or ""

        if not email:
            return redirect(f"{FRONTEND_URL}/#/?auth_error=no_email")

        sb = get_sb()
        existing = sb.table("users").select("*").eq("email", email).execute()

        if existing.data:
            user = existing.data[0]
            user_id = user["id"]
            update_data = {}
            if not user.get("google_id"):
                update_data["google_id"] = google_id
            if not user.get("avatar") and avatar:
                update_data["avatar"] = avatar
            # Đảm bảo user Google luôn được coi là đã xác nhận email
            if not user.get("email_verified"):
                update_data["email_verified"] = True
            if update_data:
                sb.table("users").update(update_data).eq("id", user_id).execute()
        else:
            # Tạo username tự động từ email (phần trước @), đảm bảo unique
            base_username = email.split("@")[0].lower()
            base_username = "".join(c for c in base_username if c.isalnum() or c == "_")[:20]
            username_candidate = base_username
            suffix = 1
            while True:
                check = sb.table("users").select("id").eq("username", username_candidate).execute()
                if not check.data:
                    break
                username_candidate = f"{base_username}{suffix}"
                suffix += 1

            res = sb.table("users").insert({
                "email":          email,
                "name":           name,
                "avatar":         avatar,
                "google_id":      google_id,
                "username":       username_candidate,
                "email_verified": True,   # Google đã xác thực email rồi
            }).execute()
            user_id = res.data[0]["id"]

        session["user_id"] = user_id
        session.permanent  = True

        # Lấy user data mới nhất để nhúng vào URL cho React dùng luôn
        # (tránh phụ thuộc cookie cross-port khi dùng proxy)
        fresh = sb.table("users").select("*").eq("id", user_id).execute().data[0]
        user_payload = {
            "id":        fresh["id"],
            "email":     fresh["email"],
            "name":      fresh["name"],
            "avatar":    fresh.get("avatar") or "",
            "google_id": fresh.get("google_id") or "",
            "username":  fresh.get("username") or "",
            "role":      fresh.get("role") or "user",
        }
        import urllib.parse, json as _json
        encoded = urllib.parse.quote(_json.dumps(user_payload, ensure_ascii=False), safe="")
        return redirect(f"{FRONTEND_URL}/#/?auth_success=1&user={encoded}")

    except Exception as e:
        print(f"[Google OAuth Error] {e}")
        return redirect(f"{FRONTEND_URL}/#/?auth_error=oauth_failed")


# ----------------------------------------------------------------
# 💾 SCHEDULE API
# ----------------------------------------------------------------

@auth_bp.route("/api/schedules", methods=["GET"])
@login_required_api
def get_schedules():
    user_id = session["user_id"]
    try:
        sb  = get_sb(user_id)
        res = sb.table("schedules").select("id,title,location,days,data_json,created_at,updated_at").eq("user_id", user_id).order("updated_at", desc=True).execute()
        return jsonify({"success": True, "schedules": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/schedules/<int:schedule_id>", methods=["GET"])
@login_required_api
def get_schedule(schedule_id):
    user_id = session["user_id"]
    try:
        sb  = get_sb(user_id)
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
        sb = get_sb(user_id)
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
        sb  = get_sb(user_id)
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

    user_id   = session["user_id"]
    ext       = file.filename.rsplit('.', 1)[1].lower()
    filename  = f"avatars/user_{user_id}.{ext}"  # ghi đè file cũ luôn
    file_bytes = file.read()

    try:
        sb = get_sb(user_id)

        # Upload lên Supabase Storage bucket "avatars" (tạo bucket này trong Dashboard nếu chưa có)
        sb.storage.from_("avatars").upload(
            filename,
            file_bytes,
            {"content-type": file.content_type or f"image/{ext}", "upsert": "true"},
        )

        # Lấy public URL
        avatar_url = sb.storage.from_("avatars").get_public_url(filename)

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
        sb  = get_sb(user_id)
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
        sb   = get_sb(user_id)
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
        sb  = get_sb(user_id)
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
        sb = get_sb(user_id)
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
        get_sb(user_id).table("favorites").delete().eq("id", fav_id).eq("user_id", user_id).execute()
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
        get_sb(user_id).table("favorites").delete().eq("user_id", user_id).eq("name", name).eq("location", location).execute()
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
        sb  = get_sb(user_id)
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
        sb  = get_sb(user_id)
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
        get_sb(user_id).table("search_history").delete().eq("id", history_id).eq("user_id", str(user_id)).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/search-history/clear", methods=["DELETE"])
@login_required_api
def clear_search_history():
    user_id = session["user_id"]
    try:
        get_sb(user_id).table("search_history").delete().eq("user_id", str(user_id)).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ================================================================
# 🔑 FORGOT / RESET PASSWORD
# ================================================================
# Cần thêm vào Supabase SQL Editor:
#
# CREATE TABLE password_reset_tokens (
#     id         BIGSERIAL PRIMARY KEY,
#     email      TEXT NOT NULL,
#     token      TEXT NOT NULL UNIQUE,
#     expires_at BIGINT NOT NULL,
#     used       BOOLEAN DEFAULT FALSE,
#     created_at TIMESTAMPTZ DEFAULT NOW()
# );
# ================================================================

def _send_reset_email(to_email: str, token: str, frontend_url: str):
    """Gửi email chứa link reset mật khẩu qua Gmail."""
    mail_user = os.getenv("MAIL_EMAIL", "")
    mail_pass = os.getenv("MAIL_PASSWORD", "")
    if not mail_user or not mail_pass:
        raise RuntimeError("Thiếu MAIL_EMAIL hoặc MAIL_PASSWORD trong .env")

    reset_link = f"{frontend_url}/#/reset-password?token={token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[S-Trip] Đặt lại mật khẩu của bạn"
    msg["From"]    = f"S-Trip <{mail_user}>"
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:40px 30px;background:#f9fafb;border-radius:16px;">
      <div style="text-align:center;">
        <div style="display:inline-flex;align-items:center;gap:10px;margin-bottom:20px;">
          <img src="https://glghrxqpowifcofofsfg.supabase.co/storage/v1/object/public/assets/S.jpg" style="width:44px;height:44px;border-radius:50%;object-fit:cover;vertical-align:middle;" alt="S-Trip"/>
          <h2 style="color:#10b981;margin:0;font-size:24px;line-height:44px;">S-Trip</h2>
        </div>
        <h3 style="color:#111827;margin:0 0 12px;">Đặt lại mật khẩu</h3>
        <p style="color:#374151;margin:0 0 20px;">Bấm nút bên dưới để đặt lại mật khẩu (hiệu lực <strong>15 phút</strong>):</p>
        <a href="{reset_link}" style="background:#10b981;color:white;padding:14px 36px;border-radius:999px;text-decoration:none;font-weight:800;font-size:17px;display:inline-block;margin-bottom:20px;">Đặt lại mật khẩu</a>
        <p style="color:#9ca3af;font-size:12px;margin:0;">© S-Trip — Khám phá Việt Nam</p>
      </div>
    </div>
    """

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(mail_user, mail_pass)
        server.sendmail(mail_user, to_email, msg.as_string())


def _send_verification_email(to_email: str, token: str, frontend_url: str):
    """Gửi email xác nhận tài khoản sau khi đăng ký."""
    mail_user = os.getenv("MAIL_EMAIL", "")
    mail_pass = os.getenv("MAIL_PASSWORD", "")
    if not mail_user or not mail_pass:
        raise RuntimeError("Thiếu MAIL_EMAIL hoặc MAIL_PASSWORD trong .env")

    verify_link = f"{frontend_url}/#/verify-email?token={token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[S-Trip] Xác nhận địa chỉ email của bạn"
    msg["From"]    = f"S-Trip <{mail_user}>"
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:40px 30px;background:#f9fafb;border-radius:16px;">
      <div style="text-align:center;">
        <div style="display:inline-flex;align-items:center;gap:10px;margin-bottom:20px;">
          <img src="https://glghrxqpowifcofofsfg.supabase.co/storage/v1/object/public/assets/S.jpg" style="width:44px;height:44px;border-radius:50%;object-fit:cover;vertical-align:middle;" alt="S-Trip"/>
          <h2 style="color:#10b981;margin:0;font-size:24px;line-height:44px;">S-Trip</h2>
        </div>
        <h3 style="color:#111827;margin:0 0 12px;">Xác nhận email của bạn</h3>
        <p style="color:#374151;margin:0 0 20px;">Bấm nút bên dưới để xác nhận địa chỉ email và kích hoạt tài khoản (hiệu lực <strong>24 giờ</strong>):</p>
        <a href="{verify_link}" style="background:#10b981;color:white;padding:14px 36px;border-radius:999px;text-decoration:none;font-weight:800;font-size:17px;display:inline-block;margin-bottom:20px;">Xác nhận email</a>
        <p style="color:#6b7280;font-size:13px;margin:0 0 8px;">Nếu bạn không đăng ký S-Trip, hãy bỏ qua email này.</p>
        <p style="color:#9ca3af;font-size:12px;margin:0;">© S-Trip — Khám phá Việt Nam</p>
      </div>
    </div>
    """

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(mail_user, mail_pass)
        server.sendmail(mail_user, to_email, msg.as_string())


@auth_bp.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    data  = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Email không hợp lệ"}), 400

    try:
        sb = get_sb()

        # Kiểm tra email có tồn tại không
        res = sb.table("users").select("id,email").eq("email", email).execute()
        if not res.data:
            # Không báo lỗi rõ để tránh dò email — vẫn trả success
            return jsonify({"success": True})

        # Tạo token ngẫu nhiên, hết hạn sau 15 phút
        token      = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 15 * 60

        # Lưu token vào DB
        sb.table("password_reset_tokens").insert({
            "email":      email,
            "token":      token,
            "expires_at": expires_at,
            "used":       False,
        }).execute()

        # Gửi email
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        _send_reset_email(email, token, frontend_url)

        return jsonify({"success": True})

    except Exception as e:
        print(f"[forgot_password] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data         = request.get_json() or {}
    token        = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""

    if not token:
        return jsonify({"success": False, "error": "Token không hợp lệ"}), 400
    if len(new_password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu phải ít nhất 6 ký tự"}), 400

    try:
        sb = get_sb()

        # Tìm token
        res = sb.table("password_reset_tokens").select("*").eq("token", token).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Link không hợp lệ hoặc đã hết hạn"}), 400

        record = res.data[0]

        if record["used"]:
            return jsonify({"success": False, "error": "Link này đã được sử dụng rồi"}), 400
        if int(time.time()) > record["expires_at"]:
            return jsonify({"success": False, "error": "Link đã hết hạn, vui lòng yêu cầu lại"}), 400

        # Cập nhật mật khẩu mới
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        sb.table("users").update({"password_hash": new_hash}).eq("email", record["email"]).execute()

        # Đánh dấu token đã dùng
        sb.table("password_reset_tokens").update({"used": True}).eq("token", token).execute()

        return jsonify({"success": True, "message": "Đặt lại mật khẩu thành công"})

    except Exception as e:
        print(f"[reset_password] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# ✉️ EMAIL VERIFICATION
# ================================================================
# Cần thêm vào Supabase SQL Editor:
#
# ALTER TABLE users
#   ADD COLUMN IF NOT EXISTS email_verified      BOOLEAN   DEFAULT TRUE,
#   ADD COLUMN IF NOT EXISTS verify_token        TEXT      DEFAULT NULL,
#   ADD COLUMN IF NOT EXISTS verify_token_expires BIGINT   DEFAULT NULL;
# -- Lưu ý: DEFAULT TRUE giúp các tài khoản cũ (trước khi thêm tính năng) không bị chặn login
# ================================================================

@auth_bp.route("/api/auth/verify-email", methods=["POST"])
def verify_email():
    data  = request.get_json() or {}
    token = (data.get("token") or "").strip()

    if not token:
        return jsonify({"success": False, "error": "Token không hợp lệ"}), 400

    try:
        sb = get_sb()

        # Tìm user có verify_token khớp — token bị xóa sau khi dùng nên không tìm thấy = đã dùng rồi
        res = sb.table("users").select("id,email,email_verified,verify_token_expires").eq("verify_token", token).execute()

        if not res.data:
            # Token không tồn tại: có thể đã xác nhận thành công trước đó (token bị xóa),
            # hoặc token hoàn toàn sai. Không phân biệt được → trả lỗi chung.
            return jsonify({"success": False, "error": "Link xác nhận không hợp lệ hoặc đã được sử dụng. Nếu bạn đã xác nhận rồi, hãy đăng nhập bình thường."}), 400

        user = res.data[0]

        # Guard: trường hợp token còn trong DB nhưng email đã verified (race condition)
        if user.get("email_verified"):
            # Xóa token thừa cho sạch
            sb.table("users").update({"verify_token": None, "verify_token_expires": None}).eq("id", user["id"]).execute()
            return jsonify({"success": True, "already_verified": True, "message": "Email của bạn đã được xác nhận trước đó."})

        expires = user.get("verify_token_expires")
        if expires and int(time.time()) > expires:
            return jsonify({"success": False, "error": "Link xác nhận đã hết hạn (24h). Vui lòng yêu cầu gửi lại.", "expired": True}), 400

        # Xác nhận email — xóa token ngay để không thể dùng lại
        sb.table("users").update({
            "email_verified":       True,
            "verify_token":         None,
            "verify_token_expires": None,
        }).eq("id", user["id"]).execute()

        # Tự động đăng nhập sau khi xác nhận
        session["user_id"] = user["id"]
        session.permanent  = True

        full_user = sb.table("users").select("*").eq("id", user["id"]).execute().data[0]
        return jsonify({"success": True, "user": _user_to_dict(full_user)})

    except Exception as e:
        print(f"[verify_email] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/api/auth/resend-verification", methods=["POST"])
def resend_verification():
    data  = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Email không hợp lệ"}), 400

    try:
        sb  = get_sb()
        res = sb.table("users").select("id,email_verified").eq("email", email).execute()
        if not res.data:
            # Không tiết lộ email có tồn tại không
            return jsonify({"success": True})

        user = res.data[0]
        if user.get("email_verified"):
            return jsonify({"success": False, "error": "Email này đã được xác nhận rồi"}), 400

        new_token   = secrets.token_urlsafe(32)
        new_expires = int(time.time()) + 24 * 3600

        sb.table("users").update({
            "verify_token":         new_token,
            "verify_token_expires": new_expires,
        }).eq("id", user["id"]).execute()

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        _send_verification_email(email, new_token, frontend_url)

        return jsonify({"success": True})

    except Exception as e:
        print(f"[resend_verification] Lỗi: {e}")
        return jsonify({"success": False, "error": str(e)}), 500