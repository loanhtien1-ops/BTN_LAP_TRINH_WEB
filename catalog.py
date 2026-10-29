"""M03 - Quản lý danh mục: ngành học và lớp (kèm khóa học)."""
import re
import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from auth import roles_required
from models import get_db

catalog_bp = Blueprint("catalog", __name__, url_prefix="/catalog")


def _clean(text):
    return " ".join(text.split())


# ---------------------------------------------------------------- ngành học
@catalog_bp.route("/nganh")
@roles_required("admin")
def nganh_list():
    rows = get_db().execute(
        """SELECT n.*,
                  (SELECT COUNT(*) FROM Lop l WHERE l.nganh_id = n.id) AS so_lop,
                  (SELECT COUNT(*) FROM SinhVien sv JOIN Lop l ON l.id = sv.lop_id
                    WHERE l.nganh_id = n.id) AS so_sv
           FROM NganhHoc n ORDER BY n.ma_nganh""").fetchall()
    return render_template("catalog/nganh.html", nganh_list=rows)


@catalog_bp.route("/nganh/save", methods=["POST"])
@roles_required("admin")
def nganh_save():
    db = get_db()
    row_id = request.form.get("id", "").strip()
    ma = request.form.get("ma_nganh", "").strip().upper()
    ten = _clean(request.form.get("ten_nganh", ""))

    if not re.fullmatch(r"[A-Z0-9_-]{2,15}", ma):
        flash("Mã ngành gồm 2–15 ký tự chữ, số, gạch ngang hoặc gạch dưới.", "danger")
    elif not 2 <= len(ten) <= 100:
        flash("Tên ngành phải từ 2 đến 100 ký tự.", "danger")
    else:
        try:
            if row_id.isascii() and row_id.isdigit():
                cur = db.execute("UPDATE NganhHoc SET ma_nganh = ?, ten_nganh = ? WHERE id = ?",
                                 (ma, ten, int(row_id)))
                if cur.rowcount == 0:
                    db.rollback()
                    abort(404)
            else:
                db.execute("INSERT INTO NganhHoc(ma_nganh, ten_nganh) VALUES (?, ?)", (ma, ten))
            db.commit()
            flash("Đã lưu ngành học.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Mã ngành đã tồn tại.", "danger")
    return redirect(url_for("catalog.nganh_list"))


@catalog_bp.route("/nganh/<int:nganh_id>/delete", methods=["POST"])
@roles_required("admin")
def nganh_delete(nganh_id):
    db = get_db()
    try:
        cur = db.execute("DELETE FROM NganhHoc WHERE id = ?", (nganh_id,))
        db.commit()
        if cur.rowcount == 0:
            abort(404)
        flash("Đã xóa ngành học.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Không thể xóa: ngành này vẫn còn lớp. Hãy chuyển hoặc xóa các lớp trước.", "danger")
    return redirect(url_for("catalog.nganh_list"))


# ---------------------------------------------------------------- lớp / khóa
@catalog_bp.route("/lop")
@roles_required("admin")
def lop_list():
    db = get_db()
    rows = db.execute(
        """SELECT l.*, n.ma_nganh, n.ten_nganh,
                  (SELECT COUNT(*) FROM SinhVien sv WHERE sv.lop_id = l.id) AS so_sv
           FROM Lop l JOIN NganhHoc n ON n.id = l.nganh_id
           ORDER BY l.ma_lop""").fetchall()
    nganh = db.execute("SELECT id, ma_nganh, ten_nganh FROM NganhHoc ORDER BY ma_nganh").fetchall()
    return render_template("catalog/lop.html", lop_list=rows, nganh_list=nganh)


@catalog_bp.route("/lop/save", methods=["POST"])
@roles_required("admin")
def lop_save():
    db = get_db()
    row_id = request.form.get("id", "").strip()
    ma = request.form.get("ma_lop", "").strip().upper()
    ten = _clean(request.form.get("ten_lop", ""))
    khoa = request.form.get("khoa_hoc", "").strip().upper()
    nganh_id = request.form.get("nganh_id", "").strip()

    if not re.fullmatch(r"[A-Z0-9_-]{2,20}", ma):
        flash("Mã lớp gồm 2–20 ký tự chữ, số, gạch ngang hoặc gạch dưới.", "danger")
    elif not 2 <= len(ten) <= 100:
        flash("Tên lớp phải từ 2 đến 100 ký tự.", "danger")
    elif not re.fullmatch(r"[A-Z0-9 _-]{1,20}", khoa):
        flash("Khóa học không hợp lệ (ví dụ K66).", "danger")
    elif not (nganh_id.isascii() and nganh_id.isdigit()) or not db.execute(
            "SELECT 1 FROM NganhHoc WHERE id = ?", (int(nganh_id),)).fetchone():
        flash("Vui lòng chọn ngành học.", "danger")
    else:
        try:
            if row_id.isascii() and row_id.isdigit():
                cur = db.execute(
                    "UPDATE Lop SET ma_lop = ?, ten_lop = ?, nganh_id = ?, khoa_hoc = ? WHERE id = ?",
                    (ma, ten, int(nganh_id), khoa, int(row_id)))
                if cur.rowcount == 0:
                    db.rollback()
                    abort(404)
            else:
                db.execute("INSERT INTO Lop(ma_lop, ten_lop, nganh_id, khoa_hoc) VALUES (?, ?, ?, ?)",
                           (ma, ten, int(nganh_id), khoa))
            db.commit()
            flash("Đã lưu lớp.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Mã lớp đã tồn tại.", "danger")
    return redirect(url_for("catalog.lop_list"))


@catalog_bp.route("/lop/<int:lop_id>/delete", methods=["POST"])
@roles_required("admin")
def lop_delete(lop_id):
    db = get_db()
    try:
        cur = db.execute("DELETE FROM Lop WHERE id = ?", (lop_id,))
        db.commit()
        if cur.rowcount == 0:
            abort(404)
        flash("Đã xóa lớp.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Không thể xóa: lớp này vẫn còn sinh viên.", "danger")
    return redirect(url_for("catalog.lop_list"))
