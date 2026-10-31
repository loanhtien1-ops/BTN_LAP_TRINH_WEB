import os
from datetime import datetime
from markupsafe import Markup, escape
from flask import Flask, g, jsonify, redirect, render_template, request, url_for

from auth import auth_bp, login_required
from catalog import catalog_bp
from models import close_db, get_db, init_db
from seed import seed
from seed_portal import seed_portal_data
from seed_support import seed_support_data
from students import api_bp, students_bp
from portal import portal_bp
from support import support_bp

ERROR_MESSAGES = {
    403: "Bạn không có quyền truy cập trang này.",
    404: "Không tìm thấy trang hoặc dữ liệu yêu cầu.",
}

def dmy(value):
    """2004-05-17 -> 17/05/2004"""
    if not value:
        return "—"
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value

def nl2br(value):
    """Chuyển newline sang thẻ <br> an toàn trong Jinja2"""
    if not value:
        return ""
    result = "<br>\n".join(str(escape(value)).splitlines())
    return Markup(result)

def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "doi-khoa-bi-mat-khi-nop-bai"),
        DATABASE=os.path.join(app.instance_path, "student_support.db"),
    )
    if config:
        app.config.update(config)
    os.makedirs(app.instance_path, exist_ok=True)

    app.teardown_appcontext(close_db)
    app.jinja_env.filters["dmy"] = dmy
    app.jinja_env.filters["nl2br"] = nl2br

    @app.context_processor
    def inject_context():
        return dict(
            current_user=getattr(g, 'user', None),
            csrf_token=lambda: ""
        )

    # Đăng ký các Blueprint
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)   # M03 - Quản lý sinh viên
    app.register_blueprint(api_bp)        # M03 - API JSON
    app.register_blueprint(catalog_bp)    # M03 - Ngành, lớp
    app.register_blueprint(portal_bp)     # Cổng sinh viên
    app.register_blueprint(support_bp)    # M12 - Hỗ trợ người học

    @app.route("/")
    @login_required
    def home():
        if g.user["vai_tro"] == "student":
            return redirect(url_for("portal.profile"))
        return redirect(url_for("students.list_students"))

    def handle_error(error):
        code = getattr(error, "code", 500)
        message = ERROR_MESSAGES.get(code) or getattr(error, "description", "Đã xảy ra lỗi.")
        if request.path.startswith("/api/"):
            return jsonify(error=message), code
        return render_template("error.html", code=code, message=message), code

    for code in (400, 403, 404):
        app.register_error_handler(code, handle_error)

    with app.app_context():
        db = get_db()
        init_db(db)
        if db.execute("SELECT COUNT(*) FROM TaiKhoan").fetchone()[0] == 0:
            seed(db)
            seed_portal_data(db)
            seed_support_data(db)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
