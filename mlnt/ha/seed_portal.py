"""
Seed dữ liệu mẫu bổ sung cho Cổng thông tin người học
"""
from models import get_db

COURSES_DATA = [
    # Ngành CNTT
    ("CNTT", "TIN1101", "Nhập môn Công nghệ thông tin", 3, 1, "Đại cương"),
    ("CNTT", "TOA1101", "Toán cao cấp 1", 3, 1, "Đại cương"),
    ("CNTT", "TIN1102", "Kỹ thuật lập trình C/C++", 3, 1, "Bắt buộc"),
    ("CNTT", "TIN1201", "Cấu trúc dữ liệu và giải thuật", 3, 2, "Bắt buộc"),
    ("CNTT", "TIN1202", "Cơ sở dữ liệu (Database Systems)", 3, 2, "Bắt buộc"),
    ("CNTT", "TIN1203", "Kiến trúc máy tính & HĐH", 3, 2, "Bắt buộc"),
    ("CNTT", "TIN1301", "Lập trình Web (Flask & Frontend)", 3, 3, "Chuyên ngành"),
    ("CNTT", "TIN1302", "Mạng máy tính & Truyền thông", 3, 3, "Chuyên ngành"),
    ("CNTT", "TIN1303", "Phân tích thiết kế hệ thống", 3, 3, "Chuyên ngành"),
    ("CNTT", "TIN1401", "Học máy & Khai phá dữ liệu", 3, 4, "Chuyên ngành"),
    ("CNTT", "TIN1402", "An toàn và bảo mật hệ thống", 3, 4, "Tự chọn"),
    ("CNTT", "TIN1403", "Phát triển ứng dụng di động", 3, 4, "Tự chọn"),
]

def seed_portal_data(db):
    # Lấy id các ngành
    nganh_map = {row["ma_nganh"]: row["id"] for row in db.execute("SELECT id, ma_nganh FROM NganhHoc").fetchall()}

    # 1. Thêm Chương trình đào tạo
    for ma_nganh, ma_hp, ten_hp, tc, hk, loai in COURSES_DATA:
        n_id = nganh_map.get(ma_nganh)
        if n_id:
            db.execute("""
                INSERT OR IGNORE INTO ChuongTrinhDaoTao (ma_hp, ten_hp, so_tin_chi, hoc_ky_goi_y, nganh_id, loai_hp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ma_hp, ten_hp, tc, hk, n_id, loai))

    # 2. Sinh dữ liệu Kết quả học tập, Tài chính và Yêu cầu cho các sinh viên hiện có
    students = db.execute("SELECT id, ma_sv, lop_id FROM SinhVien LIMIT 15").fetchall()
    cntt_courses = db.execute("SELECT id, so_tin_chi FROM ChuongTrinhDaoTao WHERE nganh_id = ?", (nganh_map.get("CNTT", 1),)).fetchall()

    for idx, sv in enumerate(students):
        # Điểm các môn kỳ 1 & 2
        for c_idx, c in enumerate(cntt_courses[:6]):
            # Tạo điểm mẫu ngẫu nhiên khá giỏi
            cc = 8.5 + (idx + c_idx) % 2
            thi = 7.0 + ((idx * 2 + c_idx) % 3)
            tk = round(cc * 0.3 + thi * 0.7, 1)
            letter = "A" if tk >= 8.5 else ("B+" if tk >= 8.0 else ("B" if tk >= 7.0 else "C+"))
            db.execute("""
                INSERT OR IGNORE INTO KetQuaHocTap (sinh_vien_id, hoc_phan_id, diem_chuyen_can, diem_thi, diem_tong_ket, diem_chu, trang_thai_hp)
                VALUES (?, ?, ?, ?, ?, ?, 'Đạt')
            """, (sv["id"], c["id"], cc, thi, tk, letter))

        # Dữ liệu tài chính học phí
        db.execute("""
            INSERT INTO TaiChinhSinhVien (sinh_vien_id, hoc_ky, noi_dung, so_tien_phai_nop, so_tien_da_nop, han_nop, trang_thai_nop, ngay_giao_dich)
            VALUES (?, 'Học kỳ 1 (2025 - 2026)', 'Học phí 15 tín chỉ học phần', 8500000, 8500000, '2025-10-15', 'Đã nộp đủ', '2025-10-10 09:15:30')
        """, (sv["id"],))

        db.execute("""
            INSERT INTO TaiChinhSinhVien (sinh_vien_id, hoc_ky, noi_dung, so_tien_phai_nop, so_tien_da_nop, han_nop, trang_thai_nop, ngay_giao_dich)
            VALUES (?, 'Học kỳ 2 (2025 - 2026)', 'Học phí 18 tín chỉ học kỳ 2', 9800000, 9800000, '2026-03-20', 'Đã nộp đủ', '2026-03-12 14:40:22')
        """, (sv["id"],))

        # Kỳ hiện tại (chưa nộp hoặc nộp một phần)
        st_nop = 0 if idx % 2 == 0 else 5000000
        tt_nop = "Chưa nộp" if st_nop == 0 else "Nộp một phần"
        db.execute("""
            INSERT INTO TaiChinhSinhVien (sinh_vien_id, hoc_ky, noi_dung, so_tien_phai_nop, so_tien_da_nop, han_nop, trang_thai_nop, ngay_giao_dich)
            VALUES (?, 'Học kỳ 1 (2026 - 2027)', 'Học phí tạm thu học kỳ 1', 10500000, ?, '2026-11-15', ?, NULL)
        """, (sv["id"], st_nop, tt_nop))

    # (Yêu cầu hỗ trợ mẫu của M12 nằm ở seed_support.py)

    db.commit()
