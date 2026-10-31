"""M12 - Hỗ trợ người học: gửi yêu cầu, phản hồi, đổi trạng thái, lịch sử, API tổng hợp cho M17.

Quy ước nhóm: trạng thái = cho_xu_ly | dang_xu_ly | da_giai_quyet (lưu không dấu, hiển thị có dấu).
Mọi thay đổi trạng thái PHẢI đi qua doi_trang_thai() để lịch sử và ngay_giai_quyet luôn đúng.
"""
import math
from datetime import datetime, timedelta

from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from auth import login_required, roles_required
from models import get_db, normalize

support_bp = Blueprint("support", __name__, url_prefix="/support")

PER_PAGE = 10
STAFF = ("support_staff", "admin")

TRANG_THAI = ("cho_xu_ly", "dang_xu_ly", "da_giai_quyet")
TEN_TRANG_THAI = {"cho_xu_ly": "Chờ xử lý", "dang_xu_ly": "Đang xử lý",
                  "da_giai_quyet": "Đã giải quyết"}
MUC_UU_TIEN = ("thap", "trung_binh", "cao")
TEN_UU_TIEN = {"thap": "Thấp", "trung_binh": "Trung Bình", "cao": "Cao"}
# Ưu tiên tự gán theo loại hỗ trợ (sinh viên không chọn)
UU_TIEN_THEO_LOAI = {"tai_khoan": "cao", "hoc_phi": "trung_binh", "hoc_vu": "trung_binh",
                     "ky_thuat": "thap", "khac": "thap"}

# Từ trạng thái hiện tại -> các trạng thái được phép chuyển tới
CHUYEN_HOP_LE = {
    "cho_xu_ly": ("dang_xu_ly",),
    "dang_xu_ly": ("da_giai_quyet",),
    "da_giai_quyet": ("dang_xu_ly",),  # mở lại
}

TICKET_SQL = """
SELECT y.*, lh.ma_loai, lh.ten_loai,
       sv.ma_sv, sv.ho_ten AS ho_ten_sv, l.ma_lop,
       tk.ho_ten AS ten_nguoi_xu_ly
FROM YeuCauHoTro y
JOIN LoaiHoTro lh ON lh.id = y.loai_ho_tro_id
JOIN SinhVien sv ON sv.id = y.sinh_vien_id
JOIN Lop l ON l.id = sv.lop_id
LEFT JOIN TaiKhoan tk ON tk.id = y.nguoi_xu_ly_id
"""
COUNT_SQL = """
SELECT COUNT(*) FROM YeuCauHoTro y
JOIN LoaiHoTro lh ON lh.id = y.loai_ho_tro_id
JOIN SinhVien sv ON sv.id = y.sinh_vien_id
"""


@support_bp.app_template_filter("dmy_gio")
def dmy_gio(value):
    """2026-10-20 10:30:00 -> 20/10/2026 10:30"""
    if not value:
        return "—"
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


# ---------------------------------------------------------------- nghiệp vụ
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SLA_GIO, CANH_BAO_GIO = 24, 2

def _doan(giay):
    h, m = divmod(giay // 60, 60)
    return "%d ngày %dg" % (h // 24, h % 24) if h >= 24 else "%dg %02dp" % (h, m)

def sla_info(t):
    """Hạn = ngay_tao + 24h. Chỉ trả nhãn khi còn <= CANH_BAO_GIO giờ hoặc đã quá hạn; ngoài ra None."""
    if t["trang_thai"] == "da_giai_quyet":
        return None
    han = datetime.strptime(t["ngay_tao"][:19], "%Y-%m-%d %H:%M:%S") + timedelta(hours=SLA_GIO)
    giay = int((han - datetime.now()).total_seconds())
    if giay < 0:
        return {"muc": "qua_han", "nhan": "Quá hạn " + _doan(-giay)}
    if giay <= CANH_BAO_GIO * 3600:
        return {"muc": "sap_het", "nhan": "Còn " + _doan(giay)}
    return None




def _is_int(text):
    return text.isascii() and text.isdigit()


def doi_trang_thai(db, yc, trang_thai_moi, nguoi_dung, ghi_chu=None):
    """Đổi trạng thái + ghi lịch sử. Không commit: nơi gọi tự commit."""
    cu = yc["trang_thai"]
    if trang_thai_moi not in CHUYEN_HOP_LE.get(cu, ()):
        raise ValueError("Không thể chuyển từ “%s” sang “%s”." % (
            TEN_TRANG_THAI.get(cu, cu), TEN_TRANG_THAI.get(trang_thai_moi, trang_thai_moi)))
    now = now_str()
    ngay_giai_quyet = now if trang_thai_moi == "da_giai_quyet" else None  # mở lại -> NULL
    db.execute(
        """UPDATE YeuCauHoTro SET trang_thai = ?, ngay_giai_quyet = ?, ngay_cap_nhat = ?,
                  nguoi_xu_ly_id = COALESCE(nguoi_xu_ly_id, ?) WHERE id = ?""",
        (trang_thai_moi, ngay_giai_quyet, now, nguoi_dung["id"], yc["id"]))
    db.execute(
        """INSERT INTO LichSuTrangThai(yeu_cau_id, trang_thai_cu, trang_thai_moi,
                                       nguoi_thay_doi_id, ghi_chu, ngay_thay_doi)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (yc["id"], cu, trang_thai_moi, nguoi_dung["id"], ghi_chu or None, now))


def get_ticket_or_404(db, yc_id):
    """Lấy yêu cầu; sinh viên chỉ được xem yêu cầu CỦA MÌNH (kiểm tra ở server)."""
    yc = db.execute(TICKET_SQL + " WHERE y.id = ?", (yc_id,)).fetchone()
    if yc is None:
        abort(404)
    if g.user["vai_tro"] == "student" and yc["sinh_vien_id"] != g.user["sinh_vien_id"]:
        abort(403)
    return yc


# ---------------------------------------------------------------- sinh viên
@support_bp.route("/")
@login_required
def index():
    if g.user["vai_tro"] == "student":
        return redirect(url_for("support.my_tickets"))
    return redirect(url_for("support.manage"))


@support_bp.route("/my")
@roles_required("student")
def my_tickets():
    rows = get_db().execute(
        TICKET_SQL + " WHERE y.sinh_vien_id = ? ORDER BY y.ngay_tao DESC, y.id DESC",
        (g.user["sinh_vien_id"],)).fetchall()
    return render_template("support/my.html", tickets=rows)


@support_bp.route("/new", methods=["GET", "POST"])
@roles_required("student")
def new_ticket():
    db = get_db()
    if g.user["sinh_vien_id"] is None:
        abort(403)
    loai_list = db.execute("SELECT id, ma_loai, ten_loai FROM LoaiHoTro ORDER BY id").fetchall()
    data, errors = {}, {}

    if request.method == "POST":
        data = {
            "loai_ho_tro_id": request.form.get("loai_ho_tro_id", "").strip(),
            "tieu_de": " ".join(request.form.get("tieu_de", "").split()),
            "noi_dung": request.form.get("noi_dung", "").strip(),
        }
        loai = db.execute("SELECT ma_loai FROM LoaiHoTro WHERE id = ?",
                          (int(data["loai_ho_tro_id"]),)).fetchone() \
            if _is_int(data["loai_ho_tro_id"]) else None
        if loai is None:
            errors["loai_ho_tro_id"] = "Vui lòng chọn loại hỗ trợ."
        if not 3 <= len(data["tieu_de"]) <= 200:
            errors["tieu_de"] = "Tiêu đề phải từ 3 đến 200 ký tự."
        if not 10 <= len(data["noi_dung"]) <= 5000:
            errors["noi_dung"] = "Nội dung phải từ 10 đến 5000 ký tự để nhân viên hiểu rõ vấn đề."

        if not errors:
            now = now_str()
            cur = db.execute(
                """INSERT INTO YeuCauHoTro(sinh_vien_id, loai_ho_tro_id, tieu_de, noi_dung,
                                           muc_uu_tien, trang_thai, ngay_tao, ngay_cap_nhat)
                   VALUES (?, ?, ?, ?, ?, 'cho_xu_ly', ?, ?)""",
                (g.user["sinh_vien_id"], int(data["loai_ho_tro_id"]), data["tieu_de"],
                 data["noi_dung"], UU_TIEN_THEO_LOAI.get(loai["ma_loai"], "thap"), now, now))
            db.execute(
                """INSERT INTO LichSuTrangThai(yeu_cau_id, trang_thai_cu, trang_thai_moi,
                                               nguoi_thay_doi_id, ghi_chu, ngay_thay_doi)
                   VALUES (?, NULL, 'cho_xu_ly', ?, 'Sinh viên gửi yêu cầu', ?)""",
                (cur.lastrowid, g.user["id"], now))
            db.commit()
            flash("Đã gửi yêu cầu hỗ trợ. Bạn có thể theo dõi kết quả xử lý tại trang này.", "success")
            return redirect(url_for("support.detail", yc_id=cur.lastrowid))

    return render_template("support/new.html", loai_list=loai_list, data=data, errors=errors)

# ---------------------------------------------------------------- nhân viên / admin
@support_bp.route("/manage")
@roles_required(*STAFF)
def manage():
    db = get_db()
    where, params = [], []

    trang_thai = request.args.get("trang_thai", "").strip()
    if trang_thai in TRANG_THAI:
        where.append("y.trang_thai = ?")
        params.append(trang_thai)
    else:
        trang_thai = ""

    loai = request.args.get("loai", "").strip()
    if _is_int(loai):
        where.append("y.loai_ho_tro_id = ?")
        params.append(int(loai))
    else:
        loai = ""

    q = request.args.get("q", "").strip()
    if q:
        like = "%" + normalize(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(norm(y.tieu_de) LIKE ? ESCAPE '\\' OR norm(sv.ma_sv) LIKE ? ESCAPE '\\' "
                     "OR norm(sv.ho_ten) LIKE ? ESCAPE '\\')")
        params += [like] * 3

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.execute(COUNT_SQL + clause, params).fetchone()[0]
    pages = max(1, math.ceil(total / PER_PAGE))
    page_arg = request.args.get("page", "1").strip()
    page = min(max(int(page_arg) if _is_int(page_arg) else 1, 1), pages)

    gan_han = (datetime.now() - timedelta(hours=SLA_GIO - CANH_BAO_GIO)).strftime("%Y-%m-%d %H:%M:%S")
    tickets = db.execute(
        TICKET_SQL + clause +
        """ ORDER BY CASE WHEN y.trang_thai = 'da_giai_quyet' THEN 9
                          WHEN y.ngay_tao <= ? THEN 0
                          ELSE 1 + CASE y.muc_uu_tien WHEN 'cao' THEN 0 WHEN 'trung_binh' THEN 1 ELSE 2 END END,
                     CASE WHEN y.trang_thai = 'da_giai_quyet' THEN -julianday(y.ngay_tao)
                          ELSE julianday(y.ngay_tao) END, y.id LIMIT ? OFFSET ?""",
        params + [gan_han, PER_PAGE, (page - 1) * PER_PAGE]).fetchall()

    counts = {r["trang_thai"]: r["n"] for r in db.execute(
        "SELECT trang_thai, COUNT(*) AS n FROM YeuCauHoTro GROUP BY trang_thai")}
    return render_template(
        "support/manage.html", tickets=tickets, total=total, page=page, pages=pages,sla={t["id"]: sla_info(t) for t in tickets},
        f={"trang_thai": trang_thai, "loai": loai, "q": q},
        counts=counts, tong=sum(counts.values()),
        loai_list=db.execute("SELECT id, ten_loai FROM LoaiHoTro ORDER BY id").fetchall(),
        trang_thai_list=[(v, TEN_TRANG_THAI[v]) for v in TRANG_THAI])


# ---------------------------------------------------------------- chi tiết (dùng chung)
@support_bp.route("/<int:yc_id>")
@login_required
def detail(yc_id):
    db = get_db()
    yc = get_ticket_or_404(db, yc_id)
    la_nhan_vien = g.user["vai_tro"] in STAFF
    # Ghi chú nội bộ lọc ngay trong SQL: sinh viên không bao giờ nhận được dữ liệu này.
    messages = db.execute(
        """SELECT p.*, tk.ho_ten, tk.vai_tro FROM PhanHoi p
           JOIN TaiKhoan tk ON tk.id = p.nguoi_gui_id
           WHERE p.yeu_cau_id = ? """ + ("" if la_nhan_vien else "AND p.la_noi_bo = 0 ") +
        "ORDER BY p.ngay_tao, p.id", (yc_id,)).fetchall()
    history = db.execute(
        """SELECT h.*, tk.ho_ten FROM LichSuTrangThai h
           LEFT JOIN TaiKhoan tk ON tk.id = h.nguoi_thay_doi_id
           WHERE h.yeu_cau_id = ? ORDER BY h.ngay_thay_doi, h.id""", (yc_id,)).fetchall()
    next_states = [(v, TEN_TRANG_THAI[v]) for v in CHUYEN_HOP_LE[yc["trang_thai"]]]
    return render_template("support/detail.html", yc=yc, messages=messages, history=history,
                           la_nhan_vien=la_nhan_vien, next_states=next_states)


@support_bp.route("/<int:yc_id>/reply", methods=["POST"])
@login_required
def reply(yc_id):
    db = get_db()
    yc = get_ticket_or_404(db, yc_id)  # sinh viên chỉ trả lời yêu cầu của mình
    noi_dung = request.form.get("noi_dung", "").strip()
    if not noi_dung or len(noi_dung) > 5000:
        flash("Nội dung phản hồi phải từ 1 đến 5000 ký tự.", "danger")
        return redirect(url_for("support.detail", yc_id=yc_id))

    la_nhan_vien = g.user["vai_tro"] in STAFF
    noi_bo = 1 if (la_nhan_vien and request.form.get("la_noi_bo")) else 0
    now = now_str()
    db.execute("""INSERT INTO PhanHoi(yeu_cau_id, nguoi_gui_id, noi_dung, la_noi_bo, ngay_tao)
                  VALUES (?, ?, ?, ?, ?)""", (yc_id, g.user["id"], noi_dung, noi_bo, now))
    db.execute("UPDATE YeuCauHoTro SET ngay_cap_nhat = ? WHERE id = ?", (now, yc_id))
    if la_nhan_vien and yc["trang_thai"] == "cho_xu_ly":  # phản hồi đầu tiên -> đang xử lý
        doi_trang_thai(db, yc, "dang_xu_ly", g.user, "Tự động khi nhân viên phản hồi lần đầu")
    db.commit()
    flash("Đã ghi chú nội bộ." if noi_bo else "Đã gửi phản hồi.", "success")
    return redirect(url_for("support.detail", yc_id=yc_id))


@support_bp.route("/<int:yc_id>/status", methods=["POST"])
@roles_required(*STAFF)
def update_status(yc_id):
    db = get_db()
    yc = get_ticket_or_404(db, yc_id)
    ghi_chu = " ".join(request.form.get("ghi_chu", "").split())[:255]
    try:
        doi_trang_thai(db, yc, request.form.get("trang_thai", ""), g.user, ghi_chu)
        db.commit()
        flash("Đã cập nhật trạng thái yêu cầu.", "success")
    except ValueError as e:
        db.rollback()
        flash(str(e), "danger")
    return redirect(url_for("support.detail", yc_id=yc_id))


@support_bp.route("/<int:yc_id>/assign", methods=["POST"])
@roles_required(*STAFF)
def assign(yc_id):
    db = get_db()
    get_ticket_or_404(db, yc_id)
    db.execute("UPDATE YeuCauHoTro SET nguoi_xu_ly_id = ?, ngay_cap_nhat = ? WHERE id = ?",
               (g.user["id"], now_str(), yc_id))
    db.commit()
    flash("Bạn đã nhận xử lý yêu cầu này.", "success")
    return redirect(url_for("support.detail", yc_id=yc_id))


# ---------------------------------------------------------------- API cho dashboard M17 (Hà)
@support_bp.route("/api/summary")
@roles_required("admin")
def api_summary():
    """Tổng hợp yêu cầu hỗ trợ. Lọc: ?tu_ngay=YYYY-MM-DD&den_ngay=YYYY-MM-DD (theo ngay_tao)."""
    db = get_db()
    cond, params = "", []
    for key, op in (("tu_ngay", ">="), ("den_ngay", "<=")):
        value = request.args.get(key, "").strip()
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return jsonify(error="%s phải có dạng YYYY-MM-DD." % key), 400
            cond += " AND date(y.ngay_tao) %s ?" % op
            params.append(value)

    base = "FROM YeuCauHoTro y JOIN LoaiHoTro lh ON lh.id = y.loai_ho_tro_id WHERE 1 = 1" + cond
    tong = db.execute("SELECT COUNT(*) " + base, params).fetchone()[0]
    theo_tt = {r["trang_thai"]: r["n"] for r in db.execute(
        "SELECT y.trang_thai, COUNT(*) AS n " + base + " GROUP BY y.trang_thai", params)}
    theo_loai = {r["ten_loai"]: r["n"] for r in db.execute(
        "SELECT lh.ten_loai, COUNT(*) AS n " + base + " GROUP BY lh.id ORDER BY lh.id", params)}
    theo_thang = {r["thang"]: r["n"] for r in db.execute(
        "SELECT strftime('%Y-%m', y.ngay_tao) AS thang, COUNT(*) AS n " + base +
        " GROUP BY thang ORDER BY thang", params)}
    gio_tb = db.execute(
        "SELECT AVG((julianday(y.ngay_giai_quyet) - julianday(y.ngay_tao)) * 24) " + base +
        " AND y.ngay_giai_quyet IS NOT NULL", params).fetchone()[0]
    xong = theo_tt.get("da_giai_quyet", 0)
    return jsonify(
        tong=tong,
        theo_trang_thai={k: theo_tt.get(k, 0) for k in TRANG_THAI},
        theo_loai=theo_loai,
        theo_thang=theo_thang,
        ty_le_xu_ly=round(xong / tong * 100, 2) if tong else 0,
        gio_xu_ly_trung_binh=round(gio_tb, 1) if gio_tb is not None else None,
        pham_vi={"tu_ngay": request.args.get("tu_ngay") or None,
                 "den_ngay": request.args.get("den_ngay") or None,
                 "tinh_theo": "ngay_tao", "thoi_diem_tinh": now_str()},
        nguon=["YeuCauHoTro", "LoaiHoTro"],
        ghi_chu="ty_le_xu_ly = da_giai_quyet / tong x 100. Đây là chỉ số nội bộ, không phải KPI chính thức.")
