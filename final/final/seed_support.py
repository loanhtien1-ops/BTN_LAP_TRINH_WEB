"""Dữ liệu mẫu M12: ~80 yêu cầu rải 5 tháng, đủ 3 trạng thái và 4 loại, kèm phản hồi + lịch sử.
Để Hà (M17) có dữ liệu vẽ biểu đồ theo tháng."""
import random
from datetime import datetime, timedelta
from support import UU_TIEN_THEO_LOAI

TIEU_DE = {
    "hoc_vu": ["Xin xác nhận bảng điểm", "Hỏi về đăng ký học phần", "Xin bảo lưu kết quả học tập",
               "Thắc mắc điểm thi cuối kỳ"],
    "tai_khoan": ["Quên mật khẩu cổng sinh viên", "Tài khoản email sinh viên bị khóa",
                  "Cần cập nhật thông tin liên hệ"],
    "hoc_phi": ["Hỏi về công nợ học phí", "Xin gia hạn nộp học phí", "Thắc mắc khoản thu học kỳ"],
    "ky_thuat": ["Không tải được trang đăng ký học phần", "Lỗi hiển thị lịch học",
                 "Không đăng nhập được trên điện thoại"],
    "khac": ["Xin giấy giới thiệu thực tập", "Góp ý về cơ sở vật chất"],
}
NOI_DUNG = "Em cần được hỗ trợ về vấn đề này, mong nhà trường xem xét và phản hồi sớm giúp em ạ."
PHAN_HOI_NV = ["Nhà trường đã tiếp nhận yêu cầu và đang xử lý cho bạn.",
               "Bộ phận chuyên môn đang kiểm tra thông tin, bạn vui lòng chờ thêm."]
PHAN_HOI_XONG = ["Yêu cầu đã được giải quyết. Nếu còn vướng mắc, bạn hãy phản hồi tại đây.",
                 "Vấn đề của bạn đã được xử lý xong, bạn kiểm tra lại giúp nhà trường nhé."]
FMT = "%Y-%m-%d %H:%M:%S"


def seed_support_data(db, so_yeu_cau=80):
    rng = random.Random(12)
    loai = {r["ma_loai"]: r["id"] for r in db.execute("SELECT id, ma_loai FROM LoaiHoTro")}
    sv_list = db.execute("""SELECT sv.id AS sv_id, tk.id AS tk_id FROM SinhVien sv
                            JOIN TaiKhoan tk ON tk.sinh_vien_id = sv.id""").fetchall()
    staff = [r["id"] for r in db.execute(
        "SELECT id FROM TaiKhoan WHERE vai_tro = 'support_staff' ORDER BY id")]
    if not (loai and sv_list and staff):
        return
    now = datetime.now()

    def ghi_lich_su(yc_id, cu, moi, tk_id, ghi_chu, luc):
        db.execute("""INSERT INTO LichSuTrangThai(yeu_cau_id, trang_thai_cu, trang_thai_moi,
                      nguoi_thay_doi_id, ghi_chu, ngay_thay_doi) VALUES (?, ?, ?, ?, ?, ?)""",
                   (yc_id, cu, moi, tk_id, ghi_chu, luc.strftime(FMT)))

    def ghi_phan_hoi(yc_id, tk_id, noi_dung, luc, noi_bo=0):
        db.execute("""INSERT INTO PhanHoi(yeu_cau_id, nguoi_gui_id, noi_dung, la_noi_bo, ngay_tao)
                      VALUES (?, ?, ?, ?, ?)""", (yc_id, tk_id, noi_dung, noi_bo, luc.strftime(FMT)))

    for _ in range(so_yeu_cau):
        ma = rng.choice(list(loai))
        sv = rng.choice(sv_list)
        nv = rng.choice(staff)
        tao = now - timedelta(days=rng.randint(0, 150), hours=rng.randint(0, 23),
                              minutes=rng.randint(0, 59))
        tt = rng.choices(["cho_xu_ly", "dang_xu_ly", "da_giai_quyet"], weights=[2, 2, 6])[0]
        t1 = min(tao + timedelta(hours=rng.randint(1, 24)), now)
        t2 = min(t1 + timedelta(days=rng.randint(1, 6)), now)
        cuoi = tao if tt == "cho_xu_ly" else (t1 if tt == "dang_xu_ly" else t2)

        cur = db.execute(
            """INSERT INTO YeuCauHoTro(sinh_vien_id, loai_ho_tro_id, tieu_de, noi_dung, muc_uu_tien,
                   trang_thai, nguoi_xu_ly_id, ngay_tao, ngay_cap_nhat, ngay_giai_quyet)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sv["sv_id"], loai[ma], rng.choice(TIEU_DE[ma]), NOI_DUNG,
             UU_TIEN_THEO_LOAI[ma], tt,
             None if tt == "cho_xu_ly" else nv, tao.strftime(FMT), cuoi.strftime(FMT),
             t2.strftime(FMT) if tt == "da_giai_quyet" else None))
        yc_id = cur.lastrowid
        ghi_lich_su(yc_id, None, "cho_xu_ly", sv["tk_id"], "Sinh viên gửi yêu cầu", tao)
        if tt != "cho_xu_ly":
            ghi_phan_hoi(yc_id, nv, rng.choice(PHAN_HOI_NV), t1)
            ghi_lich_su(yc_id, "cho_xu_ly", "dang_xu_ly", nv, "Tự động khi nhân viên phản hồi lần đầu", t1)
            if rng.random() < 0.2:
                ghi_phan_hoi(yc_id, nv, "Ghi chú nội bộ: đã chuyển phòng chức năng kiểm tra.", t1, 1)
        if tt == "da_giai_quyet":
            ghi_phan_hoi(yc_id, nv, rng.choice(PHAN_HOI_XONG), t2)
            ghi_lich_su(yc_id, "dang_xu_ly", "da_giai_quyet", nv, None, t2)
    db.commit()
