"""M03 - Quản lý sinh viên: danh sách, tìm kiếm, chi tiết, thêm/sửa/xóa và API JSON."""
import math
import re
import sqlite3
from datetime import date, datetime

from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)
from werkzeug.security import generate_password_hash

from auth import login_required, roles_required
from models import get_db, normalize

students_bp = Blueprint("students", __name__, url_prefix="/students")
api_bp = Blueprint("students_api", __name__, url_prefix="/api/students")

PER_PAGE = 10
GIOI_TINH = ["Nam", "Nữ", "Khác"]
TRANG_THAI = ["Đang học", "Bảo lưu", "Đã tốt nghiệp", "Thôi học"]
DEFAULT_PASSWORD = "123456"

SELECT_COLS = """SELECT sv.*, l.ma_lop, l.ten_lop, l.khoa_hoc,
                        n.id AS nganh_id, n.ma_nganh, n.ten_nganh """
FROM_CLAUSE = """FROM SinhVien sv
                 JOIN Lop l ON l.id = sv.lop_id
                 JOIN NganhHoc n ON n.id = l.nganh_id"""


# ---------------------------------------------------------------- truy vấn
def _is_int(text):
    return text.isascii() and text.isdigit()


def query_students(args, per_page=PER_PAGE):
    """Lọc + phân trang. Dùng chung cho trang danh sách và API."""
    where, params = [], []

    q = args.get("q", "").strip()
    if q:
        like = "%" + normalize(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(norm(sv.ma_sv) LIKE ? ESCAPE '\\' OR norm(sv.ho_ten) LIKE ? ESCAPE '\\' "
                     "OR norm(l.ma_lop) LIKE ? ESCAPE '\\' OR norm(l.ten_lop) LIKE ? ESCAPE '\\')")
        params += [like] * 4

    for key, column in (("nganh_id", "n.id"), ("lop_id", "l.id")):
        value = args.get(key, "").strip()
        if _is_int(value):
            where.append(f"{column} = ?")
            params.append(int(value))

    khoa = args.get("khoa_hoc", "").strip()
    if khoa:
        where.append("l.khoa_hoc = ?")
        params.append(khoa)

    trang_thai = args.get("trang_thai", "").strip()
    if trang_thai:
        where.append("sv.trang_thai = ?")
        params.append(trang_thai)

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    db = get_db()
    total = db.execute("SELECT COUNT(*) " + FROM_CLAUSE + clause, params).fetchone()[0]
    pages = max(1, math.ceil(total / per_page))

    page_arg = args.get("page", "1").strip()
    page = int(page_arg) if _is_int(page_arg) else 1
    page = min(max(page, 1), pages)

    rows = db.execute(
        SELECT_COLS + FROM_CLAUSE + clause + " ORDER BY sv.ma_sv LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page]).fetchall()
    return rows, total, page, pages


def get_student_or_404(sv_id):
    sv = get_db().execute(SELECT_COLS + FROM_CLAUSE + " WHERE sv.id = ?", (sv_id,)).fetchone()
    if sv is None:
        abort(404)
    return sv


def form_context(db):
    lop_list = db.execute(
        """SELECT l.id, l.ma_lop, l.ten_lop, l.khoa_hoc, n.ten_nganh
           FROM Lop l JOIN NganhHoc n ON n.id = l.nganh_id ORDER BY l.ma_lop""").fetchall()
    return {"lop_list": lop_list, "gioi_tinh_list": GIOI_TINH, "trang_thai_list": TRANG_THAI}


# ---------------------------------------------------------------- kiểm tra form
def clean_form(form):
    return {
        "ma_sv": form.get("ma_sv", "").strip().upper(),
        "ho_ten": " ".join(form.get("ho_ten", "").split()),
        "ngay_sinh": form.get("ngay_sinh", "").strip(),
        "gioi_tinh": form.get("gioi_tinh", "").strip(),
        "email": form.get("email", "").strip().lower(),
        "so_dien_thoai": form.get("so_dien_thoai", "").strip(),
        "dia_chi": form.get("dia_chi", "").strip(),
        "lop_id": form.get("lop_id", "").strip(),
        "trang_thai": form.get("trang_thai", "").strip() or "Đang học",
    }


def validate(db, d, sv_id=None):
    errors = {}

    if not re.fullmatch(r"[A-Z0-9]{4,15}", d["ma_sv"]):
        errors["ma_sv"] = "Mã sinh viên gồm 4–15 ký tự chữ hoặc số, không dấu."
    else:
        dup = db.execute("SELECT id FROM SinhVien WHERE ma_sv = ? AND id IS NOT ?",
                         (d["ma_sv"], sv_id)).fetchone()
        account = db.execute("SELECT sinh_vien_id FROM TaiKhoan WHERE username = ?",
                             (d["ma_sv"],)).fetchone()
        if dup:
            errors["ma_sv"] = "Mã sinh viên đã tồn tại."
        elif account and (sv_id is None or account["sinh_vien_id"] != sv_id):
            errors["ma_sv"] = "Mã này trùng với một tên đăng nhập đã có."

    if not 2 <= len(d["ho_ten"]) <= 100:
        errors["ho_ten"] = "Họ tên phải từ 2 đến 100 ký tự."

    if d["ngay_sinh"]:
        try:
            birth = datetime.strptime(d["ngay_sinh"], "%Y-%m-%d").date()
            if birth > date.today() or birth.year < 1950:
                errors["ngay_sinh"] = "Ngày sinh không hợp lệ."
        except ValueError:
            errors["ngay_sinh"] = "Ngày sinh không đúng định dạng."

    if d["gioi_tinh"] and d["gioi_tinh"] not in GIOI_TINH:
        errors["gioi_tinh"] = "Giới tính không hợp lệ."

    if d["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d["email"]):
        errors["email"] = "Email không hợp lệ."

    if d["so_dien_thoai"] and not re.fullmatch(r"(0|\+84)\d{9}", d["so_dien_thoai"]):
        errors["so_dien_thoai"] = "Số điện thoại gồm 10 số (bắt đầu bằng 0) hoặc +84 và 9 số."

    if len(d["dia_chi"]) > 255:
        errors["dia_chi"] = "Địa chỉ tối đa 255 ký tự."

    if not _is_int(d["lop_id"]) or not db.execute(
            "SELECT 1 FROM Lop WHERE id = ?", (int(d["lop_id"]),)).fetchone():
        errors["lop_id"] = "Vui lòng chọn lớp."

    if d["trang_thai"] not in TRANG_THAI:
        errors["trang_thai"] = "Trạng thái không hợp lệ."

    return errors


def to_row(d):
    return (d["ma_sv"], d["ho_ten"], d["ngay_sinh"] or None, d["gioi_tinh"] or None,
            d["email"] or None, d["so_dien_thoai"] or None, d["dia_chi"] or None,
            int(d["lop_id"]), d["trang_thai"])


# ---------------------------------------------------------------- trang web
@students_bp.route("/")
@roles_required("admin", "support_staff")
def list_students():
    db = get_db()
    students, total, page, pages = query_students(request.args)
    return render_template(
        "students/list.html", students=students, total=total, page=page, pages=pages,
        f=request.args,
        nganh_list=db.execute("SELECT id, ma_nganh, ten_nganh FROM NganhHoc ORDER BY ma_nganh").fetchall(),
        lop_list=db.execute("SELECT id, ma_lop FROM Lop ORDER BY ma_lop").fetchall(),
        khoa_list=db.execute("SELECT DISTINCT khoa_hoc FROM Lop ORDER BY khoa_hoc").fetchall(),
        trang_thai_list=TRANG_THAI)


@students_bp.route("/me")
@login_required
def my_profile():
    if g.user["sinh_vien_id"] is None:
        flash("Tài khoản này không gắn với hồ sơ sinh viên nào.", "warning")
        return redirect(url_for("students.list_students")
                        if g.user["vai_tro"] != "student" else url_for("auth.login"))
    return redirect(url_for("students.detail", sv_id=g.user["sinh_vien_id"]))


@students_bp.route("/<int:sv_id>")
@login_required
def detail(sv_id):
    sv = get_student_or_404(sv_id)
    if g.user["vai_tro"] == "student" and g.user["sinh_vien_id"] != sv_id:
        abort(403)
    return render_template("students/detail.html", sv=sv)


@students_bp.route("/new", methods=["GET", "POST"])
@roles_required("admin")
def create():
    db = get_db()
    errors = {}
    data = {"trang_thai": "Đang học"}

    if request.method == "POST":
        data = clean_form(request.form)
        errors = validate(db, data)
        if not errors:
            try:
                cur = db.execute(
                    """INSERT INTO SinhVien(ma_sv, ho_ten, ngay_sinh, gioi_tinh, email,
                                            so_dien_thoai, dia_chi, lop_id, trang_thai)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", to_row(data))
                db.execute(
                    "INSERT INTO TaiKhoan(username, password_hash, vai_tro, ho_ten, sinh_vien_id) "
                    "VALUES (?, ?, 'student', ?, ?)",
                    (data["ma_sv"], generate_password_hash(DEFAULT_PASSWORD),
                     data["ho_ten"], cur.lastrowid))
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                errors["ma_sv"] = "Không thể lưu vì dữ liệu bị trùng."
            else:
                flash(f"Đã thêm sinh viên {data['ho_ten']}. Tài khoản đăng nhập: "
                      f"{data['ma_sv']} / mật khẩu mặc định {DEFAULT_PASSWORD}.", "success")
                return redirect(url_for("students.detail", sv_id=cur.lastrowid))

    return render_template("students/form.html", mode="create", data=data,
                           errors=errors, sv_id=None, **form_context(db))


@students_bp.route("/<int:sv_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit(sv_id):
    db = get_db()
    sv = get_student_or_404(sv_id)
    errors = {}
    data = {k: ("" if v is None else v) for k, v in dict(sv).items()}

    if request.method == "POST":
        data = clean_form(request.form)
        errors = validate(db, data, sv_id)
        if not errors:
            try:
                db.execute(
                    """UPDATE SinhVien SET ma_sv = ?, ho_ten = ?, ngay_sinh = ?, gioi_tinh = ?,
                              email = ?, so_dien_thoai = ?, dia_chi = ?, lop_id = ?, trang_thai = ?
                       WHERE id = ?""", (*to_row(data), sv_id))
                db.execute("UPDATE TaiKhoan SET username = ?, ho_ten = ? WHERE sinh_vien_id = ?",
                           (data["ma_sv"], data["ho_ten"], sv_id))
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                errors["ma_sv"] = "Không thể lưu vì dữ liệu bị trùng."
            else:
                flash("Đã cập nhật hồ sơ sinh viên.", "success")
                return redirect(url_for("students.detail", sv_id=sv_id))

    return render_template("students/form.html", mode="edit", data=data,
                           errors=errors, sv_id=sv_id, **form_context(db))


@students_bp.route("/<int:sv_id>/delete", methods=["POST"])
@roles_required("admin")
def delete(sv_id):
    db = get_db()
    sv = get_student_or_404(sv_id)
    try:
        db.execute("DELETE FROM SinhVien WHERE id = ?", (sv_id,))  # tài khoản xóa theo (CASCADE)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Không thể xóa vì sinh viên còn dữ liệu liên quan (ví dụ yêu cầu hỗ trợ). "
              "Hãy đổi trạng thái sang “Thôi học” thay vì xóa.", "danger")
        return redirect(url_for("students.detail", sv_id=sv_id))
    flash(f"Đã xóa sinh viên {sv['ho_ten']} ({sv['ma_sv']}).", "success")
    return redirect(url_for("students.list_students"))


# ---------------------------------------------------------------- API JSON
@api_bp.route("")
@roles_required("admin", "support_staff")
def api_list():
    try:
        per_page = min(max(int(request.args.get("per_page", PER_PAGE)), 1), 100)
    except ValueError:
        per_page = PER_PAGE
    rows, total, page, pages = query_students(request.args, per_page)
    return jsonify(items=[dict(r) for r in rows], total=total, page=page,
                   pages=pages, per_page=per_page)


@api_bp.route("/<int:sv_id>")
@login_required
def api_detail(sv_id):
    sv = get_student_or_404(sv_id)
    if g.user["vai_tro"] == "student" and g.user["sinh_vien_id"] != sv_id:
        abort(403)
    return jsonify(dict(sv))
