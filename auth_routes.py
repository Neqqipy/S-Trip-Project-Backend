# auth_routes.py
# ================================================================
# 🔐 AUTH + SCHEDULE + PROFILE — Blueprint Flask
# ================================================================

import os, sqlite3, bcrypt, json, secrets
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from werkzeug.utils import secure_filename

auth_bp = Blueprint("auth", __name__)

# ----------------------------------------------------------------
# ⚙️ CONFIG
# ----------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "strip.db")

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# URL frontend React (đổi khi deploy)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Thư mục lưu avatar
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "avatars")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Định dạng file ảnh được phép upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------------------
# 🗄️ KHỞI TẠO DATABASE
# ----------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Tạo bảng nếu chưa có. Gọi khi app khởi động."""
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT    UNIQUE NOT NULL,
                password_hash TEXT,
                name         TEXT    NOT NULL DEFAULT '',
                avatar       TEXT    DEFAULT '',
                google_id    TEXT    UNIQUE,
                created_at   TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title        TEXT    NOT NULL DEFAULT 'Lịch trình',
                location     TEXT    NOT NULL DEFAULT '',
                days         INTEGER NOT NULL DEFAULT 3,
                data_json    TEXT    NOT NULL DEFAULT '{}',
                created_at   TEXT    DEFAULT (datetime('now')),
                updated_at   TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS favorites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name        TEXT    NOT NULL,
                location    TEXT    DEFAULT '',
                rating      TEXT    DEFAULT '',
                thumbnail   TEXT    DEFAULT '',
                type        TEXT    DEFAULT 'default',
                created_at  TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS search_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                origin      TEXT    NOT NULL,
                destination TEXT    NOT NULL,
                days        INTEGER DEFAULT 0,
                passengers  INTEGER DEFAULT 1,
                searched_at TEXT    DEFAULT (datetime('now'))
            );
        """)
    print("✅ Database khởi tạo OK →", DB_PATH)

# Tự động init khi import
init_db()

# ----------------------------------------------------------------
# 🔧 HELPER
# ----------------------------------------------------------------
def _user_to_dict(user):
    """Chuyển sqlite3.Row thành dict an toàn (không có password_hash)."""
    return {
        "id":         user["id"],
        "email":      user["email"],
        "name":       user["name"],
        "avatar":     user["avatar"] or "",
        "created_at": user["created_at"],
    }

def login_required_api(f):
    """Decorator — trả 401 nếu chưa đăng nhập."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
        return f(*args, **kwargs)
    return decorated

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
        with get_db() as db:
            cur = db.execute(
                "INSERT INTO users (email, password_hash, name) VALUES (?,?,?)",
                (email, pw_hash, name)
            )
            user_id = cur.lastrowid
            user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

        session["user_id"] = user_id
        session.permanent  = True
        return jsonify({"success": True, "user": _user_to_dict(user)})

    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Email đã được sử dụng"}), 409

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json() or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ thông tin"}), 400

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

    if not user or not user["password_hash"]:
        return jsonify({"success": False, "error": "Email hoặc mật khẩu không đúng"}), 401

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"success": False, "error": "Email hoặc mật khẩu không đúng"}), 401

    session["user_id"] = user["id"]
    session.permanent  = True
    return jsonify({"success": True, "user": _user_to_dict(user)})

@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "user": None})

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    if not user:
        session.clear()
        return jsonify({"success": False, "user": None})

    return jsonify({"success": True, "user": _user_to_dict(user)})

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
        return jsonify({"error": "OAuth chưa được khởi tạo. Gọi init_oauth(app) trong main.py"}), 500
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

        with get_db() as db:
            existing = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

            if existing:
                if not existing["google_id"]:
                    db.execute(
                        "UPDATE users SET google_id=?, avatar=? WHERE id=?",
                        (google_id, avatar, existing["id"])
                    )
                    db.commit()
                user_id = existing["id"]
            else:
                cur = db.execute(
                    "INSERT INTO users (email, name, avatar, google_id) VALUES (?,?,?,?)",
                    (email, name, avatar, google_id)
                )
                user_id = cur.lastrowid

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
    with get_db() as db:
        rows = db.execute(
            """SELECT id, title, location, days, data_json, created_at, updated_at
               FROM schedules WHERE user_id=? ORDER BY updated_at DESC""",
            (user_id,)
        ).fetchall()
    schedules = []
    for r in rows:
        item = dict(r)
        try:
            item["data_json"] = json.loads(item["data_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            item["data_json"] = {}
        schedules.append(item)
    return jsonify({"success": True, "schedules": schedules})

@auth_bp.route("/api/schedules/<int:schedule_id>", methods=["GET"])
@login_required_api
def get_schedule(schedule_id):
    user_id = session["user_id"]
    with get_db() as db:
        row = db.execute("SELECT * FROM schedules WHERE id=? AND user_id=?", (schedule_id, user_id)).fetchone()
    if not row:
        return jsonify({"success": False, "error": "Không tìm thấy"}), 404
    result = dict(row)
    result["data_json"] = json.loads(result["data_json"] or "{}")
    return jsonify({"success": True, "schedule": result})

@auth_bp.route("/api/schedules/save", methods=["POST"])
@login_required_api
def save_schedule():
    user_id = session["user_id"]
    data    = request.get_json() or {}

    schedule_id = data.get("id")
    title       = (data.get("title") or "").strip() or "Lịch trình"
    location    = (data.get("location") or "").strip()
    days        = int(data.get("days") or 3)
    data_json   = json.dumps(data.get("data_json") or {}, ensure_ascii=False)
    now         = datetime.utcnow().isoformat()

    if not location:
        return jsonify({"success": False, "error": "Thiếu thông tin điểm đến"}), 400

    with get_db() as db:
        if schedule_id:
            existing = db.execute("SELECT id FROM schedules WHERE id=? AND user_id=?",(schedule_id, user_id)).fetchone()
            if not existing:
                return jsonify({"success": False, "error": "Không tìm thấy lịch trình"}), 404

            db.execute(
                "UPDATE schedules SET title=?, location=?, days=?, data_json=?, updated_at=? WHERE id=? AND user_id=?",
                (title, location, days, data_json, now, schedule_id, user_id)
            )
            return jsonify({"success": True, "id": schedule_id, "action": "updated"})
        else:
            cur = db.execute(
                "INSERT INTO schedules (user_id, title, location, days, data_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (user_id, title, location, days, data_json, now, now)
            )
            return jsonify({"success": True, "id": cur.lastrowid, "action": "created"})

@auth_bp.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
@login_required_api
def delete_schedule(schedule_id):
    user_id = session["user_id"]
    with get_db() as db:
        result = db.execute("DELETE FROM schedules WHERE id=? AND user_id=?", (schedule_id, user_id))
    if result.rowcount == 0:
        return jsonify({"success": False, "error": "Không tìm thấy"}), 404
    return jsonify({"success": True})


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

    # [FIX 2] Validate định dạng file ảnh
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Chỉ chấp nhận file ảnh (png, jpg, jpeg, gif, webp)"}), 400

    user_id = session["user_id"]
    filename = secure_filename(f"user_{user_id}_{file.filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # [FIX 3] Dùng full URL để frontend React có thể load ảnh đúng
    avatar_url = f"{request.host_url}static/avatars/{filename}"

    with get_db() as db:
        db.execute("UPDATE users SET avatar=? WHERE id=?", (avatar_url, user_id))
        db.commit()  # [FIX 1] Commit để lưu thay đổi vào DB
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    return jsonify({"success": True, "user": _user_to_dict(user)})

@auth_bp.route("/api/auth/update-profile", methods=["POST"])
@login_required_api
def update_profile():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"success": False, "error": "Tên không được để trống"}), 400

    user_id = session["user_id"]
    with get_db() as db:
        db.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))
        db.commit()  # [FIX 1] Commit để lưu thay đổi vào DB
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    return jsonify({"success": True, "user": _user_to_dict(user)})

@auth_bp.route("/api/auth/change-password", methods=["POST"])
@login_required_api
def change_password():
    data = request.get_json() or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    user_id = session["user_id"]

    if len(new_pw) < 6:
        return jsonify({"success": False, "error": "Mật khẩu mới phải ít nhất 6 ký tự"}), 400

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

        if not user["password_hash"]:
            return jsonify({"success": False, "error": "Tài khoản Google không thể đổi mật khẩu"}), 400

        if not bcrypt.checkpw(current_pw.encode(), user["password_hash"].encode()):
            return jsonify({"success": False, "error": "Mật khẩu hiện tại không đúng"}), 400

        new_pw_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_pw_hash, user_id))
        db.commit()  # [FIX 1] Commit để lưu thay đổi vào DB

    return jsonify({"success": True})


# ================================================================
# ❤️ FAVORITES API
# ================================================================

@auth_bp.route("/api/favorites", methods=["GET"])
@login_required_api
def get_favorites():
    user_id = session["user_id"]
    with get_db() as db:
        rows = db.execute("SELECT * FROM favorites WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    return jsonify({"success": True, "favorites": [dict(r) for r in rows]})

@auth_bp.route("/api/favorites", methods=["POST"])
@login_required_api
def add_favorite():
    user_id = session["user_id"]
    data = request.get_json() or {}
    name      = (data.get("name") or "").strip()
    location  = (data.get("location") or "").strip()
    rating    = str(data.get("rating") or "")
    thumbnail = (data.get("thumbnail") or "").strip()
    fav_type  = (data.get("type") or "default").strip()

    if not name:
        return jsonify({"success": False, "error": "Thiếu tên địa điểm"}), 400

    with get_db() as db:
        # Kiểm tra trùng lặp
        existing = db.execute(
            "SELECT id FROM favorites WHERE user_id=? AND name=? AND location=?",
            (user_id, name, location)
        ).fetchone()
        if existing:
            return jsonify({"success": True, "id": existing["id"], "duplicate": True})

        cur = db.execute(
            "INSERT INTO favorites (user_id, name, location, rating, thumbnail, type) VALUES (?,?,?,?,?,?)",
            (user_id, name, location, rating, thumbnail, fav_type)
        )
        return jsonify({"success": True, "id": cur.lastrowid})

@auth_bp.route("/api/favorites/<int:fav_id>", methods=["DELETE"])
@login_required_api
def delete_favorite(fav_id):
    user_id = session["user_id"]
    with get_db() as db:
        db.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, user_id))
    return jsonify({"success": True})


@auth_bp.route("/api/favorites/remove-by-name", methods=["POST"])
@login_required_api
def remove_favorite_by_name():
    user_id = session["user_id"]
    data = request.get_json() or {}
    name     = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip()
    with get_db() as db:
        db.execute(
            "DELETE FROM favorites WHERE user_id=? AND name=? AND location=?",
            (user_id, name, location)
        )
    return jsonify({"success": True})


# ================================================================
# 🔍 SEARCH HISTORY API
# ================================================================

@auth_bp.route("/api/search-history", methods=["GET"])
@login_required_api
def get_search_history():
    user_id = session["user_id"]
    with get_db() as db:
        rows = db.execute("SELECT * FROM search_history WHERE user_id=? ORDER BY searched_at DESC LIMIT 50", (user_id,)).fetchall()
    return jsonify({"success": True, "history": [dict(r) for r in rows]})

@auth_bp.route("/api/search-history", methods=["POST"])
@login_required_api
def add_search_history():
    user_id = session["user_id"]
    data        = request.get_json() or {}
    origin      = (data.get("origin") or "").strip()
    destination = (data.get("destination") or "").strip()
    days        = int(data.get("days") or 0)
    passengers  = int(data.get("passengers") or 1)

    if not destination:
        return jsonify({"success": False, "error": "Thiếu điểm đến"}), 400

    with get_db() as db:
        cur = db.execute(
            "INSERT INTO search_history (user_id, origin, destination, days, passengers) VALUES (?,?,?,?,?)",
            (user_id, origin, destination, days, passengers)
        )
    return jsonify({"success": True, "id": cur.lastrowid})

@auth_bp.route("/api/search-history/<int:history_id>", methods=["DELETE"])
@login_required_api
def delete_search_history(history_id):
    user_id = session["user_id"]
    with get_db() as db:
        db.execute("DELETE FROM search_history WHERE id=? AND user_id=?", (history_id, user_id))
    return jsonify({"success": True})

@auth_bp.route("/api/search-history/all", methods=["DELETE"])
@login_required_api
def clear_search_history():
    user_id = session["user_id"]
    with get_db() as db:
        db.execute("DELETE FROM search_history WHERE user_id=?", (user_id,))
    return jsonify({"success": True})