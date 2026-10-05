import os
import re
import sqlite3
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
import requests

app = Flask(__name__)
app.secret_key = "xaydung_vietnam_secret_key_letos"
CORS(app)  # Mở khóa toàn bộ kết nối giữa Frontend và Backend

DB_NAME = "database.db"

# ==================== CẤU HÌNH ĐỒNG BỘ SANG LETOS ====================
LETOS_API_URL = "https://api.letos.vn/v1/sync"  # Điền link API/Webhook của Letos
LETOS_API_KEY = "Bearer YOUR_LETOS_TOKEN_HERE"


def sync_to_letos(action, table_name, data):
  """Hàm tự động gửi dữ liệu sang Letos khi có Thêm (CREATE), Sửa (UPDATE), Xóa (DELETE)"""
  headers = {
      "Authorization": LETOS_API_KEY,
      "Content-Type": "application/json",
  }
  payload = {
      "action": action,
      "module": table_name,
      "data": data,
      "source": "QLCT_WEB_APP",
  }
  try:
    response = requests.post(
        LETOS_API_URL, json=payload, headers=headers, timeout=5
    )
    print(
        f"[Letos Sync] Thành công: {action} {table_name} - HTTP"
        f" {response.status_code}"
    )
    return True
  except Exception as e:
    print(f"[Letos Sync Cảnh báo] Chưa kết nối được sang Letos ({e})")
    return False


# ==================== KHỞI TẠO CƠ SỞ DỮ LIỆU SQLITE ====================
def init_db():
  conn = sqlite3.connect(DB_NAME)
  cur = conn.cursor()

  # 1. Bảng Công ty
  cur.execute("""
    CREATE TABLE IF NOT EXISTS cong_ty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ct TEXT UNIQUE,
        ten_ct TEXT,
        dia_chi TEXT,
        sdt TEXT,
        nguoi_dai_dien TEXT
    )
    """)

  # 2. Bảng Phòng ban
  cur.execute("""
    CREATE TABLE IF NOT EXISTS phong_ban (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_pb TEXT UNIQUE,
        ten_pb TEXT,
        cong_ty TEXT,
        truong_phong TEXT,
        sdt TEXT
    )
    """)

  # 3. Bảng Công trình (Có trường Mã Phòng Ban: ma_pb)
  cur.execute("""
    CREATE TABLE IF NOT EXISTS cong_trinh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_ctrin TEXT UNIQUE,
        ma_pb TEXT,
        ten_ctrin TEXT,
        dia_diem TEXT,
        chu_dau_tu TEXT,
        du_toan TEXT
    )
    """)

  # 4. Bảng Hạng mục
  cur.execute("""
    CREATE TABLE IF NOT EXISTS hang_muc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_hm TEXT UNIQUE,
        ten_hm TEXT,
        cong_trinh TEXT,
        khoi_luong TEXT,
        tien_do TEXT
    )
    """)
  conn.commit()
  conn.close()


def get_db():
  conn = sqlite3.connect(DB_NAME)
  conn.row_factory = sqlite3.Row
  return conn


# ==================== ROUTE GIAO DIỆN & XÁC THỰC ====================
@app.route("/")
def home():
  return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def api_login():
  data = request.get_json(silent=True) or {}
  username = data.get("username", "").strip()
  password = data.get("password", "").strip()

  # Kiểm tra quy tắc [tên][sdt 10 số]@qlct.html
  pattern = r"^[a-zA-Z0-9_]+(\d{10})@qlct\.html$"
  match = re.match(pattern, username)

  if not match:
    return (
        jsonify({
            "success": False,
            "message": (
                "Tài khoản không đúng định dạng [tên][sđt 10 số]@qlct.html"
            ),
        }),
        400,
    )

  sdt = match.group(1)
  if password != sdt:
    return (
        jsonify({
            "success": False,
            "message": "Mật khẩu không khớp với 10 số điện thoại!",
        }),
        400,
    )

  session["user"] = username
  return jsonify({"success": True, "user": username})


@app.route("/api/logout", methods=["POST"])
def api_logout():
  session.pop("user", None)
  return jsonify({"success": True})


# ==================== 1. CÔNG TY ====================
@app.route("/api/cong-ty", methods=["GET"])
def get_cong_ty():
  q = request.args.get("q", "").strip()
  db = get_db()
  if q:
    kw = f"%{q}%"
    rows = db.execute(
        "SELECT * FROM cong_ty WHERE ma_ct LIKE ? OR ten_ct LIKE ? OR dia_chi"
        " LIKE ? OR nguoi_dai_dien LIKE ? ORDER BY id DESC",
        (kw, kw, kw, kw),
    ).fetchall()
  else:
    rows = db.execute("SELECT * FROM cong_ty ORDER BY id DESC").fetchall()
  db.close()
  return jsonify([dict(r) for r in rows])


@app.route("/api/cong-ty", methods=["POST", "PUT"])
def save_cong_ty():
  data = request.get_json(silent=True) or {}
  item_id = data.get("id")
  db = get_db()
  try:
    if item_id:
      db.execute(
          """UPDATE cong_ty SET ma_ct=?, ten_ct=?, dia_chi=?, sdt=?, nguoi_dai_dien=? WHERE id=?""",
          (
              data.get("ma_ct"),
              data.get("ten_ct"),
              data.get("dia_chi"),
              data.get("sdt"),
              data.get("nguoi_dai_dien"),
              item_id,
          ),
      )
      db.commit()
      sync_to_letos(action="UPDATE", table_name="cong_ty", data=data)
      return jsonify(
          {"success": True, "message": "Đã cập nhật và đồng bộ sang Letos!"}
      )
    else:
      cur = db.cursor()
      cur.execute(
          """INSERT INTO cong_ty (ma_ct, ten_ct, dia_chi, sdt, nguoi_dai_dien) VALUES (?, ?, ?, ?, ?)""",
          (
              data.get("ma_ct"),
              data.get("ten_ct"),
              data.get("dia_chi"),
              data.get("sdt"),
              data.get("nguoi_dai_dien"),
          ),
      )
      db.commit()
      data["id"] = cur.lastrowid
      sync_to_letos(action="CREATE", table_name="cong_ty", data=data)
      return jsonify(
          {"success": True, "message": "Đã thêm mới và đồng bộ sang Letos!"}
      )
  except Exception as e:
    return (
        jsonify(
            {"success": False, "message": f"Mã công ty đã tồn tại hoặc lỗi: {e}"}
        ),
        400,
    )
  finally:
    db.close()


# ==================== 2. PHÒNG BAN ====================
@app.route("/api/phong-ban", methods=["GET"])
def get_phong_ban():
  q = request.args.get("q", "").strip()
  db = get_db()
  if q:
    kw = f"%{q}%"
    rows = db.execute(
        "SELECT * FROM phong_ban WHERE ma_pb LIKE ? OR ten_pb LIKE ? OR cong_ty"
        " LIKE ? OR truong_phong LIKE ? ORDER BY id DESC",
        (kw, kw, kw, kw),
    ).fetchall()
  else:
    rows = db.execute("SELECT * FROM phong_ban ORDER BY id DESC").fetchall()
  db.close()
  return jsonify([dict(r) for r in rows])


@app.route("/api/phong-ban", methods=["POST", "PUT"])
def save_phong_ban():
  data = request.get_json(silent=True) or {}
  item_id = data.get("id")
  db = get_db()
  try:
    if item_id:
      db.execute(
          """UPDATE phong_ban SET ma_pb=?, ten_pb=?, cong_ty=?, truong_phong=?, sdt=? WHERE id=?""",
          (
              data.get("ma_pb"),
              data.get("ten_pb"),
              data.get("cong_ty"),
              data.get("truong_phong"),
              data.get("sdt"),
              item_id,
          ),
      )
      db.commit()
      sync_to_letos(action="UPDATE", table_name="phong_ban", data=data)
      return jsonify(
          {"success": True, "message": "Đã cập nhật và đồng bộ sang Letos!"}
      )
    else:
      cur = db.cursor()
      cur.execute(
          """INSERT INTO phong_ban (ma_pb, ten_pb, cong_ty, truong_phong, sdt) VALUES (?, ?, ?, ?, ?)""",
          (
              data.get("ma_pb"),
              data.get("ten_pb"),
              data.get("cong_ty"),
              data.get("truong_phong"),
              data.get("sdt"),
          ),
      )
      db.commit()
      data["id"] = cur.lastrowid
      sync_to_letos(action="CREATE", table_name="phong_ban", data=data)
      return jsonify(
          {"success": True, "message": "Đã thêm mới và đồng bộ sang Letos!"}
      )
  except Exception as e:
    return (
        jsonify(
            {"success": False, "message": f"Mã PB đã tồn tại hoặc lỗi: {e}"}
        ),
        400,
    )
  finally:
    db.close()


# ==================== 3. CÔNG TRÌNH (CÓ MÃ PHÒNG BAN) ====================
@app.route("/api/cong-trinh", methods=["GET"])
def get_cong_trinh():
  q = request.args.get("q", "").strip()
  db = get_db()
  if q:
    kw = f"%{q}%"
    rows = db.execute(
        "SELECT * FROM cong_trinh WHERE ma_ctrin LIKE ? OR ma_pb LIKE ? OR"
        " ten_ctrin LIKE ? OR dia_diem LIKE ? OR chu_dau_tu LIKE ? ORDER BY id"
        " DESC",
        (kw, kw, kw, kw, kw),
    ).fetchall()
  else:
    rows = db.execute("SELECT * FROM cong_trinh ORDER BY id DESC").fetchall()
  db.close()
  return jsonify([dict(r) for r in rows])


@app.route("/api/cong-trinh", methods=["POST", "PUT"])
def save_cong_trinh():
  data = request.get_json(silent=True) or {}
  item_id = data.get("id")
  db = get_db()
  try:
    if item_id:
      db.execute(
          """UPDATE cong_trinh SET ma_ctrin=?, ma_pb=?, ten_ctrin=?, dia_diem=?, chu_dau_tu=?, du_toan=? WHERE id=?""",
          (
              data.get("ma_ctrin"),
              data.get("ma_pb"),
              data.get("ten_ctrin"),
              data.get("dia_diem"),
              data.get("chu_dau_tu"),
              data.get("du_toan"),
              item_id,
          ),
      )
      db.commit()
      sync_to_letos(action="UPDATE", table_name="cong_trinh", data=data)
      return jsonify(
          {"success": True, "message": "Đã cập nhật và đồng bộ sang Letos!"}
      )
    else:
      cur = db.cursor()
      cur.execute(
          """INSERT INTO cong_trinh (ma_ctrin, ma_pb, ten_ctrin, dia_diem, chu_dau_tu, du_toan) VALUES (?, ?, ?, ?, ?, ?)""",
          (
              data.get("ma_ctrin"),
              data.get("ma_pb"),
              data.get("ten_ctrin"),
              data.get("dia_diem"),
              data.get("chu_dau_tu"),
              data.get("du_toan"),
          ),
      )
      db.commit()
      data["id"] = cur.lastrowid
      sync_to_letos(action="CREATE", table_name="cong_trinh", data=data)
      return jsonify(
          {"success": True, "message": "Đã thêm mới và đồng bộ sang Letos!"}
      )
  except Exception as e:
    return (
        jsonify(
            {"success": False, "message": f"Mã CT đã tồn tại hoặc lỗi: {e}"}
        ),
        400,
    )
  finally:
    db.close()


# ==================== 4. HẠNG MỤC ====================
@app.route("/api/hang-muc", methods=["GET"])
def get_hang_muc():
  q = request.args.get("q", "").strip()
  db = get_db()
  if q:
    kw = f"%{q}%"
    rows = db.execute(
        "SELECT * FROM hang_muc WHERE ma_hm LIKE ? OR ten_hm LIKE ? OR"
        " cong_trinh LIKE ? ORDER BY id DESC",
        (kw, kw, kw),
    ).fetchall()
  else:
    rows = db.execute("SELECT * FROM hang_muc ORDER BY id DESC").fetchall()
  db.close()
  return jsonify([dict(r) for r in rows])


@app.route("/api/hang-muc", methods=["POST", "PUT"])
def save_hang_muc():
  data = request.get_json(silent=True) or {}
  item_id = data.get("id")
  db = get_db()
  try:
    if item_id:
      db.execute(
          """UPDATE hang_muc SET ma_hm=?, ten_hm=?, cong_trinh=?, khoi_luong=?, tien_do=? WHERE id=?""",
          (
              data.get("ma_hm"),
              data.get("ten_hm"),
              data.get("cong_trinh"),
              data.get("khoi_luong"),
              data.get("tien_do"),
              item_id,
          ),
      )
      db.commit()
      sync_to_letos(action="UPDATE", table_name="hang_muc", data=data)
      return jsonify(
          {"success": True, "message": "Đã cập nhật và đồng bộ sang Letos!"}
      )
    else:
      cur = db.cursor()
      cur.execute(
          """INSERT INTO hang_muc (ma_hm, ten_hm, cong_trinh, khoi_luong, tien_do) VALUES (?, ?, ?, ?, ?)""",
          (
              data.get("ma_hm"),
              data.get("ten_hm"),
              data.get("cong_trinh"),
              data.get("khoi_luong"),
              data.get("tien_do"),
          ),
      )
      db.commit()
      data["id"] = cur.lastrowid
      sync_to_letos(action="CREATE", table_name="hang_muc", data=data)
      return jsonify(
          {"success": True, "message": "Đã thêm mới và đồng bộ sang Letos!"}
      )
  except Exception as e:
    return (
        jsonify(
            {"success": False, "message": f"Mã HM đã tồn tại hoặc lỗi: {e}"}
        ),
        400,
    )
  finally:
    db.close()


# ==================== 5. XÓA BẢN GHI ====================
@app.route("/api/delete/<table>/<int:id>", methods=["DELETE"])
def delete_item(table, id):
  valid_tables = ["cong_ty", "phong_ban", "cong_trinh", "hang_muc"]
  if table not in valid_tables:
    return jsonify({"success": False, "message": "Bảng không tồn tại"}), 400

  db = get_db()
  record = db.execute(f"SELECT * FROM {table} WHERE id = ?", (id,)).fetchone()
  if record:
    deleted_dict = dict(record)
    db.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
    db.commit()
    sync_to_letos(action="DELETE", table_name=table, data=deleted_dict)

  db.close()
  return jsonify(
      {"success": True, "message": "Đã xóa và đồng bộ xóa sang Letos!"}
  )


# ==================== 6. TRA CỨU LIÊN THÔNG ====================
@app.route("/api/tra-cuu", methods=["GET"])
def global_search():
  q = request.args.get("q", "").strip()
  if not q:
    return jsonify(
        {"cong_ty": [], "phong_ban": [], "cong_trinh": [], "hang_muc": []}
    )

  db = get_db()
  kw = f"%{q}%"
  res_ct = db.execute(
      "SELECT * FROM cong_ty WHERE ma_ct LIKE ? OR ten_ct LIKE ? OR dia_chi"
      " LIKE ? OR nguoi_dai_dien LIKE ?",
      (kw, kw, kw, kw),
  ).fetchall()
  res_pb = db.execute(
      "SELECT * FROM phong_ban WHERE ma_pb LIKE ? OR ten_pb LIKE ? OR cong_ty"
      " LIKE ? OR truong_phong LIKE ?",
      (kw, kw, kw, kw),
  ).fetchall()
  res_ctrin = db.execute(
      "SELECT * FROM cong_trinh WHERE ma_ctrin LIKE ? OR ma_pb LIKE ? OR"
      " ten_ctrin LIKE ? OR dia_diem LIKE ? OR chu_dau_tu LIKE ?",
      (kw, kw, kw, kw, kw),
  ).fetchall()
  res_hm = db.execute(
      "SELECT * FROM hang_muc WHERE ma_hm LIKE ? OR ten_hm LIKE ? OR cong_trinh"
      " LIKE ?",
      (kw, kw, kw),
  ).fetchall()
  db.close()

  return jsonify({
      "cong_ty": [dict(r) for r in res_ct],
      "phong_ban": [dict(r) for r in res_pb],
      "cong_trinh": [dict(r) for r in res_ctrin],
      "hang_muc": [dict(r) for r in res_hm],
  })


if __name__ == "__main__":
  init_db()
  print("=" * 65)
  print(">> SERVER ĐANG CHẠY: http://127.0.0.1:5000")
  print(">> Đã bật CORS. Đã sẵn sàng kết nối và đồng bộ Letos.")
  print("=" * 65)
app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)