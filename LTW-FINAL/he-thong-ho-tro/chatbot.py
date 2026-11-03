"""Chatbot FAQ: sinh viên hỏi, hệ thống tìm trong kho FAQ đã duyệt; không có thì chuyển nhân viên.

- Sinh viên (đã đăng nhập) hỏi chatbot tại /chatbot/ và xem FAQ tại /chatbot/faq.
- Nhân viên tạo/sửa FAQ (chờ duyệt); chỉ admin duyệt, ẩn, xóa. Admin tạo FAQ thì được duyệt luôn.
- Nhật ký hỏi đáp (ChatLog) đã che email/số điện thoại và tự xóa sau 30 ngày; không hiện tên người hỏi.
"""
import re
from datetime import datetime

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from auth import login_required, roles_required
from models import get_db, normalize

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

STAFF = ("support_staff", "admin")

# FAQ mẫu nạp ở lần chạy đầu tiên khi bảng FAQ còn trống: (câu hỏi, trả lời, từ khóa, cần chuyển nhân viên)
FAQ_MAU = [
    ("Tôi quên mật khẩu cổng sinh viên thì làm thế nào?",
     "Nếu còn đăng nhập được, vào mục Đổi mật khẩu để tự đổi. Nếu không đăng nhập được, hãy chọn Vẫn cần hỗ trợ "
     "(loại Tài khoản) để nhân viên đặt lại mật khẩu cho bạn.",
     "quên mật khẩu, mất mật khẩu, đổi mật khẩu, không đăng nhập được", 0),
    ("Xin gia hạn nộp học phí cần làm gì?",
     "Bạn gửi yêu cầu hỗ trợ loại Học phí, nêu rõ học kỳ cần gia hạn và lý do. Nhân viên sẽ phản hồi trong vòng 24 giờ.",
     "gia hạn học phí, nộp học phí, hạn nộp, công nợ", 0),
    ("Làm sao để xin xác nhận bảng điểm?",
     "Gửi yêu cầu hỗ trợ loại Học vụ, ghi rõ mục đích sử dụng và số bản cần. Bạn sẽ được thông báo ngày nhận trong phần phản hồi.",
     "xác nhận bảng điểm, bảng điểm, giấy xác nhận", 0),
    ("Trang web bị lỗi hiển thị hoặc không tải được thì sao?",
     "Hãy thử tải lại trang hoặc dùng trình duyệt khác. Nếu vẫn lỗi, gửi yêu cầu loại Kỹ thuật kèm tên trang và thiết bị bạn đang dùng.",
     "lỗi trang web, không tải được, lỗi hiển thị", 0),
    ("Em muốn bảo lưu kết quả học tập hoặc xin điểm thi cần kiểm tra lại?",
     "Việc này cần nhân viên kiểm tra hồ sơ của bạn nên chatbot không thể trả lời thay.",
     "bảo lưu, phúc khảo, kiểm tra lại điểm, điểm thi sai", 1),
]


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def seed_faq_neu_rong(db):
    """Nạp vài FAQ mẫu (đã duyệt) nếu bảng FAQ trống, để chatbot dùng được ngay."""
    if db.execute("SELECT COUNT(*) FROM FAQ").fetchone()[0]:
        return
    now = now_str()
    for hoi, tra, tu_khoa, chuyen in FAQ_MAU:
        db.execute("""INSERT INTO FAQ(cau_hoi, cau_tra_loi, tu_khoa, trang_thai, can_chuyen_nhan_vien,
                                      ngay_tao, ngay_cap_nhat) VALUES (?, ?, ?, 'da_duyet', ?, ?, ?)""",
                   (hoi, tra, tu_khoa, chuyen, now, now))
    db.commit()


# Tìm FAQ phù hợp với câu hỏi sinh viên
def tim_faq_phu_hop(db, question):
    q = normalize(question)
    if not q:
        return None

    faqs = db.execute("SELECT * FROM FAQ WHERE trang_thai = 'da_duyet'").fetchall()

    best_faq = None
    best_score = 0

    for faq in faqs:
        cau_hoi = normalize(faq["cau_hoi"])
        score = 0

        # Ưu tiên câu hỏi có nội dung gần giống FAQ (bỏ qua câu quá ngắn để tránh khớp nhầm)
        if cau_hoi and (cau_hoi in q or (len(q) >= 4 and q in cau_hoi)):
            score += 10

        # So khớp các từ khóa
        for keyword in re.split(r"[;,\n]", faq["tu_khoa"]):
            keyword = normalize(keyword.strip())
            if keyword and keyword in q:
                score += 3 + len(keyword.split())

        # Ưu tiên tuyệt đối FAQ bắt buộc chuyển nhân viên
        if faq["can_chuyen_nhan_vien"] and score >= 3:
            return faq

        if score > best_score:
            best_score = score
            best_faq = faq

    # Không đủ độ phù hợp thì không trả lời
    if best_score < 3:
        return None
    return best_faq


# Che một số thông tin cá nhân trước khi ghi nhật ký
def che_thong_tin(text):
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[EMAIL]", text)
    text = re.sub(r"(?<!\d)(?:\+?84|0)\d{8,10}(?!\d)", "[SO_DIEN_THOAI]", text)
    return text[:1000]


# ---------------------------------------------------------------- sinh viên
@chatbot_bp.route("/")
@roles_required("student")
def chat():
    db = get_db()
    goi_y = db.execute(
        "SELECT cau_hoi FROM FAQ WHERE trang_thai = 'da_duyet' AND can_chuyen_nhan_vien = 0 "
        "ORDER BY id LIMIT 5").fetchall()
    return render_template("chatbot/chat.html", goi_y=[r["cau_hoi"] for r in goi_y])


@chatbot_bp.route("/faq")
@login_required
def faq_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    where, params = ["trang_thai = 'da_duyet'", "can_chuyen_nhan_vien = 0"], []
    if q:
        like = "%" + normalize(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(norm(cau_hoi) LIKE ? ESCAPE '\\' OR norm(cau_tra_loi) LIKE ? ESCAPE '\\' "
                     "OR norm(tu_khoa) LIKE ? ESCAPE '\\')")
        params += [like] * 3
    rows = db.execute("SELECT * FROM FAQ WHERE " + " AND ".join(where) + " ORDER BY id DESC LIMIT 200",
                      params).fetchall()
    return render_template("chatbot/faq.html", items=rows, q=q)


# API nhận câu hỏi từ sinh viên
@chatbot_bp.route("/ask", methods=["POST"])
@roles_required("student")
def ask():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()

    if not question:
        return jsonify(answer="Bạn vui lòng nhập câu hỏi nhé.")

    if len(question) > 1000:
        return jsonify(answer="Câu hỏi quá dài. Bạn vui lòng nhập ngắn gọn hơn.")

    db = get_db()

    # Xóa nhật ký đã quá 30 ngày
    db.execute("DELETE FROM ChatLog WHERE ngay_tao < datetime('now', 'localtime', '-30 days')")

    faq = tim_faq_phu_hop(db, question)

    if faq and faq["can_chuyen_nhan_vien"]:
        answer = ("Vấn đề này cần nhân viên hỗ trợ trực tiếp để đảm bảo thông tin được kiểm tra chính xác. "
                  "Bạn có thể chọn Vẫn cần hỗ trợ để gửi yêu cầu đến nhà trường.")
        ket_qua = "chuyen_nhan_vien"
        handoff = True
    elif faq:
        answer = faq["cau_tra_loi"]
        ket_qua = "da_tim_thay"
        handoff = False
    else:
        answer = ("Xin lỗi, mình chưa tìm thấy câu trả lời phù hợp trong kho dữ liệu. Bạn có thể chọn "
                  "Vẫn cần hỗ trợ để được nhân viên nhà trường giải đáp.")
        ket_qua = "khong_tim_thay"
        handoff = True

    db.execute("INSERT INTO ChatLog(tai_khoan_id, cau_hoi, faq_id, ket_qua, ngay_tao) VALUES (?, ?, ?, ?, ?)",
               (g.user["id"], che_thong_tin(question), faq["id"] if faq else None, ket_qua, now_str()))
    db.commit()

    # Nút "Vẫn cần hỗ trợ": mở form gửi yêu cầu, điền sẵn câu hỏi
    ticket_url = url_for("support.new_ticket", tieu_de=question[:80], noi_dung=question)
    return jsonify(answer=answer, handoff=handoff, ticket_url=ticket_url)


# ---------------------------------------------------------------- nhân viên / admin
@chatbot_bp.route("/manage")
@roles_required(*STAFF)
def manage():
    db = get_db()
    faqs = db.execute("""
        SELECT f.*, t.ho_ten AS ten_nguoi_tao, a.ho_ten AS ten_nguoi_duyet
        FROM FAQ f
        LEFT JOIN TaiKhoan t ON t.id = f.nguoi_tao_id
        LEFT JOIN TaiKhoan a ON a.id = f.nguoi_duyet_id
        ORDER BY (f.trang_thai = 'cho_duyet') DESC, f.id DESC
    """).fetchall()
    # Những câu sinh viên hỏi mà chatbot chưa trả lời được (đã che email/SĐT, không có tên người hỏi)
    chua_tra_loi = db.execute("""
        SELECT cau_hoi, COUNT(*) AS so_lan FROM ChatLog WHERE ket_qua = 'khong_tim_thay'
        GROUP BY cau_hoi ORDER BY so_lan DESC, MAX(id) DESC LIMIT 10
    """).fetchall()
    prefill = {"cau_hoi": request.args.get("cau_hoi", "").strip()[:300], "tu_khoa": request.args.get("tu_khoa", "").strip()[:300]}
    return render_template("chatbot/manage.html", faqs=faqs, chua_tra_loi=chua_tra_loi, prefill=prefill)


def _doc_form():
    return (request.form.get("cau_hoi", "").strip(), request.form.get("cau_tra_loi", "").strip(),
            request.form.get("tu_khoa", "").strip(), 1 if request.form.get("can_chuyen_nhan_vien") else 0)


def _hop_le(cau_hoi, cau_tra_loi, tu_khoa):
    if not cau_hoi or not cau_tra_loi or not tu_khoa:
        return "Vui lòng nhập đầy đủ thông tin FAQ."
    if len(cau_hoi) > 300 or len(tu_khoa) > 300 or len(cau_tra_loi) > 5000:
        return "Nội dung FAQ quá dài."
    return None


# Nhân viên tạo FAQ mới (admin tạo thì được duyệt luôn)
@chatbot_bp.route("/create", methods=["POST"])
@roles_required(*STAFF)
def create():
    cau_hoi, cau_tra_loi, tu_khoa, chuyen = _doc_form()
    loi = _hop_le(cau_hoi, cau_tra_loi, tu_khoa)
    if loi:
        flash(loi, "danger")
        return redirect(url_for("chatbot.manage"))

    la_admin = g.user["vai_tro"] == "admin"
    now = now_str()
    db = get_db()
    db.execute("""
        INSERT INTO FAQ(cau_hoi, cau_tra_loi, tu_khoa, trang_thai, can_chuyen_nhan_vien,
                        nguoi_tao_id, nguoi_duyet_id, ngay_tao, ngay_cap_nhat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cau_hoi, cau_tra_loi, tu_khoa, "da_duyet" if la_admin else "cho_duyet", chuyen,
          g.user["id"], g.user["id"] if la_admin else None, now, now))
    db.commit()
    flash("Đã thêm FAQ. Chatbot có thể dùng ngay." if la_admin else "Đã gửi FAQ để admin duyệt.", "success")
    return redirect(url_for("chatbot.manage"))


# Sửa FAQ (nhân viên sửa thì FAQ quay về chờ duyệt)
@chatbot_bp.route("/update/<int:faq_id>", methods=["POST"])
@roles_required(*STAFF)
def update(faq_id):
    cau_hoi, cau_tra_loi, tu_khoa, chuyen = _doc_form()
    loi = _hop_le(cau_hoi, cau_tra_loi, tu_khoa)
    if loi:
        flash(loi, "danger")
        return redirect(url_for("chatbot.manage"))
    db = get_db()
    la_admin = g.user["vai_tro"] == "admin"
    if not db.execute("SELECT 1 FROM FAQ WHERE id = ?", (faq_id,)).fetchone():
        abort(404)
    if la_admin:
        db.execute("UPDATE FAQ SET cau_hoi=?, cau_tra_loi=?, tu_khoa=?, can_chuyen_nhan_vien=?, ngay_cap_nhat=? WHERE id=?",
                   (cau_hoi, cau_tra_loi, tu_khoa, chuyen, now_str(), faq_id))
    else:
        db.execute("""UPDATE FAQ SET cau_hoi=?, cau_tra_loi=?, tu_khoa=?, can_chuyen_nhan_vien=?, ngay_cap_nhat=?,
                      trang_thai='cho_duyet', nguoi_duyet_id=NULL WHERE id=?""",
                   (cau_hoi, cau_tra_loi, tu_khoa, chuyen, now_str(), faq_id))
    db.commit()
    flash("Đã cập nhật FAQ." if la_admin else "Đã cập nhật FAQ và gửi lại để admin duyệt.", "success")
    return redirect(url_for("chatbot.manage"))


# Chỉ admin được duyệt FAQ
@chatbot_bp.route("/approve/<int:faq_id>", methods=["POST"])
@roles_required("admin")
def approve(faq_id):
    db = get_db()
    cur = db.execute("UPDATE FAQ SET trang_thai = 'da_duyet', nguoi_duyet_id = ?, ngay_cap_nhat = ? WHERE id = ?",
                     (g.user["id"], now_str(), faq_id))
    if cur.rowcount == 0:
        db.rollback()
        abort(404)
    db.commit()
    flash("Đã duyệt FAQ. Chatbot có thể sử dụng câu trả lời này.", "success")
    return redirect(url_for("chatbot.manage"))


# Admin ẩn FAQ (đưa về chờ duyệt, chatbot không dùng nữa)
@chatbot_bp.route("/unapprove/<int:faq_id>", methods=["POST"])
@roles_required("admin")
def unapprove(faq_id):
    db = get_db()
    cur = db.execute("UPDATE FAQ SET trang_thai = 'cho_duyet', nguoi_duyet_id = NULL, ngay_cap_nhat = ? WHERE id = ?",
                     (now_str(), faq_id))
    if cur.rowcount == 0:
        db.rollback()
        abort(404)
    db.commit()
    flash("Đã ẩn FAQ khỏi chatbot.", "success")
    return redirect(url_for("chatbot.manage"))


@chatbot_bp.route("/delete/<int:faq_id>", methods=["POST"])
@roles_required("admin")
def delete(faq_id):
    db = get_db()
    db.execute("UPDATE ChatLog SET faq_id = NULL WHERE faq_id = ?", (faq_id,))  # nhật ký tham chiếu FAQ
    cur = db.execute("DELETE FROM FAQ WHERE id = ?", (faq_id,))
    if cur.rowcount == 0:
        db.rollback()
        abort(404)
    db.commit()
    flash("Đã xóa FAQ.", "success")
    return redirect(url_for("chatbot.manage"))
