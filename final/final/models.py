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

-- 4. Hỗ trợ người học (M12): loại hỗ trợ, yêu cầu, phản hồi, lịch sử trạng thái
CREATE TABLE IF NOT EXISTS LoaiHoTro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_loai TEXT NOT NULL UNIQUE,
    ten_loai TEXT NOT NULL
);

-- Không dùng ON DELETE CASCADE cho sinh_vien_id: xóa sinh viên còn yêu cầu sẽ bị chặn
-- (students.py báo lỗi thân thiện) để số liệu dashboard của M17 không bị mất.
CREATE TABLE IF NOT EXISTS YeuCauHoTro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sinh_vien_id INTEGER NOT NULL REFERENCES SinhVien(id),
    loai_ho_tro_id INTEGER NOT NULL REFERENCES LoaiHoTro(id),
    tieu_de TEXT NOT NULL,
    noi_dung TEXT NOT NULL,
    muc_uu_tien TEXT NOT NULL DEFAULT 'trung_binh' CHECK (muc_uu_tien IN ('thap', 'trung_binh', 'cao')),
    trang_thai TEXT NOT NULL DEFAULT 'cho_xu_ly' CHECK (trang_thai IN ('cho_xu_ly', 'dang_xu_ly', 'da_giai_quyet')),
    nguoi_xu_ly_id INTEGER REFERENCES TaiKhoan(id),
    ngay_tao TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    ngay_cap_nhat TEXT,
    ngay_giai_quyet TEXT  -- NULL khi chưa giải quyết
);

CREATE TABLE IF NOT EXISTS PhanHoi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yeu_cau_id INTEGER NOT NULL REFERENCES YeuCauHoTro(id) ON DELETE CASCADE,
    nguoi_gui_id INTEGER NOT NULL REFERENCES TaiKhoan(id),
    noi_dung TEXT NOT NULL,
    la_noi_bo INTEGER NOT NULL DEFAULT 0 CHECK (la_noi_bo IN (0, 1)),  -- 1 = ghi chú nội bộ, sinh viên không thấy
    ngay_tao TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS LichSuTrangThai (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yeu_cau_id INTEGER NOT NULL REFERENCES YeuCauHoTro(id) ON DELETE CASCADE,
    trang_thai_cu TEXT,
    trang_thai_moi TEXT NOT NULL,
    nguoi_thay_doi_id INTEGER REFERENCES TaiKhoan(id),
    ghi_chu TEXT,
    ngay_thay_doi TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sinhvien_lop ON SinhVien(lop_id);
CREATE INDEX IF NOT EXISTS idx_ctdt_nganh ON ChuongTrinhDaoTao(nganh_id);
CREATE INDEX IF NOT EXISTS idx_kqht_sv ON KetQuaHocTap(sinh_vien_id);
CREATE INDEX IF NOT EXISTS idx_taichinh_sv ON TaiChinhSinhVien(sinh_vien_id);
CREATE INDEX IF NOT EXISTS idx_yeucau_sv ON YeuCauHoTro(sinh_vien_id);
CREATE INDEX IF NOT EXISTS idx_yeucau_trangthai ON YeuCauHoTro(trang_thai);
CREATE INDEX IF NOT EXISTS idx_yeucau_ngaytao ON YeuCauHoTro(ngay_tao);
CREATE INDEX IF NOT EXISTS idx_phanhoi_yc ON PhanHoi(yeu_cau_id);
CREATE INDEX IF NOT EXISTS idx_lichsu_yc ON LichSuTrangThai(yeu_cau_id);
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

LOAI_HO_TRO = [("hoc_vu", "Học vụ"), ("tai_khoan", "Tài khoản"),
               ("hoc_phi", "Học phí"), ("ky_thuat", "Kỹ thuật"), ("khac", "Khác")]


def _bo_bang_yeu_cau_cu(db):
    """CSDL tạo từ bản trước có bảng YeuCauHoTro kiểu cũ (không có loai_ho_tro_id): bỏ để tạo lại đúng cấu trúc M12."""
    cols = [r["name"] for r in db.execute("PRAGMA table_info(YeuCauHoTro)")]
    if cols and "loai_ho_tro_id" not in cols:
        db.execute("DROP TABLE YeuCauHoTro")


def init_db(db):
    _bo_bang_yeu_cau_cu(db)
    db.executescript(SCHEMA)
    db.executemany("INSERT OR IGNORE INTO LoaiHoTro(ma_loai, ten_loai) VALUES (?, ?)", LOAI_HO_TRO)
    db.commit()
