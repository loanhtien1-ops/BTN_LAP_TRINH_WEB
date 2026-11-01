"""Dữ liệu mẫu để chạy thử. Khởi tạo tài khoản Admin, Nhân viên và Sinh viên"""
import os
import random
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

NGANH = [
    ("CNTT", "Công nghệ thông tin"),
    ("KTPM", "Kỹ thuật phần mềm"),
    ("HTTT", "Hệ thống thông tin"),
    ("QTKD", "Quản trị kinh doanh"),
]

LOP = [
    ("CNTT66A", "Công nghệ thông tin 66A", "CNTT", "K66"),
    ("CNTT66B", "Công nghệ thông tin 66B", "CNTT", "K66"),
    ("KTPM66A", "Kỹ thuật phần mềm 66A", "KTPM", "K66"),
    ("HTTT67A", "Hệ thống thông tin 67A", "HTTT", "K67"),
    ("QTKD67A", "Quản trị kinh doanh 67A", "QTKD", "K67"),
]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô"]
DEM_NAM = ["Văn", "Đức", "Minh", "Quang", "Hữu"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Phương", "Khánh"]
TEN_NAM = ["Tiến", "Hùng", "Nam", "Dũng", "Long", "Khoa", "Hải", "Phúc", "Sơn", "Bình"]
TEN_NU = ["Thảo", "Hà", "Linh", "Lan", "Hương", "Mai", "Trang", "Anh", "Ngọc", "Yến"]
DIA_CHI = ["Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình", "Bắc Ninh",
           "Thanh Hóa", "Nghệ An", "Hưng Yên", "Hải Dương", "Quảng Ninh"]

DEFAULT_PASSWORD = "123456"

def seed(db, so_sinh_vien=40):
    rng = random.Random(42)

    # 1. Thêm Ngành học
    for ma, ten in NGANH:
        db.execute("INSERT OR IGNORE INTO NganhHoc(ma_nganh, ten_nganh) VALUES (?, ?)", (ma, ten))
    nganh_id = {r["ma_nganh"]: r["id"] for r in db.execute("SELECT id, ma_nganh FROM NganhHoc")}

    # 2. Thêm Lớp học
    for ma, ten, ma_nganh, khoa in LOP:
        db.execute("INSERT OR IGNORE INTO Lop(ma_lop, ten_lop, nganh_id, khoa_hoc) VALUES (?, ?, ?, ?)",
                   (ma, ten, nganh_id[ma_nganh], khoa))
    lop_rows = db.execute("SELECT id, khoa_hoc FROM Lop ORDER BY id").fetchall()

    # 3. Thêm tài khoản ADMIN & NHÂN VIÊN
    db.execute("""
        INSERT OR IGNORE INTO TaiKhoan(username, password_hash, vai_tro, ho_ten)
        VALUES (?, ?, 'admin', ?)
    """, ("admin", generate_password_hash("admin123"), "Admin"))

    db.execute("""
        INSERT OR IGNORE INTO TaiKhoan(username, password_hash, vai_tro, ho_ten)
        VALUES (?, ?, 'support_staff', ?)
    """, ("staff", generate_password_hash("staff123"), "Nhân viên hỗ trợ"))

    # Thêm thêm tài khoản nhân viên 2 cho phong phú
    db.execute("""
        INSERT OR IGNORE INTO TaiKhoan(username, password_hash, vai_tro, ho_ten)
        VALUES (?, ?, 'support_staff', ?)
    """, ("staff2", generate_password_hash("staff123"), "Nhân viên hỗ trợ 2"))

    # 4. Thêm Sinh viên và Tài khoản Sinh viên
    pw_student = generate_password_hash(DEFAULT_PASSWORD)
    for i in range(so_sinh_vien):
        lop = lop_rows[i % len(lop_rows)]
        nam = rng.random() < 0.55
        ho_ten = " ".join([
            rng.choice(HO),
            rng.choice(DEM_NAM if nam else DEM_NU),
            rng.choice(TEN_NAM if nam else TEN_NU),
        ])
        ma_sv = f"SV{lop['khoa_hoc'][1:]}{i + 1:04d}"
        ngay_sinh = date(2004, 1, 1) + timedelta(days=rng.randint(0, 365 * 2))
        trang_thai = "Bảo lưu" if i % 17 == 16 else "Đang học"

        cur = db.execute(
            """INSERT OR IGNORE INTO SinhVien(ma_sv, ho_ten, ngay_sinh, gioi_tinh, email,
                                   so_dien_thoai, dia_chi, lop_id, trang_thai)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ma_sv, ho_ten, ngay_sinh.isoformat(), "Nam" if nam else "Nữ",
             f"{ma_sv.lower()}@student.neu.edu.vn", "09" + "".join(rng.choices("0123456789", k=8)),
             rng.choice(DIA_CHI), lop["id"], trang_thai))
        
        # Lấy id sinh viên vừa tạo
        sv_row = db.execute("SELECT id FROM SinhVien WHERE ma_sv = ?", (ma_sv,)).fetchone()
        if sv_row:
            db.execute(
                """INSERT OR IGNORE INTO TaiKhoan(username, password_hash, vai_tro, ho_ten, sinh_vien_id)
                   VALUES (?, ?, 'student', ?, ?)""",
                (ma_sv, pw_student, ho_ten, sv_row["id"]))

    db.commit()

if __name__ == "__main__":
    from app import app
    from models import connect, init_db
    from seed_portal import seed_portal_data
    from seed_support import seed_support_data

    path = app.config["DATABASE"]
    if os.path.exists(path):
        os.remove(path)
    conn = connect(path)
    init_db(conn)
    seed(conn)
    seed_portal_data(conn)
    seed_support_data(conn)
    conn.close()
    print(">>> ĐÃ KHỞI TẠO XONG CƠ SỞ DỮ LIỆU VÀ TOÀN BỘ TÀI KHOẢN MẪU TẠI:", path)
