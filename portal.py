"""
Module Cổng sinh viên & Hỗ trợ người học (Phiên bản V4 hoàn thiện):
1. Hồ sơ sinh viên, Cập nhật thông tin liên hệ, In sơ yếu lý lịch chuẩn A4
2. Đổi mật khẩu cá nhân
3. Chương trình đào tạo & Điểm tích lũy
4. Tài chính sinh viên (Học phí, Công nợ)
5. Hỗ trợ người học: Gửi yêu cầu, Cán bộ phản hồi, Cập nhật trạng thái thời gian thực (Real-time polling)
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
    """Sinh viên tự cập nhật số điện thoại, email cá nhân và địa chỉ thường trú"""
    db = get_db()
    sv = get_current_student(db)
    if not sv:
        abort(404)

    email = request.form.get("email", "").strip().lower()
    so_dien_thoai = request.form.get("so_dien_thoai", "").strip()
    dia_chi = request.form.get("dia_chi", "").strip()

    db.execute("""
        UPDATE SinhVien
        SET email = ?, so_dien_thoai = ?, dia_chi = ?
        WHERE id = ?
    """, (email or None, so_dien_thoai or None, dia_chi or None, sv["id"]))
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

# ----------------- 5. HỆ THỐNG HỖ TRỢ & CẬP NHẬT REAL-TIME -----------------
@portal_bp.route("/support", methods=["GET", "POST"])
@login_required
def support():
    db = get_db()
    sv = get_current_student(db)

    # Sinh viên gửi yêu cầu mới
    if request.method == "POST" and g.user["vai_tro"] == "student":
        chu_de = request.form.get("chu_de", "").strip()
        danh_muc = request.form.get("danh_muc", "").strip()
        noi_dung = request.form.get("noi_dung", "").strip()

        if not chu_de or not noi_dung:
            flash("Vui lòng nhập đầy đủ tiêu đề và nội dung cần hỗ trợ.", "danger")
        else:
            db.execute("""
                INSERT INTO YeuCauHoTro (sinh_vien_id, chu_de, danh_muc, noi_dung)
                VALUES (?, ?, ?, ?)
            """, (sv["id"], chu_de, danh_muc, noi_dung))
            db.commit()
            flash("Gửi yêu cầu hỗ trợ thành công! Ban tư vấn sẽ sớm phản hồi.", "success")
            return redirect(url_for("portal.support"))

    # Lấy danh sách yêu cầu
    if g.user["vai_tro"] == "student":
        if not sv:
            abort(403)
        requests_list = db.execute("""
            SELECT y.*, tk.ho_ten AS ten_nguoi_phan_hoi
            FROM YeuCauHoTro y
            LEFT JOIN TaiKhoan tk ON tk.id = y.nguoi_phan_hoi_id
            WHERE y.sinh_vien_id = ?
            ORDER BY y.id DESC
        """, (sv["id"],)).fetchall()
    else:
        # Cán bộ hoặc Admin xem toàn bộ yêu cầu
        requests_list = db.execute("""
            SELECT y.*, sv.ma_sv, sv.ho_ten AS ho_ten_sv, l.ma_lop, tk.ho_ten AS ten_nguoi_phan_hoi
            FROM YeuCauHoTro y
            JOIN SinhVien sv ON sv.id = y.sinh_vien_id
            JOIN Lop l ON l.id = sv.lop_id
            LEFT JOIN TaiKhoan tk ON tk.id = y.nguoi_phan_hoi_id
            ORDER BY CASE y.trang_thai WHEN 'Chờ xử lý' THEN 1 WHEN 'Đang xử lý' THEN 2 ELSE 3 END, y.id DESC
        """).fetchall()

    return render_template(
        "portal/support.html",
        sv=sv,
        requests_list=requests_list,
        categories=['Học vụ & Đào tạo', 'Tài chính & Học phí', 'Ký túc xá & Đời sống', 'Kỹ thuật & Hệ thống', 'Khác']
    )

@portal_bp.route("/support/<int:ticket_id>/reply", methods=["POST"])
@roles_required("admin", "support_staff")
def reply_support(ticket_id):
    """Nhân viên gửi phản hồi -> Tự động cập nhật trạng thái sang 'Đã giải quyết'"""
    db = get_db()
    phan_hoi = request.form.get("phan_hoi", "").strip()

    if not phan_hoi:
        flash("Nội dung phản hồi không được để trống.", "danger")
    else:
        db.execute("""
            UPDATE YeuCauHoTro
            SET phan_hoi = ?, trang_thai = 'Đã giải quyết', nguoi_phan_hoi_id = ?, ngay_phan_hoi = datetime('now', 'localtime')
            WHERE id = ?
        """, (phan_hoi, g.user["id"], ticket_id))
        db.commit()
        flash("Đã gửi phản hồi thành công và tự động đánh dấu yêu cầu là 'Đã giải quyết'.", "success")

    return redirect(url_for("portal.support"))

# ----------------- API REAL-TIME CHO TRANG SINH VIÊN -----------------
@portal_bp.route("/api/ticket-status")
@login_required
def api_ticket_status():
    """API trả về JSON trạng thái các yêu cầu để trình duyệt sinh viên tự động cập nhật thời gian thực"""
    db = get_db()
    if g.user["vai_tro"] == "student":
        sv = get_current_student(db)
        if not sv:
            return jsonify([])
        rows = db.execute("""
            SELECT y.id, y.trang_thai, y.phan_hoi, y.ngay_phan_hoi, tk.ho_ten AS ten_nguoi_phan_hoi
            FROM YeuCauHoTro y
            LEFT JOIN TaiKhoan tk ON tk.id = y.nguoi_phan_hoi_id
            WHERE y.sinh_vien_id = ?
        """, (sv["id"],)).fetchall()
    else:
        rows = db.execute("""
            SELECT y.id, y.trang_thai, y.phan_hoi, y.ngay_phan_hoi, tk.ho_ten AS ten_nguoi_phan_hoi
            FROM YeuCauHoTro y
            LEFT JOIN TaiKhoan tk ON tk.id = y.nguoi_phan_hoi_id
        """).fetchall()

    return jsonify([dict(r) for r in rows])
