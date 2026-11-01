"""M17 - Dashboard báo cáo và đánh giá hoạt động hỗ trợ người học.

Phân quyền (vai trò + phạm vi):
  - admin         : xem toàn bộ, quản lý chỉ tiêu (xác nhận, kiểm tra, công bố), giao phạm vi cho nhân viên
  - support_staff : xem phần hỗ trợ; nếu được giao phạm vi (PhamViNhanVien) thì chỉ thấy các loại hỗ trợ được giao
  - student       : không vào được

Nguyên tắc (theo đề M17 và quy tắc quản trị dữ liệu chung):
  - Chỉ ĐỌC dữ liệu của M03 và M12; bảng riêng của M17 (ChiTieu, LichSuChiTieu, KetQuaChiTieu,
    PhamViNhanVien) tự tạo trong file này, không phải sửa models.py.
  - Mọi API trả kèm pham_vi, nguon, thoi_diem_tinh để truy được nguồn và phạm vi tính.
  - Báo cáo tổng hợp và danh sách truy xuất không hiện họ tên, mã sinh viên.
  - Chỉ số nội bộ, không đồng nhất với HEDI (chưa có công thức chính thức cho H10).
"""
import csv
import hmac
import io
import json
import math
import secrets
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

from auth import roles_required
from models import get_db
from support import SLA_GIO, TEN_TRANG_THAI, TEN_UU_TIEN, TRANG_THAI, now_str

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

STAFF = ("support_staff", "admin")
PER_PAGE = 10
GHI_CHU = "Chỉ số nội bộ của hệ thống, không phải KPI chính thức và không đồng nhất với HEDI."
TEN_VAI_TRO = {"student": "Sinh viên", "support_staff": "Nhân viên hỗ trợ", "admin": "Quản trị viên"}

# ---------------------------------------------------------------- Quy trình chỉ tiêu
TEN_TRANG_THAI_CT = {"nhap": "Nháp", "da_xac_nhan_nguon": "Đã xác nhận nguồn",
                     "da_kiem_tra": "Đã kiểm tra", "da_cong_bo": "Đã công bố"}
MAU_TRANG_THAI_CT = {"nhap": "secondary", "da_xac_nhan_nguon": "info",
                     "da_kiem_tra": "warning", "da_cong_bo": "success"}
TEN_HANH_DONG = {"tao": "Khởi tạo", "sua_dinh_nghia": "Sửa định nghĩa", "xac_nhan_nguon": "Xác nhận nguồn",
                 "kiem_tra": "Xác nhận đã kiểm tra", "cong_bo": "Công bố kết quả", "tra_ve": "Trả về nháp"}
# hành động -> (các trạng thái được phép chuyển từ, trạng thái mới)
CHUYEN = {
    "xac_nhan_nguon": (("nhap",), "da_xac_nhan_nguon"),
    "kiem_tra": (("da_xac_nhan_nguon",), "da_kiem_tra"),
    "cong_bo": (("da_kiem_tra", "da_cong_bo"), "da_cong_bo"),
    "tra_ve": (("da_xac_nhan_nguon", "da_kiem_tra", "da_cong_bo"), "nhap"),
}
TRUONG_DINH_NGHIA = ("ten", "cong_thuc", "don_vi", "chieu_phan_tich", "nguon", "dau_moi")
NHAN_TRUONG = {"ten": "Tên chỉ tiêu", "cong_thuc": "Công thức", "don_vi": "Đơn vị tính",
               "chieu_phan_tich": "Chiều phân tích", "nguon": "Nguồn dữ liệu", "dau_moi": "Đầu mối dữ liệu"}

SCHEMA_M17 = """
CREATE TABLE IF NOT EXISTS ChiTieu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma TEXT NOT NULL UNIQUE,
    ten TEXT NOT NULL,
    cong_thuc TEXT NOT NULL,
    don_vi TEXT NOT NULL,
    chieu_phan_tich TEXT,
    nguon TEXT NOT NULL,
    dau_moi TEXT NOT NULL,
    vai_tro_xem TEXT NOT NULL DEFAULT 'staff' CHECK (vai_tro_xem IN ('staff', 'admin')),
    phien_ban INTEGER NOT NULL DEFAULT 1,
    trang_thai TEXT NOT NULL DEFAULT 'nhap'
        CHECK (trang_thai IN ('nhap', 'da_xac_nhan_nguon', 'da_kiem_tra', 'da_cong_bo')),
    ngay_cap_nhat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS LichSuChiTieu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chi_tieu_id INTEGER NOT NULL REFERENCES ChiTieu(id) ON DELETE CASCADE,
    phien_ban INTEGER NOT NULL,
    hanh_dong TEXT NOT NULL,
    trang_thai_cu TEXT,
    trang_thai_moi TEXT,
    nguoi_thuc_hien_id INTEGER REFERENCES TaiKhoan(id),
    can_cu TEXT,
    noi_dung_truoc TEXT,
    ngay_thuc_hien TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS KetQuaChiTieu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chi_tieu_id INTEGER NOT NULL REFERENCES ChiTieu(id) ON DELETE CASCADE,
    phien_ban INTEGER NOT NULL,
    ky_tu TEXT,
    ky_den TEXT,
    chieu TEXT NOT NULL DEFAULT 'toan_he_thong',
    gia_tri REAL,
    thoi_diem_tinh TEXT NOT NULL,
    nguoi_cong_bo_id INTEGER REFERENCES TaiKhoan(id)
);
CREATE TABLE IF NOT EXISTS PhamViNhanVien (
    tai_khoan_id INTEGER NOT NULL REFERENCES TaiKhoan(id) ON DELETE CASCADE,
    loai_ho_tro_id INTEGER NOT NULL REFERENCES LoaiHoTro(id) ON DELETE CASCADE,
    PRIMARY KEY (tai_khoan_id, loai_ho_tro_id)
);
CREATE INDEX IF NOT EXISTS idx_lichsuct_ct ON LichSuChiTieu(chi_tieu_id);
CREATE INDEX IF NOT EXISTS idx_ketquact_ct ON KetQuaChiTieu(chi_tieu_id);
"""

# Định nghĩa ban đầu, nạp vào bảng ChiTieu ở lần chạy đầu tiên. Từ đó mọi thay đổi đi qua
# trang Danh mục chỉ tiêu và được ghi lịch sử (ai, khi nào, căn cứ).
CHI_TIEU_MAC_DINH = [
    {"ma": "HT01", "ten": "Tổng số yêu cầu hỗ trợ", "don_vi": "yêu cầu", "vai_tro_xem": "staff",
     "cong_thuc": "COUNT(YeuCauHoTro) có ngay_tao nằm trong khoảng đã chọn",
     "chieu_phan_tich": "trạng thái, loại hỗ trợ, tháng, ngành, lớp",
     "nguon": "YeuCauHoTro, LoaiHoTro, SinhVien, Lop", "dau_moi": "M12 - Hỗ trợ người học"},
    {"ma": "HT02", "ten": "Tỷ lệ giải quyết", "don_vi": "%", "vai_tro_xem": "staff",
     "cong_thuc": "số yêu cầu trạng thái da_giai_quyet / tổng số yêu cầu x 100",
     "chieu_phan_tich": "khoảng thời gian, ngành, lớp", "nguon": "YeuCauHoTro",
     "dau_moi": "M12 - Hỗ trợ người học"},
    {"ma": "HT03", "ten": "Thời gian tiếp nhận trung bình", "don_vi": "giờ", "vai_tro_xem": "staff",
     "cong_thuc": "AVG(thời điểm chuyển sang dang_xu_ly lần đầu - ngay_tao), chỉ tính yêu cầu đã được tiếp nhận",
     "chieu_phan_tich": "khoảng thời gian, ngành, lớp", "nguon": "YeuCauHoTro, LichSuTrangThai",
     "dau_moi": "M12 - Hỗ trợ người học"},
    {"ma": "HT04", "ten": "Thời gian giải quyết trung bình", "don_vi": "giờ", "vai_tro_xem": "staff",
     "cong_thuc": "AVG(ngay_giai_quyet - ngay_tao), chỉ tính yêu cầu đã giải quyết",
     "chieu_phan_tich": "loại hỗ trợ, tháng, ngành, lớp", "nguon": "YeuCauHoTro",
     "dau_moi": "M12 - Hỗ trợ người học"},
    {"ma": "HT05", "ten": "Tỷ lệ giải quyết đúng hạn", "don_vi": "%", "vai_tro_xem": "staff",
     "cong_thuc": "số yêu cầu giải quyết trong %d giờ kể từ ngay_tao / số yêu cầu đã giải quyết x 100" % SLA_GIO,
     "chieu_phan_tich": "khoảng thời gian, ngành, lớp",
     "nguon": "YeuCauHoTro (hạn xử lý %d giờ lấy từ support.py)" % SLA_GIO,
     "dau_moi": "M12 - Hỗ trợ người học"},
    {"ma": "HT06", "ten": "Số yêu cầu quá hạn", "don_vi": "yêu cầu", "vai_tro_xem": "staff",
     "cong_thuc": "COUNT yêu cầu chưa da_giai_quyet và ngay_tao cách hiện tại hơn %d giờ" % SLA_GIO,
     "chieu_phan_tich": "khoảng thời gian, ngành, lớp", "nguon": "YeuCauHoTro",
     "dau_moi": "M12 - Hỗ trợ người học"},
    {"ma": "SV01", "ten": "Tổng số sinh viên", "don_vi": "sinh viên", "vai_tro_xem": "admin",
     "cong_thuc": "COUNT(SinhVien), toàn bộ hồ sơ, không lọc theo ngày",
     "chieu_phan_tich": "lớp, ngành, khóa, trạng thái học", "nguon": "SinhVien, Lop, NganhHoc",
     "dau_moi": "M03 - Quản lý sinh viên"},
]

FROM_Y = ("FROM YeuCauHoTro y JOIN SinhVien sv ON sv.id = y.sinh_vien_id "
          "JOIN Lop l ON l.id = sv.lop_id")
GIO = "((julianday(y.ngay_giai_quyet) - julianday(y.ngay_tao)) * 24)"
DA_XONG = " AND y.trang_thai = 'da_giai_quyet' AND y.ngay_giai_quyet IS NOT NULL"


# ================================================================ nền tảng
def _khoi_tao(db):
    db.executescript(SCHEMA_M17)
    if db.execute("SELECT COUNT(*) FROM ChiTieu").fetchone()[0] == 0:
        now = now_str()
        for c in CHI_TIEU_MAC_DINH:
            cur = db.execute(
                """INSERT INTO ChiTieu(ma, ten, cong_thuc, don_vi, chieu_phan_tich, nguon, dau_moi,
                                       vai_tro_xem, phien_ban, trang_thai, ngay_cap_nhat)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'nhap', ?)""",
                (c["ma"], c["ten"], c["cong_thuc"], c["don_vi"], c["chieu_phan_tich"], c["nguon"],
                 c["dau_moi"], c["vai_tro_xem"], now))
            db.execute(
                """INSERT INTO LichSuChiTieu(chi_tieu_id, phien_ban, hanh_dong, trang_thai_moi, can_cu, ngay_thuc_hien)
                   VALUES (?, 1, 'tao', 'nhap', 'Định nghĩa ban đầu của module M17', ?)""",
                (cur.lastrowid, now))
    db.commit()


def _db():
    """Kết nối CSDL và tự tạo bảng của M17 nếu chưa có."""
    db = get_db()
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ChiTieu'").fetchone() is None:
        _khoi_tao(db)
    return db


def _csrf():
    token = session.get("dash_csrf")
    if not token:
        token = secrets.token_hex(16)
        session["dash_csrf"] = token
    return token


def _kiem_csrf():
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("dash_csrf", "")):
        abort(400, "Phiên làm việc không hợp lệ. Hãy tải lại trang rồi thử lại.")


def _loai_duoc_giao(db):
    """None = xem tất cả loại hỗ trợ. Danh sách id = chỉ các loại được giao (chỉ áp dụng cho support_staff)."""
    if g.user["vai_tro"] != "support_staff":
        return None
    ids = [r[0] for r in db.execute(
        "SELECT loai_ho_tro_id FROM PhamViNhanVien WHERE tai_khoan_id = ? ORDER BY loai_ho_tro_id",
        (g.user["id"],))]
    return ids or None


def _ngay_hop_le(value, ten):
    value = (value or "").strip()
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("%s phải có dạng YYYY-MM-DD." % ten)
    return value


def _so_nguyen(value, ten):
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError("%s không hợp lệ." % ten)
    return int(value)


def _dieu_kien(tu_ngay=None, den_ngay=None, nganh_id=None, lop_id=None, loai_ids=None):
    """Ghép điều kiện lọc dùng chung cho mọi truy vấn (bí danh y, sv, l)."""
    cond, params = "", []
    if tu_ngay:
        cond += " AND date(y.ngay_tao) >= ?"
        params.append(tu_ngay)
    if den_ngay:
        cond += " AND date(y.ngay_tao) <= ?"
        params.append(den_ngay)
    cond_sv, params_sv = "", []
    if nganh_id is not None:
        cond_sv += " AND l.nganh_id = ?"
        params_sv.append(nganh_id)
    if lop_id is not None:
        cond_sv += " AND l.id = ?"
        params_sv.append(lop_id)
    cond += cond_sv
    params += params_sv
    if loai_ids:
        cond += " AND y.loai_ho_tro_id IN (%s)" % ",".join("?" * len(loai_ids))
        params += list(loai_ids)
    return {"cond": cond, "params": params, "cond_sv": cond_sv, "params_sv": params_sv, "loai_ids": loai_ids}


def _doc_bo_loc(loai_ids=None):
    """Đọc ?tu_ngay=&den_ngay=&nganh_id=&lop_id= từ URL. Ném ValueError nếu sai định dạng."""
    pv = {"tu_ngay": _ngay_hop_le(request.args.get("tu_ngay"), "tu_ngay"),
          "den_ngay": _ngay_hop_le(request.args.get("den_ngay"), "den_ngay"),
          "nganh_id": _so_nguyen(request.args.get("nganh_id"), "nganh_id"),
          "lop_id": _so_nguyen(request.args.get("lop_id"), "lop_id")}
    if pv["tu_ngay"] and pv["den_ngay"] and pv["tu_ngay"] > pv["den_ngay"]:
        raise ValueError("tu_ngay không được sau den_ngay.")
    pv["tinh_theo"] = "ngay_tao"
    pv["loai_duoc_giao"] = loai_ids
    return _dieu_kien(pv["tu_ngay"], pv["den_ngay"], pv["nganh_id"], pv["lop_id"], loai_ids), pv


def _lam_tron(value, so_le=1):
    return round(value, so_le) if value is not None else None


def _du_thang(theo_thang):
    """Điền các tháng không có dữ liệu để biểu đồ liền mạch."""
    if not theo_thang:
        return []
    co = {r["thang"]: r for r in theo_thang}
    y, m = map(int, theo_thang[0]["thang"].split("-"))
    y_cuoi, m_cuoi = map(int, theo_thang[-1]["thang"].split("-"))
    ket_qua = []
    while (y, m) <= (y_cuoi, m_cuoi):
        key = "%04d-%02d" % (y, m)
        ket_qua.append(co.get(key, {"thang": key, "so": 0, "gio_giai_quyet_tb": None}))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return ket_qua


def _han_qua_han():
    return (datetime.now() - timedelta(hours=SLA_GIO)).strftime("%Y-%m-%d %H:%M:%S")


# ================================================================ tính số liệu (một nguồn duy nhất)
def _tinh_ho_tro(db, f):
    """Mọi số liệu hỗ trợ đều tính ở đây: dùng cho API, danh sách truy xuất và công bố chỉ tiêu."""
    cond, params = f["cond"], f["params"]
    base = FROM_Y + " WHERE 1 = 1" + cond

    tong = db.execute("SELECT COUNT(*) " + base, params).fetchone()[0]
    theo_tt = {r["trang_thai"]: r["n"] for r in db.execute(
        "SELECT y.trang_thai, COUNT(*) AS n " + base + " GROUP BY y.trang_thai", params)}
    theo_trang_thai = {k: theo_tt.get(k, 0) for k in TRANG_THAI}

    loai_cond, loai_params = "", []
    if f["loai_ids"]:
        loai_cond = " WHERE lh.id IN (%s)" % ",".join("?" * len(f["loai_ids"]))
        loai_params = list(f["loai_ids"])
    theo_loai = [{"id": r["id"], "ten": r["ten_loai"], "so": r["n"]} for r in db.execute(
        "SELECT lh.id, lh.ten_loai, COUNT(t.id) AS n FROM LoaiHoTro lh LEFT JOIN "
        "(SELECT y.id, y.loai_ho_tro_id " + base + ") t ON t.loai_ho_tro_id = lh.id" + loai_cond +
        " GROUP BY lh.id ORDER BY lh.id", params + loai_params)]

    gio_thang = {r["thang"]: r["gio"] for r in db.execute(
        "SELECT strftime('%Y-%m', y.ngay_tao) AS thang, AVG" + GIO + " AS gio " + base + DA_XONG +
        " GROUP BY thang", params)}
    theo_thang = _du_thang([
        {"thang": r["thang"], "so": r["n"], "gio_giai_quyet_tb": _lam_tron(gio_thang.get(r["thang"]))}
        for r in db.execute("SELECT strftime('%Y-%m', y.ngay_tao) AS thang, COUNT(*) AS n " + base +
                            " GROUP BY thang ORDER BY thang", params)])

    theo_nganh = [{"ma": r["ma_nganh"], "ten": r["ten_nganh"], "so": r["n"]} for r in db.execute(
        "SELECT n.ma_nganh, n.ten_nganh, COUNT(*) AS n " + FROM_Y + " JOIN NganhHoc n ON n.id = l.nganh_id "
        "WHERE 1 = 1" + cond + " GROUP BY n.id ORDER BY n.ma_nganh", params)]
    theo_lop = [{"ma": r["ma_lop"], "ten": r["ten_lop"], "so": r["n"]} for r in db.execute(
        "SELECT l.ma_lop, l.ten_lop, COUNT(*) AS n " + base + " GROUP BY l.id ORDER BY l.ma_lop", params)]

    da_gui = db.execute("SELECT COUNT(DISTINCT y.sinh_vien_id) " + base, params).fetchone()[0]
    tong_sv = db.execute("SELECT COUNT(*) FROM SinhVien sv JOIN Lop l ON l.id = sv.lop_id WHERE 1 = 1" +
                         f["cond_sv"], f["params_sv"]).fetchone()[0]

    r = db.execute(
        "SELECT AVG" + GIO + ", MIN" + GIO + ", MAX" + GIO + ", COUNT(*), "
        "SUM(CASE WHEN " + GIO + " <= ? THEN 1 ELSE 0 END) " + base + DA_XONG,
        [SLA_GIO] + params).fetchone()
    so_da_giai_quyet, so_dung_han = r[3], r[4] or 0

    gio_theo_loai = [{"id": x["id"], "ten": x["ten_loai"], "gio": _lam_tron(x["gio"])} for x in db.execute(
        "SELECT lh.id, lh.ten_loai, AVG" + GIO + " AS gio " + FROM_Y +
        " JOIN LoaiHoTro lh ON lh.id = y.loai_ho_tro_id WHERE 1 = 1" + cond + DA_XONG +
        " GROUP BY lh.id ORDER BY lh.id", params)]

    tiep_nhan = db.execute(
        "SELECT AVG((julianday(h.t) - julianday(y.ngay_tao)) * 24) " + FROM_Y +
        " JOIN (SELECT yeu_cau_id, MIN(ngay_thay_doi) AS t FROM LichSuTrangThai "
        "WHERE trang_thai_moi = 'dang_xu_ly' GROUP BY yeu_cau_id) h ON h.yeu_cau_id = y.id "
        "WHERE 1 = 1" + cond, params).fetchone()[0]

    qua_han = db.execute(
        "SELECT COUNT(*) " + base + " AND y.trang_thai != 'da_giai_quyet' AND y.ngay_tao <= ?",
        params + [_han_qua_han()]).fetchone()[0]

    xong = theo_trang_thai["da_giai_quyet"]
    return {
        "tong": tong,
        "theo_trang_thai": theo_trang_thai,
        "theo_loai": theo_loai,
        "theo_thang": theo_thang,
        "theo_nganh": theo_nganh,
        "theo_lop": theo_lop,
        "sinh_vien_gui_yeu_cau": {"da_gui": da_gui, "tong_sinh_vien": tong_sv,
                                  "ty_le": _lam_tron(da_gui / tong_sv * 100) if tong_sv else None},
        "ty_le_giai_quyet": _lam_tron(xong / tong * 100) if tong else None,
        "thoi_gian": {
            "tiep_nhan_tb_gio": _lam_tron(tiep_nhan),
            "giai_quyet_tb_gio": _lam_tron(r[0]),
            "nhanh_nhat_gio": _lam_tron(r[1]),
            "cham_nhat_gio": _lam_tron(r[2]),
            "so_da_giai_quyet": so_da_giai_quyet,
            "ty_le_dung_han": _lam_tron(so_dung_han / so_da_giai_quyet * 100) if so_da_giai_quyet else None,
            "theo_loai": gio_theo_loai,
            "sla_gio": SLA_GIO,
        },
        "qua_han": qua_han,
    }


GIA_TRI_HO_TRO = {
    "HT01": lambda d: d["tong"],
    "HT02": lambda d: d["ty_le_giai_quyet"],
    "HT03": lambda d: d["thoi_gian"]["tiep_nhan_tb_gio"],
    "HT04": lambda d: d["thoi_gian"]["giai_quyet_tb_gio"],
    "HT05": lambda d: d["thoi_gian"]["ty_le_dung_han"],
    "HT06": lambda d: d["qua_han"],
}


def _tinh_gia_tri(db, ma, tu_ngay, den_ngay):
    """Giá trị chỉ tiêu cho một kỳ, dùng khi công bố. Trả (giá trị, kỳ từ, kỳ đến)."""
    if ma == "SV01":
        return db.execute("SELECT COUNT(*) FROM SinhVien").fetchone()[0], None, None
    ham = GIA_TRI_HO_TRO.get(ma)
    if ham is None:
        raise ValueError("Chỉ tiêu %s chưa có cách tính trong code." % ma)
    return ham(_tinh_ho_tro(db, _dieu_kien(tu_ngay, den_ngay))), tu_ngay, den_ngay


# ================================================================ trang dashboard
def _chi_tieu_xem_duoc(db):
    la_admin = g.user["vai_tro"] == "admin"
    rows = db.execute("SELECT * FROM ChiTieu" + ("" if la_admin else " WHERE vai_tro_xem = 'staff'") +
                      " ORDER BY ma").fetchall()
    ket_qua = []
    for r in rows:
        d = dict(r)
        d["ten_trang_thai"] = TEN_TRANG_THAI_CT[d["trang_thai"]]
        ket_qua.append(d)
    return ket_qua


@dashboard_bp.route("/")
@roles_required(*STAFF)
def index():
    db = _db()
    la_admin = g.user["vai_tro"] == "admin"
    loai_ids = _loai_duoc_giao(db)
    if la_admin:
        pham_vi_text = "toàn bộ hệ thống"
    elif loai_ids:
        ten = [r[0] for r in db.execute(
            "SELECT ten_loai FROM LoaiHoTro WHERE id IN (%s) ORDER BY id" % ",".join("?" * len(loai_ids)), loai_ids)]
        pham_vi_text = "các loại hỗ trợ được giao: " + ", ".join(ten)
    else:
        pham_vi_text = "tất cả loại hỗ trợ (chưa được giao phạm vi riêng)"
    return render_template(
        "dashboard/index.html", la_admin=la_admin, sla_gio=SLA_GIO, pham_vi_text=pham_vi_text,
        chi_tieu=_chi_tieu_xem_duoc(db),
        nganh_list=[dict(r) for r in db.execute("SELECT id, ma_nganh, ten_nganh FROM NganhHoc ORDER BY ma_nganh")],
        lop_list=[dict(r) for r in db.execute("SELECT id, ma_lop, ten_lop, nganh_id FROM Lop ORDER BY ma_lop")])


# ================================================================ xuất báo cáo (CSV mở được bằng Excel)
def _o(v):
    """Ô trống thay cho None để file xuất không có chữ 'None'."""
    return "" if v is None else v


def _csv_response(rows, ten_file):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    # BOM giúp Excel đọc đúng tiếng Việt có dấu
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=%s" % ten_file})


def _mo_ta_bo_loc(db, pv):
    """Mô tả bộ lọc đang áp dụng (dùng cho phần đầu file xuất)."""
    nganh = lop = None
    if pv["nganh_id"] is not None:
        r = db.execute("SELECT ma_nganh, ten_nganh FROM NganhHoc WHERE id = ?", (pv["nganh_id"],)).fetchone()
        nganh = "%s - %s" % (r["ma_nganh"], r["ten_nganh"]) if r else "#%s" % pv["nganh_id"]
    if pv["lop_id"] is not None:
        r = db.execute("SELECT ma_lop FROM Lop WHERE id = ?", (pv["lop_id"],)).fetchone()
        lop = r["ma_lop"] if r else "#%s" % pv["lop_id"]
    return [["Từ ngày", pv["tu_ngay"] or "Tất cả"], ["Đến ngày", pv["den_ngay"] or "Tất cả"],
            ["Ngành học", nganh or "Tất cả"], ["Lớp", lop or "Tất cả"]]


def _pham_vi_xuat(db, loai_ids):
    if g.user["vai_tro"] == "admin":
        return "toàn bộ hệ thống"
    if loai_ids:
        ten = [r[0] for r in db.execute(
            "SELECT ten_loai FROM LoaiHoTro WHERE id IN (%s) ORDER BY id" % ",".join("?" * len(loai_ids)), loai_ids)]
        return "các loại hỗ trợ được giao: " + ", ".join(ten)
    return "tất cả loại hỗ trợ"


@dashboard_bp.route("/xuat-bao-cao")
@roles_required(*STAFF)
def xuat_bao_cao():
    """Xuất báo cáo theo đúng bộ lọc và phạm vi đang xem. ?loai=tong-hop (mặc định) hoặc chi-tiet.
    Giống API: không có họ tên, mã sinh viên hay nội dung yêu cầu."""
    db = _db()
    loai_ids = _loai_duoc_giao(db)
    try:
        f, pv = _doc_bo_loc(loai_ids)
    except ValueError as e:
        abort(400, description=str(e))
    kieu = request.args.get("loai", "tong-hop")
    if kieu not in ("tong-hop", "chi-tiet"):
        abort(400, description="loai không hợp lệ.")

    dau = [["BÁO CÁO HOẠT ĐỘNG HỖ TRỢ NGƯỜI HỌC"],
           ["Thời điểm xuất", now_str()],
           ["Người xuất", g.user["ho_ten"]],
           ["Phạm vi", _pham_vi_xuat(db, loai_ids)]] + _mo_ta_bo_loc(db, pv) + [[]]
    ten_file = "bao-cao-ho-tro-%s-%s.csv" % (kieu, datetime.now().strftime("%Y%m%d-%H%M"))

    if kieu == "chi-tiet":
        han = _han_qua_han()
        rows = db.execute(
            "SELECT y.id, lh.ten_loai, y.muc_uu_tien, y.trang_thai, l.ma_lop, y.ngay_tao, y.ngay_giai_quyet, "
            "CASE WHEN y.ngay_giai_quyet IS NULL THEN NULL ELSE " + GIO + " END AS gio " + FROM_Y +
            " JOIN LoaiHoTro lh ON lh.id = y.loai_ho_tro_id WHERE 1 = 1" + f["cond"] +
            " ORDER BY y.ngay_tao DESC, y.id DESC", f["params"]).fetchall()
        out = dau + [["Danh sách yêu cầu (%d yêu cầu)" % len(rows)],
                     ["Mã yêu cầu", "Loại hỗ trợ", "Ưu tiên", "Trạng thái", "Lớp", "Ngày gửi",
                      "Ngày giải quyết", "Giờ giải quyết", "Quá hạn"]]
        for r in rows:
            qua_han = r["trang_thai"] != "da_giai_quyet" and r["ngay_tao"] <= han
            out.append([r["id"], r["ten_loai"], TEN_UU_TIEN.get(r["muc_uu_tien"], r["muc_uu_tien"]),
                        TEN_TRANG_THAI[r["trang_thai"]], r["ma_lop"], r["ngay_tao"],
                        _o(r["ngay_giai_quyet"]), _o(_lam_tron(r["gio"])), "Có" if qua_han else "Không"])
        out += [[], ["Ghi chú", GHI_CHU + " Danh sách không hiện họ tên hay mã sinh viên."]]
        return _csv_response(out, ten_file)

    d = _tinh_ho_tro(db, f)
    t = d["thoi_gian"]
    sv = d["sinh_vien_gui_yeu_cau"]
    out = dau + [
        ["I. TỔNG QUAN"], ["Chỉ số", "Giá trị", "Đơn vị"],
        ["Tổng số yêu cầu", d["tong"], "yêu cầu"],
        ["Tỷ lệ giải quyết", _o(d["ty_le_giai_quyet"]), "%"],
        ["Thời gian tiếp nhận trung bình", _o(t["tiep_nhan_tb_gio"]), "giờ"],
        ["Thời gian giải quyết trung bình", _o(t["giai_quyet_tb_gio"]), "giờ"],
        ["Giải quyết nhanh nhất", _o(t["nhanh_nhat_gio"]), "giờ"],
        ["Giải quyết chậm nhất", _o(t["cham_nhat_gio"]), "giờ"],
        ["Tỷ lệ giải quyết đúng hạn (%d giờ)" % t["sla_gio"], _o(t["ty_le_dung_han"]), "%"],
        ["Số yêu cầu quá hạn", d["qua_han"], "yêu cầu"],
        ["Sinh viên đã gửi yêu cầu", "%s / %s" % (sv["da_gui"], sv["tong_sinh_vien"]), "sinh viên"],
        ["Tỷ lệ sinh viên gửi yêu cầu", _o(sv["ty_le"]), "%"], [],
        ["II. THEO TRẠNG THÁI"], ["Trạng thái", "Số yêu cầu", "Tỷ lệ (%)"]]
    for k, n in d["theo_trang_thai"].items():
        out.append([TEN_TRANG_THAI[k], n, _lam_tron(n / d["tong"] * 100) if d["tong"] else ""])
    out += [[], ["III. THEO LOẠI HỖ TRỢ"], ["Loại hỗ trợ", "Số yêu cầu", "Giờ giải quyết TB"]]
    gio_loai = {x["id"]: x["gio"] for x in t["theo_loai"]}
    for x in d["theo_loai"]:
        out.append([x["ten"], x["so"], _o(gio_loai.get(x["id"]))])
    out += [[], ["IV. THEO THÁNG"], ["Tháng", "Số yêu cầu", "Giờ giải quyết TB"]]
    for x in d["theo_thang"]:
        out.append([x["thang"], x["so"], _o(x["gio_giai_quyet_tb"])])
    out += [[], ["V. THEO NGÀNH"], ["Mã ngành", "Tên ngành", "Số yêu cầu"]]
    for x in d["theo_nganh"]:
        out.append([x["ma"], x["ten"], x["so"]])
    out += [[], ["VI. THEO LỚP"], ["Mã lớp", "Tên lớp", "Số yêu cầu"]]
    for x in d["theo_lop"]:
        out.append([x["ma"], x["ten"], x["so"]])
    out += [[], ["Ghi chú", GHI_CHU]]
    return _csv_response(out, ten_file)


# ================================================================ API
def _meta(f_pv, nguon):
    return {"pham_vi": f_pv, "nguon": nguon, "thoi_diem_tinh": now_str(), "ghi_chu": GHI_CHU}


@dashboard_bp.route("/api/ho-tro")
@roles_required(*STAFF)
def api_ho_tro():
    db = _db()
    try:
        f, pv = _doc_bo_loc(_loai_duoc_giao(db))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    d = _tinh_ho_tro(db, f)
    d.update(_meta(pv, ["YeuCauHoTro", "LoaiHoTro", "LichSuTrangThai", "SinhVien", "Lop", "NganhHoc"]))
    return jsonify(d)


@dashboard_bp.route("/api/chi-tiet")
@roles_required(*STAFF)
def api_chi_tiet():
    """Danh sách yêu cầu phía sau một con số trên biểu đồ. Cùng bộ lọc với /api/ho-tro nên số khớp nhau.
    Không trả họ tên, mã sinh viên hay nội dung yêu cầu."""
    db = _db()
    try:
        f, pv = _doc_bo_loc(_loai_duoc_giao(db))
        loai = _so_nguyen(request.args.get("loai"), "loai")
        trang = _so_nguyen(request.args.get("page"), "page") or 1
    except ValueError as e:
        return jsonify(error=str(e)), 400
    cond, params = f["cond"], list(f["params"])
    loc = {}
    tt = request.args.get("trang_thai", "").strip()
    if tt:
        if tt not in TRANG_THAI:
            return jsonify(error="trang_thai không hợp lệ."), 400
        cond += " AND y.trang_thai = ?"
        params.append(tt)
        loc["trang_thai"] = tt
    if loai is not None:
        cond += " AND y.loai_ho_tro_id = ?"
        params.append(loai)
        loc["loai"] = loai
    if request.args.get("qua_han") == "1":
        cond += " AND y.trang_thai != 'da_giai_quyet' AND y.ngay_tao <= ?"
        params.append(_han_qua_han())
        loc["qua_han"] = True

    base = FROM_Y + " JOIN LoaiHoTro lh ON lh.id = y.loai_ho_tro_id WHERE 1 = 1" + cond
    tong = db.execute("SELECT COUNT(*) " + base, params).fetchone()[0]
    so_trang = max(1, math.ceil(tong / PER_PAGE))
    trang = min(max(trang, 1), so_trang)
    rows = db.execute(
        "SELECT y.id, y.trang_thai, y.muc_uu_tien, y.ngay_tao, y.ngay_giai_quyet, lh.ten_loai, l.ma_lop, "
        "CASE WHEN y.ngay_giai_quyet IS NULL THEN NULL ELSE " + GIO + " END AS gio " + base +
        " ORDER BY y.ngay_tao DESC, y.id DESC LIMIT ? OFFSET ?",
        params + [PER_PAGE, (trang - 1) * PER_PAGE]).fetchall()
    muc = [{"id": r["id"], "loai": r["ten_loai"], "trang_thai": r["trang_thai"],
            "ten_trang_thai": TEN_TRANG_THAI[r["trang_thai"]],
            "uu_tien": TEN_UU_TIEN.get(r["muc_uu_tien"], r["muc_uu_tien"]), "lop": r["ma_lop"],
            "ngay_tao": r["ngay_tao"], "gio_giai_quyet": _lam_tron(r["gio"]),
            "url": url_for("support.detail", yc_id=r["id"])} for r in rows]
    pv["bo_loc_them"] = loc
    out = {"tong": tong, "trang": trang, "so_trang": so_trang, "muc": muc}
    out.update(_meta(pv, ["YeuCauHoTro", "LoaiHoTro", "SinhVien", "Lop"]))
    out["ghi_chu"] = GHI_CHU + " Danh sách không hiện họ tên hay mã sinh viên."
    return jsonify(out)


@dashboard_bp.route("/api/sinh-vien")
@roles_required("admin")
def api_sinh_vien():
    try:
        f, pv = _doc_bo_loc()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db, cond, params = _db(), f["cond_sv"], f["params_sv"]
    tong = db.execute("SELECT COUNT(*) FROM SinhVien sv JOIN Lop l ON l.id = sv.lop_id WHERE 1 = 1" + cond,
                      params).fetchone()[0]
    theo_lop = [{"ma": r["ma_lop"], "ten": r["ten_lop"], "so": r["n"]} for r in db.execute(
        "SELECT l.ma_lop, l.ten_lop, COUNT(sv.id) AS n FROM Lop l LEFT JOIN SinhVien sv ON sv.lop_id = l.id "
        "WHERE 1 = 1" + cond + " GROUP BY l.id ORDER BY l.ma_lop", params)]
    theo_nganh = [{"ma": r["ma_nganh"], "ten": r["ten_nganh"], "so": r["n"]} for r in db.execute(
        "SELECT n.ma_nganh, n.ten_nganh, COUNT(sv.id) AS n FROM NganhHoc n JOIN Lop l ON l.nganh_id = n.id "
        "LEFT JOIN SinhVien sv ON sv.lop_id = l.id WHERE 1 = 1" + cond + " GROUP BY n.id ORDER BY n.ma_nganh",
        params)]
    theo_khoa = [{"ten": r["khoa_hoc"], "so": r["n"]} for r in db.execute(
        "SELECT l.khoa_hoc, COUNT(sv.id) AS n FROM Lop l LEFT JOIN SinhVien sv ON sv.lop_id = l.id "
        "WHERE 1 = 1" + cond + " GROUP BY l.khoa_hoc ORDER BY l.khoa_hoc", params)]
    theo_hoc = [{"ten": r["trang_thai"], "so": r["n"]} for r in db.execute(
        "SELECT sv.trang_thai, COUNT(*) AS n FROM SinhVien sv JOIN Lop l ON l.id = sv.lop_id WHERE 1 = 1" +
        cond + " GROUP BY sv.trang_thai ORDER BY n DESC", params)]
    pv_sv = {"nganh_id": pv["nganh_id"], "lop_id": pv["lop_id"],
             "tinh_theo": "toàn bộ hồ sơ sinh viên, không lọc theo ngày"}
    out = {"tong": tong, "theo_lop": theo_lop, "theo_nganh": theo_nganh, "theo_khoa": theo_khoa,
           "theo_trang_thai_hoc": theo_hoc}
    out.update(_meta(pv_sv, ["SinhVien", "Lop", "NganhHoc"]))
    out["ghi_chu"] = GHI_CHU + " Chỉ có số liệu tổng hợp, không có dữ liệu cá nhân."
    return jsonify(out)


@dashboard_bp.route("/api/he-thong")
@roles_required("admin")
def api_he_thong():
    try:
        f, pv = _doc_bo_loc()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db = _db()
    tai_khoan = [{"vai_tro": r["vai_tro"], "ten": TEN_VAI_TRO.get(r["vai_tro"], r["vai_tro"]), "so": r["n"]}
                 for r in db.execute("SELECT vai_tro, COUNT(*) AS n FROM TaiKhoan GROUP BY vai_tro ORDER BY n DESC")]
    ph = db.execute("SELECT COALESCE(SUM(CASE WHEN la_noi_bo = 0 THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(CASE WHEN la_noi_bo = 1 THEN 1 ELSE 0 END), 0), COUNT(*) FROM PhanHoi").fetchone()
    nhan_vien = [{"ten": r["ten"], "so": r["n"], "da_giai_quyet": r["xong"]} for r in db.execute(
        "SELECT COALESCE(tk.ho_ten, tk.username, 'Chưa phân công') AS ten, COUNT(*) AS n, "
        "SUM(CASE WHEN y.trang_thai = 'da_giai_quyet' THEN 1 ELSE 0 END) AS xong " + FROM_Y +
        " LEFT JOIN TaiKhoan tk ON tk.id = y.nguoi_xu_ly_id WHERE 1 = 1" + f["cond"] +
        " GROUP BY y.nguoi_xu_ly_id ORDER BY n DESC", f["params"])]
    out = {"tai_khoan_theo_vai_tro": tai_khoan,
           "phan_hoi": {"cong_khai": ph[0], "noi_bo": ph[1], "tong": ph[2]},
           "so_lan_doi_trang_thai": db.execute("SELECT COUNT(*) FROM LichSuTrangThai").fetchone()[0],
           "yeu_cau_theo_nhan_vien": nhan_vien}
    pv["ghi_chu_pham_vi"] = "Tài khoản và phản hồi tính trên toàn hệ thống; yêu cầu theo nhân viên theo bộ lọc."
    out.update(_meta(pv, ["TaiKhoan", "PhanHoi", "LichSuTrangThai", "YeuCauHoTro"]))
    return jsonify(out)


# ================================================================ danh mục chỉ tiêu và quy trình công bố
def _lay_chi_tieu(db, ma):
    ct = db.execute("SELECT * FROM ChiTieu WHERE ma = ?", (ma,)).fetchone()
    if ct is None or (g.user["vai_tro"] != "admin" and ct["vai_tro_xem"] == "admin"):
        abort(404)
    return ct


@dashboard_bp.route("/chi-tieu")
@roles_required(*STAFF)
def chi_tieu_list():
    db = _db()
    moi_nhat = {r["chi_tieu_id"]: r for r in db.execute(
        "SELECT k.* FROM KetQuaChiTieu k WHERE k.id = "
        "(SELECT MAX(id) FROM KetQuaChiTieu WHERE chi_tieu_id = k.chi_tieu_id)")}
    return render_template("dashboard/chi_tieu.html", chi_tieu=_chi_tieu_xem_duoc(db), moi_nhat=moi_nhat,
                           mau=MAU_TRANG_THAI_CT, la_admin=g.user["vai_tro"] == "admin")


@dashboard_bp.route("/chi-tieu/<ma>")
@roles_required(*STAFF)
def chi_tieu_detail(ma):
    db = _db()
    ct = _lay_chi_tieu(db, ma)
    lich_su = []
    for r in db.execute(
            "SELECT h.*, tk.ho_ten FROM LichSuChiTieu h LEFT JOIN TaiKhoan tk ON tk.id = h.nguoi_thuc_hien_id "
            "WHERE h.chi_tieu_id = ? ORDER BY h.id DESC", (ct["id"],)):
        d = dict(r)
        d["truoc"] = json.loads(d["noi_dung_truoc"]) if d["noi_dung_truoc"] else None
        lich_su.append(d)
    ket_qua = db.execute(
        "SELECT k.*, tk.ho_ten FROM KetQuaChiTieu k LEFT JOIN TaiKhoan tk ON tk.id = k.nguoi_cong_bo_id "
        "WHERE k.chi_tieu_id = ? ORDER BY k.id DESC", (ct["id"],)).fetchall()
    return render_template(
        "dashboard/chi_tieu_chi_tiet.html", ct=ct, lich_su=lich_su, ket_qua=ket_qua, dash_csrf=_csrf(),
        la_admin=g.user["vai_tro"] == "admin", ten_tt=TEN_TRANG_THAI_CT, mau=MAU_TRANG_THAI_CT,
        ten_hd=TEN_HANH_DONG, nhan=NHAN_TRUONG, cho_phep={k: v[0] for k, v in CHUYEN.items()},
        buoc=("nhap", "da_xac_nhan_nguon", "da_kiem_tra", "da_cong_bo"))


@dashboard_bp.route("/chi-tieu/<ma>/chuyen", methods=["POST"])
@roles_required("admin")
def chi_tieu_chuyen(ma):
    _kiem_csrf()
    db = _db()
    ct = _lay_chi_tieu(db, ma)
    quay_lai = redirect(url_for("dashboard.chi_tieu_detail", ma=ma))
    hanh_dong = request.form.get("hanh_dong", "")
    if hanh_dong not in CHUYEN:
        abort(400, "Hành động không hợp lệ.")
    tu_cac, trang_thai_moi = CHUYEN[hanh_dong]
    if ct["trang_thai"] not in tu_cac:
        flash("Không thể «%s» khi chỉ tiêu đang ở trạng thái «%s»." %
              (TEN_HANH_DONG[hanh_dong], TEN_TRANG_THAI_CT[ct["trang_thai"]]), "danger")
        return quay_lai
    can_cu = request.form.get("can_cu", "").strip()
    if hanh_dong == "tra_ve" and not can_cu:
        flash("Hãy ghi lý do trả về nháp.", "danger")
        return quay_lai
    now = now_str()
    if hanh_dong == "cong_bo":
        try:
            tu = _ngay_hop_le(request.form.get("tu_ngay"), "Từ ngày")
            den = _ngay_hop_le(request.form.get("den_ngay"), "Đến ngày")
            if tu and den and tu > den:
                raise ValueError("Từ ngày không được sau đến ngày.")
            gia_tri, ky_tu, ky_den = _tinh_gia_tri(db, ma, tu, den)
        except ValueError as e:
            flash(str(e), "danger")
            return quay_lai
        db.execute(
            """INSERT INTO KetQuaChiTieu(chi_tieu_id, phien_ban, ky_tu, ky_den, chieu, gia_tri, thoi_diem_tinh,
                                         nguoi_cong_bo_id) VALUES (?, ?, ?, ?, 'toan_he_thong', ?, ?, ?)""",
            (ct["id"], ct["phien_ban"], ky_tu, ky_den, gia_tri, now, g.user["id"]))
    db.execute("UPDATE ChiTieu SET trang_thai = ?, ngay_cap_nhat = ? WHERE id = ?",
               (trang_thai_moi, now, ct["id"]))
    db.execute(
        """INSERT INTO LichSuChiTieu(chi_tieu_id, phien_ban, hanh_dong, trang_thai_cu, trang_thai_moi,
                                     nguoi_thuc_hien_id, can_cu, ngay_thuc_hien) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ct["id"], ct["phien_ban"], hanh_dong, ct["trang_thai"], trang_thai_moi, g.user["id"], can_cu or None, now))
    db.commit()
    flash("Đã thực hiện: %s." % TEN_HANH_DONG[hanh_dong], "success")
    return quay_lai


@dashboard_bp.route("/chi-tieu/<ma>/sua", methods=["POST"])
@roles_required("admin")
def chi_tieu_sua(ma):
    _kiem_csrf()
    db = _db()
    ct = _lay_chi_tieu(db, ma)
    quay_lai = redirect(url_for("dashboard.chi_tieu_detail", ma=ma))
    moi = {k: request.form.get(k, "").strip() for k in TRUONG_DINH_NGHIA}
    can_cu = request.form.get("can_cu", "").strip()
    thieu = [NHAN_TRUONG[k] for k in TRUONG_DINH_NGHIA if k != "chieu_phan_tich" and not moi[k]]
    if thieu:
        flash("Còn thiếu: " + ", ".join(thieu) + ".", "danger")
        return quay_lai
    if not can_cu:
        flash("Hãy ghi căn cứ điều chỉnh (vì sao sửa định nghĩa).", "danger")
        return quay_lai
    if all(moi[k] == (ct[k] or "") for k in TRUONG_DINH_NGHIA):
        flash("Không có nội dung nào thay đổi.", "info")
        return quay_lai
    truoc = json.dumps({k: ct[k] for k in TRUONG_DINH_NGHIA}, ensure_ascii=False)
    phien_ban, now = ct["phien_ban"] + 1, now_str()
    db.execute(
        """UPDATE ChiTieu SET ten = ?, cong_thuc = ?, don_vi = ?, chieu_phan_tich = ?, nguon = ?, dau_moi = ?,
                              phien_ban = ?, trang_thai = 'nhap', ngay_cap_nhat = ? WHERE id = ?""",
        (moi["ten"], moi["cong_thuc"], moi["don_vi"], moi["chieu_phan_tich"] or None, moi["nguon"],
         moi["dau_moi"], phien_ban, now, ct["id"]))
    db.execute(
        """INSERT INTO LichSuChiTieu(chi_tieu_id, phien_ban, hanh_dong, trang_thai_cu, trang_thai_moi,
                                     nguoi_thuc_hien_id, can_cu, noi_dung_truoc, ngay_thuc_hien)
           VALUES (?, ?, 'sua_dinh_nghia', ?, 'nhap', ?, ?, ?, ?)""",
        (ct["id"], phien_ban, ct["trang_thai"], g.user["id"], can_cu, truoc, now))
    db.commit()
    flash("Đã lưu định nghĩa, phiên bản %d. Chỉ tiêu quay về Nháp để xác nhận và kiểm tra lại." % phien_ban, "success")
    return quay_lai


# ================================================================ phạm vi của nhân viên hỗ trợ
@dashboard_bp.route("/pham-vi", methods=["GET", "POST"])
@roles_required("admin")
def pham_vi():
    db = _db()
    nhan_vien = db.execute(
        "SELECT id, username, ho_ten FROM TaiKhoan WHERE vai_tro = 'support_staff' ORDER BY id").fetchall()
    loai = db.execute("SELECT id, ten_loai FROM LoaiHoTro ORDER BY id").fetchall()
    if request.method == "POST":
        _kiem_csrf()
        hop_le = {r["id"] for r in loai}
        for nv in nhan_vien:
            chon = {int(x) for x in request.form.getlist("loai_%d" % nv["id"]) if x.isdigit()} & hop_le
            db.execute("DELETE FROM PhamViNhanVien WHERE tai_khoan_id = ?", (nv["id"],))
            db.executemany("INSERT INTO PhamViNhanVien(tai_khoan_id, loai_ho_tro_id) VALUES (?, ?)",
                           [(nv["id"], i) for i in sorted(chon)])
        db.commit()
        flash("Đã lưu phạm vi của nhân viên hỗ trợ.", "success")
        return redirect(url_for("dashboard.pham_vi"))
    hien_tai = {(r["tai_khoan_id"], r["loai_ho_tro_id"]) for r in db.execute("SELECT * FROM PhamViNhanVien")}
    return render_template("dashboard/pham_vi.html", nhan_vien=nhan_vien, loai=loai, hien_tai=hien_tai,
                           dash_csrf=_csrf())
