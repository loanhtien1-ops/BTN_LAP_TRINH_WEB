"""
Kết nối SQLite và định nghĩa bảng mở rộng cho Cổng sinh viên & Hỗ trợ người học
"""
import sqlite3
import unicodedata
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS NganhHoc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_nganh TEXT NOT NULL UNIQUE,
    ten_nganh TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Lop (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_lop TEXT NOT NULL UNIQUE,
    ten_lop TEXT NOT NULL,
    nganh_id INTEGER NOT NULL REFERENCES NganhHoc(id),
    khoa_hoc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS SinhVien (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_sv TEXT NOT NULL UNIQUE,
    ho_ten TEXT NOT NULL,
    ngay_sinh TEXT,
    gioi_tinh TEXT CHECK (gioi_tinh IN ('Nam', 'Nữ', 'Khác')),
    email TEXT,
    so_dien_thoai TEXT,
    dia_chi TEXT,
    lop_id INTEGER NOT NULL REFERENCES Lop(id),
    trang_thai TEXT NOT NULL DEFAULT 'Đang học'
        CHECK (trang_thai IN ('Đang học', 'Bảo lưu', 'Đã tốt nghiệp', 'Thôi học')),
    ngay_tao TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS TaiKhoan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    vai_tro TEXT NOT NULL CHECK (vai_tro IN ('student', 'support_staff', 'admin')),
    ho_ten TEXT,
    sinh_vien_id INTEGER UNIQUE REFERENCES SinhVien(id) ON DELETE CASCADE
);

-- ================= CÁC BẢNG BỔ SUNG CHO CỔNG SINH VIÊN =================

-- 1. Chương trình đào tạo & Học phần
CREATE TABLE IF NOT EXISTS ChuongTrinhDaoTao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_hp TEXT NOT NULL UNIQUE,
    ten_hp TEXT NOT NULL,
    so_tin_chi INTEGER NOT NULL,
    hoc_ky_goi_y INTEGER NOT NULL,
    nganh_id INTEGER NOT NULL REFERENCES NganhHoc(id),
    loai_hp TEXT DEFAULT 'Bắt buộc' CHECK (loai_hp IN ('Bắt buộc', 'Tự chọn', 'Đại cương', 'Chuyên ngành'))
);

-- 2. Kết quả học tập của sinh viên theo học phần
CREATE TABLE IF NOT EXISTS KetQuaHocTap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sinh_vien_id INTEGER NOT NULL REFERENCES SinhVien(id) ON DELETE CASCADE,
    hoc_phan_id INTEGER NOT NULL REFERENCES ChuongTrinhDaoTao(id),
    diem_chuyen_can REAL,
    diem_thi REAL,
    diem_tong_ket REAL,
    diem_chu TEXT,
    trang_thai_hp TEXT DEFAULT 'Đạt' CHECK (trang_thai_hp IN ('Đạt', 'Học lại', 'Đang học'))
);

-- 3. Tài chính / Học phí sinh viên
CREATE TABLE IF NOT EXISTS TaiChinhSinhVien (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sinh_vien_id INTEGER NOT NULL REFERENCES SinhVien(id) ON DELETE CASCADE,
    hoc_ky TEXT NOT NULL, -- Ví dụ: "Kỳ 1 (2025-2026)", "Kỳ 2 (2025-2026)"
    noi_dung TEXT NOT NULL,
    so_tien_phai_nop INTEGER NOT NULL,
    so_tien_da_nop INTEGER NOT NULL DEFAULT 0,
    han_nop TEXT NOT NULL,
    trang_thai_nop TEXT NOT NULL DEFAULT 'Chưa nộp' CHECK (trang_thai_nop IN ('Đã nộp đủ', 'Chưa nộp', 'Nộp một phần')),
    ngay_giao_dich TEXT
);

-- 4. Yêu cầu thắc mắc, hỗ trợ sinh viên
CREATE TABLE IF NOT EXISTS YeuCauHoTro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sinh_vien_id INTEGER NOT NULL REFERENCES SinhVien(id) ON DELETE CASCADE,
    chu_de TEXT NOT NULL,
    danh_muc TEXT NOT NULL CHECK (danh_muc IN ('Học vụ & Đào tạo', 'Tài chính & Học phí', 'Ký túc xá & Đời sống', 'Kỹ thuật & Hệ thống', 'Khác')),
    noi_dung TEXT NOT NULL,
    ngay_gui TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    trang_thai TEXT NOT NULL DEFAULT 'Chờ xử lý' CHECK (trang_thai IN ('Chờ xử lý', 'Đang xử lý', 'Đã giải quyết', 'Đã đóng')),
    phan_hoi TEXT,
    nguoi_phan_hoi_id INTEGER REFERENCES TaiKhoan(id),
    ngay_phan_hoi TEXT
);

CREATE INDEX IF NOT EXISTS idx_sinhvien_lop ON SinhVien(lop_id);
CREATE INDEX IF NOT EXISTS idx_ctdt_nganh ON ChuongTrinhDaoTao(nganh_id);
CREATE INDEX IF NOT EXISTS idx_kqht_sv ON KetQuaHocTap(sinh_vien_id);
CREATE INDEX IF NOT EXISTS idx_taichinh_sv ON TaiChinhSinhVien(sinh_vien_id);
CREATE INDEX IF NOT EXISTS idx_yeucau_sv ON YeuCauHoTro(sinh_vien_id);
"""

def normalize(text):
    if text is None:
        return ""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()

def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("norm", 1, normalize, deterministic=True)
    return conn

def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db

def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db(db):
    db.executescript(SCHEMA)
    db.commit()
