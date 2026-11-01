"""
Module Cổng sinh viên & Hỗ trợ người học (Phiên bản V4 hoàn thiện):
1. Hồ sơ sinh viên, Cập nhật thông tin liên hệ, In sơ yếu lý lịch chuẩn A4
2. Đổi mật khẩu cá nhân
3. Chương trình đào tạo & Điểm tích lũy
4. Tài chính sinh viên (Học phí, Công nợ)
5. Hỗ trợ người học (M12) đã chuyển sang support.py; /portal/support chỉ còn chuyển hướng
"""
from datetime import datetime
from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from auth import login_required, roles_required
from models import get_db

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")

def get_current_student(db):
    """Lấy bản ghi sinh viên gắn với tài khoản đang đăng nhập."""
    if not g.user or g.user["sinh_vien_id"] is None:
        return None
    query = """
        SELECT sv.*, l.ma_lop, l.ten_lop, l.khoa_hoc,
               n.id AS nganh_id, n.ma_nganh, n.ten_nganh
        FROM SinhVien sv
        JOIN Lop l ON l.id = sv.lop_id
        JOIN NganhHoc n ON n.id = l.nganh_id
        WHERE sv.id = ?
    """
    return db.execute(query, (g.user["sinh_vien_id"],)).fetchone()

# ----------------- 1. HỒ SƠ SINH VIÊN & CẬP NHẬT THÔNG TIN LIÊN HỆ -----------------
@portal_bp.route("/profile")
@login_required
@roles_required("student")
def profile():
    db = get_db()
    sv = get_current_student(db)
    if not sv:
        flash("Không tìm thấy thông tin sinh viên liên kết với tài khoản này.", "warning")
        return redirect(url_for("auth.login"))
    return render_template("portal/profile.html", sv=sv)


@portal_bp.route("/profile/edit", methods=["POST"])
@login_required
@roles_required("student")
def update_contact():
    """Sinh viên tự cập nhật số điện thoại và địa chỉ. Email trường cấp bị khóa (chỉ admin sửa)."""
    db = get_db()
    sv = get_current_student(db)
    if not sv:
        abort(404)

    so_dien_thoai = request.form.get("so_dien_thoai", "").strip()
    dia_chi = request.form.get("dia_chi", "").strip()

    db.execute("""
        UPDATE SinhVien
        SET so_dien_thoai = ?, dia_chi = ?
        WHERE id = ?
    """, (so_dien_thoai or None, dia_chi or None, sv["id"]))
    db.commit()

    flash("Cập nhật thông tin liên hệ thành công!", "success")
    return redirect(url_for("portal.profile"))

@portal_bp.route("/profile/print")
@login_required
@roles_required("student")
def print_profile():
    """Trang xem và in Sơ yếu lý lịch sinh viên định dạng chuẩn A4 có đóng dấu & QR xác thực"""
    db = get_db()
    sv = get_current_student(db)
    if not sv:
        abort(404)
    return render_template("portal/profile_print.html", sv=sv, now=datetime.now())

# ----------------- 2. ĐỔI MẬT KHẨU CÁ NHÂN -----------------
@portal_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Cho phép sinh viên hoặc cán bộ tự đổi mật khẩu cá nhân"""
    if request.method == "POST":
        old_password = request.form.get("old_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        db = get_db()

        user = db.execute("SELECT password_hash FROM TaiKhoan WHERE id = ?", (g.user["id"],)).fetchone()

        if not check_password_hash(user["password_hash"], old_password):
            flash("Mật khẩu hiện tại không chính xác.", "danger")
        elif len(new_password) < 6:
            flash("Mật khẩu mới phải có tối thiểu 6 ký tự.", "danger")
        elif new_password != confirm_password:
            flash("Xác nhận mật khẩu mới không trùng khớp.", "danger")
        else:
            db.execute("UPDATE TaiKhoan SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(new_password), g.user["id"]))
            db.commit()
            flash("Đổi mật khẩu thành công! Hãy ghi nhớ mật khẩu mới của bạn.", "success")
            if g.user["vai_tro"] == "student":
                return redirect(url_for("portal.profile"))
            return redirect(url_for("students.list_students"))

    return render_template("portal/change_password.html")

# ----------------- 3. CHƯƠNG TRÌNH ĐÀO TẠO & KẾT QUẢ HỌC TẬP -----------------
@portal_bp.route("/curriculum")
@login_required
@roles_required("student")
def curriculum():
    db = get_db()
    sv = get_current_student(db)
    if not sv:
        abort(404)

    curriculum_sql = """
        SELECT c.*, kq.diem_chuyen_can, kq.diem_thi, kq.diem_tong_ket, kq.diem_chu, kq.trang_thai_hp
        FROM ChuongTrinhDaoTao c
        LEFT JOIN KetQuaHocTap kq ON kq.hoc_phan_id = c.id AND kq.sinh_vien_id = ?
        WHERE c.nganh_id = ?
        ORDER BY c.hoc_ky_goi_y, c.ma_hp
    """
    courses = db.execute(curriculum_sql, (sv["id"], sv["nganh_id"])).fetchall()

    semesters = {}
    total_credits = 0
    accumulated_credits = 0
    for c in courses:
        sem = c["hoc_ky_goi_y"]
        if sem not in semesters:
            semesters[sem] = []
        semesters[sem].append(c)
        total_credits += c["so_tin_chi"]
        if c["trang_thai_hp"] == "Đạt":
            accumulated_credits += c["so_tin_chi"]

    return render_template(
        "portal/curriculum.html",
        sv=sv,
        semesters=semesters,
        total_credits=total_credits,
        accumulated_credits=accumulated_credits
    )

# ----------------- 4. TÀI CHÍNH SINH VIÊN -----------------
@portal_bp.route("/finance")
@login_required
@roles_required("student")
def finance():
    db = get_db()
    sv = get_current_student(db)
    if not sv:
        abort(404)

    finance_records = db.execute("""
        SELECT * FROM TaiChinhSinhVien
        WHERE sinh_vien_id = ?
        ORDER BY id DESC
    """, (sv["id"],)).fetchall()

    tong_phai_nop = sum(r["so_tien_phai_nop"] for r in finance_records)
    tong_da_nop = sum(r["so_tien_da_nop"] for r in finance_records)
    cong_no_con_lai = tong_phai_nop - tong_da_nop

    return render_template(
        "portal/finance.html",
        sv=sv,
        records=finance_records,
        tong_phai_nop=tong_phai_nop,
        tong_da_nop=tong_da_nop,
        cong_no=cong_no_con_lai
    )

# ----------------- 5. HỖ TRỢ NGƯỜI HỌC -> chuyển sang support.py (M12) -----------------
@portal_bp.route("/support")
@login_required
def support():
    """Giữ endpoint cũ để các liên kết còn sót trong template không bị lỗi."""
    return redirect(url_for("support.index"))
