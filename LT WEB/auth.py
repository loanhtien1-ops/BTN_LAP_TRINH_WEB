"""
Module Quản lý Xác thực và Phân quyền (Authentication & Authorization):
- Hỗ trợ đăng nhập (Login) cho 3 nhóm vai trò: Admin, Nhân viên hỗ trợ, Sinh viên.
- Hỗ trợ đăng xuất (Logout) xóa sạch session.
- Các decorator bảo vệ route: @login_required, @roles_required
"""
import functools
from flask import (Blueprint, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash
from models import get_db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.before_app_request
def load_logged_in_user():
    """Tự động nạp thông tin tài khoản đang đăng nhập vào biến toàn cục g.user"""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute(
            "SELECT id, username, vai_tro, ho_ten, sinh_vien_id FROM TaiKhoan WHERE id = ?",
            (user_id,)
        ).fetchone()

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Xử lý đăng nhập tài khoản"""
    if g.user:
        # Nếu đã đăng nhập thì chuyển hướng theo vai trò
        if g.user["vai_tro"] == "student":
            return redirect(url_for("portal.profile"))
        return redirect(url_for("students.list_students"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        db = get_db()
        error = None

        user = db.execute(
            "SELECT * FROM TaiKhoan WHERE username = ?", (username,)
        ).fetchone()

        if user is None:
            error = "Tên đăng nhập không tồn tại trong hệ thống."
        elif not check_password_hash(user["password_hash"], password):
            error = "Mật khẩu không chính xác. Vui lòng thử lại."

        if error is None:
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Đăng nhập thành công! Chào mừng {user['ho_ten']}.", "success")

            # Chuyển hướng theo vai trò
            if user["vai_tro"] == "student":
                return redirect(url_for("portal.profile"))
            return redirect(url_for("students.list_students"))

        flash(error, "danger")

    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    """Xử lý đăng xuất, làm sạch session"""
    session.clear()
    flash("Bạn đã đăng xuất khỏi hệ thống thành công.", "info")
    return redirect(url_for("auth.login"))

def login_required(view):
    """Decorator yêu cầu đăng nhập trước khi truy cập"""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Vui lòng đăng nhập để truy cập chức năng này.", "warning")
            return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped_view

def roles_required(*roles):
    """Decorator kiểm tra phân quyền vai trò (admin, support_staff, student)"""
    def decorator(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                flash("Vui lòng đăng nhập để tiếp tục.", "warning")
                return redirect(url_for("auth.login"))
            if g.user["vai_tro"] not in roles:
                flash("Bạn không có quyền truy cập vào chức năng hoặc trang này.", "danger")
                if g.user["vai_tro"] == "student":
                    return redirect(url_for("portal.profile"))
                return redirect(url_for("students.list_students"))
            return view(**kwargs)
        return wrapped_view
    return decorator
