"""Kiểm thử M12. Chạy:  python -m unittest discover -s tests -v"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app          # noqa: E402
from models import get_db            # noqa: E402


class M12Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE": os.path.join(self.tmp, "t.db"), "TESTING": True})
        with self.app.app_context():
            db = get_db()
            # hai sinh viên có tài khoản để thử quyền sở hữu
            rows = db.execute("""SELECT tk.username, sv.id FROM TaiKhoan tk JOIN SinhVien sv
                                 ON sv.id = tk.sinh_vien_id ORDER BY sv.id LIMIT 2""").fetchall()
            self.sv_a, self.sv_b = rows[0]["username"], rows[1]["username"]
            self.id_a, self.id_b = rows[0]["id"], rows[1]["id"]
            db.execute("DELETE FROM YeuCauHoTro")  # bắt đầu sạch, test tự tạo dữ liệu
            db.commit()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, username, password="123456"):
        c = self.app.test_client()
        pw = {"admin": "admin123", "staff": "staff123"}.get(username, password)
        c.post("/auth/login", data={"username": username, "password": pw})
        return c

    def q(self, sql, *args):
        with self.app.app_context():
            return get_db().execute(sql, args).fetchall()

    def tao(self, client, **kw):
        data = {"loai_ho_tro_id": "1", "tieu_de": "Xin xác nhận bảng điểm",
                "noi_dung": "Em cần xác nhận bảng điểm học kỳ 1."}
        data.update(kw)
        return client.post("/support/new", data=data)

    def test_gui_yeu_cau_hop_le(self):
        r = self.tao(self.login(self.sv_a))
        self.assertEqual(r.status_code, 302)
        yc = self.q("SELECT * FROM YeuCauHoTro")[0]
        self.assertEqual(yc["trang_thai"], "cho_xu_ly")
        self.assertIsNone(yc["ngay_giai_quyet"])
        self.assertEqual(len(self.q("SELECT * FROM LichSuTrangThai")), 1)

    def test_form_khong_hop_le_khong_luu(self):
        c = self.login(self.sv_a)
        for bad in ({"tieu_de": ""}, {"noi_dung": "ngắn"}, {"loai_ho_tro_id": "999"},
                    {"loai_ho_tro_id": ""}):
            self.assertEqual(self.tao(c, **bad).status_code, 200)
        self.assertEqual(len(self.q("SELECT * FROM YeuCauHoTro")), 0)

    def test_sinh_vien_khong_xem_duoc_yeu_cau_nguoi_khac(self):
        self.tao(self.login(self.sv_a))
        yc_id = self.q("SELECT id FROM YeuCauHoTro")[0]["id"]
        b = self.login(self.sv_b)
        self.assertEqual(b.get(f"/support/{yc_id}").status_code, 403)
        self.assertEqual(b.post(f"/support/{yc_id}/reply", data={"noi_dung": "xen vào"}).status_code, 403)
        self.assertEqual(self.login(self.sv_a).get(f"/support/{yc_id}").status_code, 200)

    def test_sinh_vien_khong_vao_trang_nhan_vien(self):
        c = self.login(self.sv_a)
        self.assertNotEqual(c.get("/support/manage").status_code, 200)
        self.assertNotEqual(c.get("/support/api/summary").status_code, 200)

    def test_nhan_vien_phan_hoi_lan_dau_chuyen_dang_xu_ly(self):
        self.tao(self.login(self.sv_a))
        yc_id = self.q("SELECT id FROM YeuCauHoTro")[0]["id"]
        self.login("staff").post(f"/support/{yc_id}/reply", data={"noi_dung": "Đã nhận."})
        yc = self.q("SELECT * FROM YeuCauHoTro WHERE id = ?", yc_id)[0]
        self.assertEqual(yc["trang_thai"], "dang_xu_ly")
        self.assertIsNotNone(yc["nguoi_xu_ly_id"])
        self.assertEqual(len(self.q("SELECT * FROM LichSuTrangThai")), 2)

    def test_chuyen_trang_thai_va_mo_lai(self):
        self.tao(self.login(self.sv_a))
        yc_id = self.q("SELECT id FROM YeuCauHoTro")[0]["id"]
        s = self.login("staff")
        def tt(): return self.q("SELECT * FROM YeuCauHoTro WHERE id = ?", yc_id)[0]
        s.post(f"/support/{yc_id}/status", data={"trang_thai": "da_giai_quyet"})   # nhảy cóc
        self.assertEqual(tt()["trang_thai"], "cho_xu_ly")
        s.post(f"/support/{yc_id}/status", data={"trang_thai": "dang_xu_ly"})
        s.post(f"/support/{yc_id}/status", data={"trang_thai": "da_giai_quyet"})
        self.assertEqual(tt()["trang_thai"], "da_giai_quyet")
        self.assertIsNotNone(tt()["ngay_giai_quyet"])
        s.post(f"/support/{yc_id}/status", data={"trang_thai": "dang_xu_ly", "ghi_chu": "SV phản hồi chưa ổn"})
        self.assertEqual(tt()["trang_thai"], "dang_xu_ly")
        self.assertIsNone(tt()["ngay_giai_quyet"])
        self.assertEqual(len(self.q("SELECT * FROM LichSuTrangThai")), 4)

    def test_ghi_chu_noi_bo_sinh_vien_khong_thay(self):
        a = self.login(self.sv_a)
        self.tao(a)
        yc_id = self.q("SELECT id FROM YeuCauHoTro")[0]["id"]
        s = self.login("staff")
        s.post(f"/support/{yc_id}/reply", data={"noi_dung": "BIMAT-NOIBO-XYZ", "la_noi_bo": "on"})
        s.post(f"/support/{yc_id}/reply", data={"noi_dung": "Phản hồi công khai ABC"})
        self.assertNotIn("BIMAT-NOIBO-XYZ", a.get(f"/support/{yc_id}").get_data(as_text=True))
        self.assertIn("Phản hồi công khai ABC", a.get(f"/support/{yc_id}").get_data(as_text=True))
        self.assertIn("BIMAT-NOIBO-XYZ", s.get(f"/support/{yc_id}").get_data(as_text=True))

    def test_api_tong_hop(self):
        self.tao(self.login(self.sv_a))
        self.assertNotEqual(self.login("staff").get("/support/api/summary").status_code, 200)
        r = self.login("admin").get("/support/api/summary")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["tong"], 1)
        self.assertEqual(d["theo_trang_thai"]["cho_xu_ly"], 1)
        self.assertEqual(d["ty_le_xu_ly"], 0)
        self.assertEqual(self.login("admin").get("/support/api/summary?tu_ngay=abc").status_code, 400)

    def test_xoa_sinh_vien_con_yeu_cau_bi_chan(self):
        self.tao(self.login(self.sv_a))
        self.login("admin").post(f"/students/{self.id_a}/delete")
        self.assertEqual(len(self.q("SELECT * FROM SinhVien WHERE id = ?", self.id_a)), 1)
        self.assertEqual(len(self.q("SELECT * FROM YeuCauHoTro")), 1)

    def test_loc_va_phan_trang_nhan_vien(self):
        a = self.login(self.sv_a)
        for i in range(12):
            self.tao(a, tieu_de=f"Yêu cầu số {i}")
        s = self.login("staff")
        self.assertEqual(s.get("/support/manage").status_code, 200)
        self.assertEqual(s.get("/support/manage?page=999&trang_thai=sai&loai=abc").status_code, 200)
        self.assertIn("Yêu cầu số 3", s.get("/support/manage?q=yeu+cau+so+3").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
