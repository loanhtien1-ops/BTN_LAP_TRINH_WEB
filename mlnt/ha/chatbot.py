
import re
from datetime import datetime

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from auth import roles_required
from models import get_db, normalize

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

STAFF = ("support_staff", "admin")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Tìm FAQ phù hợp với câu hỏi sinh viên
def tim_faq_phu_hop(db, question):
    q = normalize(question)
    if not q:
        return None

    faqs = db.execute(
        "SELECT * FROM FAQ WHERE trang_thai = 'da_duyet'"
    ).fetchall()

    best_faq = None
    best_score = 0

    for faq in faqs:
        cau_hoi = normalize(faq["cau_hoi"])
        score = 0

        # Ưu tiên câu hỏi có nội dung gần giống FAQ
        if cau_hoi and (cau_hoi in q or q in cau_hoi):
            score += 10

        # So khớp các từ khóa
        keywords = re.split(r"[;,\n]", faq["tu_khoa"])

        for keyword in keywords:
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
    text = re.sub(
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
        "[EMAIL]",
        text
    )

    text = re.sub(
        r"(?<!\d)(?:\+?84|0)\d{8,10}(?!\d)",
        "[SO_DIEN_THOAI]",
        text
    )

    return text[:1000]


# API nhận câu hỏi từ sinh viên
@chatbot_bp.route("/ask", methods=["POST"])
@roles_required("student")
def ask():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify(answer="Bạn vui lòng nhập câu hỏi nhé.")

    if len(question) > 1000:
        return jsonify(answer="Câu hỏi quá dài. Bạn vui lòng nhập ngắn gọn hơn.")

    db = get_db()

    # Xóa nhật ký đã quá 30 ngày
    db.execute("""
        DELETE FROM ChatLog
        WHERE ngay_tao < datetime('now', 'localtime', '-30 days')
    """)

    faq = tim_faq_phu_hop(db, question)

    if faq and faq["can_chuyen_nhan_vien"]:
        answer = (
            "Vấn đề này cần nhân viên hỗ trợ trực tiếp để đảm bảo "
            "thông tin được kiểm tra chính xác. Bạn có thể chọn "
            "Vẫn cần hỗ trợ để gửi yêu cầu đến nhà trường."
        )
        ket_qua = "chuyen_nhan_vien"
        handoff = True

    elif faq:
        answer = faq["cau_tra_loi"]
        ket_qua = "da_tim_thay"
        handoff = False

    else:
        answer = (
            "Xin lỗi, mình chưa tìm thấy câu trả lời phù hợp trong "
            "kho dữ liệu. Bạn có thể chọn Vẫn cần hỗ trợ để được "
            "nhân viên nhà trường giải đáp."
        )
        ket_qua = "khong_tim_thay"
        handoff = True

    db.execute("""
        INSERT INTO ChatLog(
            tai_khoan_id, cau_hoi, faq_id, ket_qua, ngay_tao
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        g.user["id"],
        che_thong_tin(question),
        faq["id"] if faq else None,
        ket_qua,
        now_str()
    ))

    db.commit()

    return jsonify(
        answer=answer,
        handoff=handoff
    )


# Trang quản lý FAQ dành cho nhân viên và admin
@chatbot_bp.route("/manage")
@roles_required(*STAFF)
def manage():
    db = get_db()

    faqs = db.execute("""
        SELECT f.*, 
               t.ho_ten AS ten_nguoi_tao,
               a.ho_ten AS ten_nguoi_duyet
        FROM FAQ f
        LEFT JOIN TaiKhoan t ON t.id = f.nguoi_tao_id
        LEFT JOIN TaiKhoan a ON a.id = f.nguoi_duyet_id
        ORDER BY f.id DESC
    """).fetchall()

    return render_template(
        "chatbot/manage.html",
        faqs=faqs
    )


# Nhân viên tạo FAQ mới
@chatbot_bp.route("/create", methods=["POST"])
@roles_required(*STAFF)
def create():
    cau_hoi = request.form.get("cau_hoi", "").strip()
    cau_tra_loi = request.form.get("cau_tra_loi", "").strip()
    tu_khoa = request.form.get("tu_khoa", "").strip()

    chuyen = 1 if request.form.get("can_chuyen_nhan_vien") else 0

    if not cau_hoi or not cau_tra_loi or not tu_khoa:
        flash("Vui lòng nhập đầy đủ thông tin FAQ.", "danger")
        return redirect(url_for("chatbot.manage"))

    db = get_db()

    db.execute("""
        INSERT INTO FAQ(
            cau_hoi, cau_tra_loi, tu_khoa,
            trang_thai, can_chuyen_nhan_vien,
            nguoi_tao_id, ngay_tao
        )
        VALUES (?, ?, ?, 'cho_duyet', ?, ?, ?)
    """, (
        cau_hoi,
        cau_tra_loi,
        tu_khoa,
        chuyen,
        g.user["id"],
        now_str()
    ))

    db.commit()

    flash("Đã gửi FAQ để admin duyệt.", "success")
    return redirect(url_for("chatbot.manage"))


# Chỉ admin được duyệt FAQ
@chatbot_bp.route("/approve/<int:faq_id>", methods=["POST"])
@roles_required("admin")
def approve(faq_id):
    db = get_db()

    db.execute("""
        UPDATE FAQ
        SET trang_thai = 'da_duyet',
            nguoi_duyet_id = ?,
            ngay_cap_nhat = ?
        WHERE id = ?
    """, (g.user["id"], now_str(), faq_id))

    db.commit()

    flash("Đã duyệt FAQ. Chatbot có thể sử dụng câu trả lời này.", "success")
    return redirect(url_for("chatbot.manage"))
