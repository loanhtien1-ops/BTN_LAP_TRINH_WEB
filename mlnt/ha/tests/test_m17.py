"""Kiểm thử M17 (dashboard). Chạy:  python -m unittest tests.test_m17 -v"""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app          # noqa: E402
from models import get_db            # noqa: E402

CSRF = "token-thu-nghiem"


class M17Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE": os.path.join(self.tmp, "t.db"), "TESTING": True})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ tiện ích
    def login(self, username):
        c = self.app.test_client()
        pw = {"admin": "admin123", "staff": "staff123", "staff2": "staff123"}.get(username, "123456")
        c.post("/auth/login", data={"username": username, "password": pw})
        with c.session_transaction() as s:
            s["dash_csrf"] = CSRF
        return c

    def q(self, sql, *args):
        with self.app.app_context():
            return get_db().execute(sql, args).fetchall()

    def run_sql(self, sql, *args):
        with self.app.app_context():
            db = get_db()
            db.execute(sql, args)
            db.commit()

    def xoa_yeu_cau(self):
        self.run_sql("DELETE FROM YeuCauHoTro")

    def them_yeu_cau(self, ngay_tao, trang_thai="cho_xu_ly", ngay_giai_quyet=None, tiep_nhan=None, loai=1, sv_id=None):
        with self.app.app_context():
            db = get_db()
            sv = sv_id or db.execute("SELECT id FROM SinhVien ORDER BY id LIMIT 1").fetchone()[0]
            cur = db.execute(
                """INSERT INTO YeuCauHoTro(sinh_vien_id, loai_ho_tro_id, tieu_de, noi_dung, trang_thai,
                                           ngay_tao, ngay_giai_quyet) VALUES (?, ?, 'T', 'N', ?, ?, ?)""",
                (sv, loai, trang_thai, ngay_tao, ngay_giai_quyet))
            if tiep_nhan:
                db.execute("""INSERT INTO LichSuTrangThai(yeu_cau_id, trang_thai_cu, trang_thai_moi, ngay_thay_doi)
                              VALUES (?, 'cho_xu_ly', 'dang_xu_ly', ?)""", (cur.lastrowid, tiep_nhan))
            db.commit()

    def chi_tieu(self, ma):
        return self.q("SELECT * FROM ChiTieu WHERE ma = ?", ma)[0]

    def chuyen(self, c, ma, hanh_dong, **extra):
        data = {"csrf": CSRF, "hanh_dong": hanh_dong}
        data.update(extra)
        return c.post("/dashboard/chi-tieu/%s/chuyen" % ma, data=data)

    # ------------------------------------------------------------ phân quyền
    def test_student_khong_vao_duoc(self):
        sv = self.q("SELECT username FROM TaiKhoan WHERE vai_tro = 'student' LIMIT 1")[0][0]
        c = self.login(sv)
        for url in ("/dashboard/", "/dashboard/api/ho-tro", "/dashboard/api/chi-tiet", "/dashboard/api/sinh-vien",
                    "/dashboard/api/he-thong", "/dashboard/chi-tieu", "/dashboard/pham-vi"):
            self.assertEqual(c.get(url).status_code, 302, url)

    def test_chua_dang_nhap_bi_chuyen_ve_login(self):
        r = self.app.test_client().get("/dashboard/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/login", r.headers["Location"])

    def test_staff_chi_xem_phan_ho_tro(self):
        c = self.login("staff")
        page = c.get("/dashboard/")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("SV01", page.get_data(as_text=True))
        for url in ("/dashboard/api/ho-tro", "/dashboard/api/chi-tiet", "/dashboard/chi-tieu"):
            self.assertEqual(c.get(url).status_code, 200, url)
        for url in ("/dashboard/api/sinh-vien", "/dashboard/api/he-thong", "/dashboard/pham-vi"):
            self.assertEqual(c.get(url).status_code, 302, url)
        self.assertEqual(c.get("/dashboard/chi-tieu/SV01").status_code, 404)
        self.assertEqual(c.get("/dashboard/chi-tieu/HT01").status_code, 200)

    def test_admin_xem_du(self):
        c = self.login("admin")
        page = c.get("/dashboard/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("SV01", page.get_data(as_text=True))
        for url in ("/dashboard/api/sinh-vien", "/dashboard/api/he-thong", "/dashboard/chi-tieu",
                    "/dashboard/chi-tieu/SV01", "/dashboard/pham-vi"):
            self.assertEqual(c.get(url).status_code, 200, url)

    # ------------------------------------------------------------ số liệu khớp CSDL và khớp API của M12
    def test_so_lieu_ho_tro_khop_csdl(self):
        d = self.login("admin").get("/dashboard/api/ho-tro").get_json()
        tong = self.q("SELECT COUNT(*) FROM YeuCauHoTro")[0][0]
        xong = self.q("SELECT COUNT(*) FROM YeuCauHoTro WHERE trang_thai = 'da_giai_quyet'")[0][0]
        self.assertEqual(d["tong"], tong)
        for key in ("theo_trang_thai", ):
            self.assertEqual(sum(d[key].values()), tong)
        for key in ("theo_loai", "theo_thang", "theo_nganh", "theo_lop"):
            self.assertEqual(sum(x["so"] for x in d[key]), tong, key)
        self.assertEqual(d["ty_le_giai_quyet"], round(xong / tong * 100, 1))
        for key in ("pham_vi", "nguon", "thoi_diem_tinh", "ghi_chu"):
            self.assertIn(key, d)

    def test_nhat_quan_voi_api_cua_m12(self):
        """Cùng một chỉ số thì dashboard và /support/api/summary phải ra cùng một số."""
        c = self.login("admin")
        m17 = c.get("/dashboard/api/ho-tro").get_json()
        m12 = c.get("/support/api/summary").get_json()
        self.assertEqual(m17["tong"], m12["tong"])
        self.assertEqual(m17["theo_trang_thai"], m12["theo_trang_thai"])
        self.assertAlmostEqual(m17["ty_le_giai_quyet"], m12["ty_le_xu_ly"], delta=0.06)

    def test_so_lieu_sinh_vien_khop_va_khong_lo_ca_nhan(self):
        r = self.login("admin").get("/dashboard/api/sinh-vien")
        d = r.get_json()
        tong = self.q("SELECT COUNT(*) FROM SinhVien")[0][0]
        self.assertEqual(d["tong"], tong)
        for key in ("theo_lop", "theo_nganh", "theo_khoa", "theo_trang_thai_hoc"):
            self.assertEqual(sum(x["so"] for x in d[key]), tong, key)
        text = r.get_data(as_text=True)
        for ho_ten in [row[0] for row in self.q("SELECT ho_ten FROM SinhVien LIMIT 5")]:
            self.assertNotIn(ho_ten, text)
        self.assertNotIn("ma_sv", text)

    # ------------------------------------------------------------ bộ lọc
    def test_loc_theo_ngay(self):
        self.xoa_yeu_cau()
        self.them_yeu_cau("2026-08-10 09:00:00")
        self.them_yeu_cau("2026-09-10 09:00:00")
        d = self.login("admin").get("/dashboard/api/ho-tro?tu_ngay=2026-09-01&den_ngay=2026-09-30").get_json()
        self.assertEqual(d["tong"], 1)
        self.assertEqual([x["thang"] for x in d["theo_thang"]], ["2026-09"])

    def test_loc_theo_nganh_va_lop(self):
        c = self.login("admin")
        nganh = self.q("SELECT l.nganh_id FROM YeuCauHoTro y JOIN SinhVien s ON s.id = y.sinh_vien_id "
                       "JOIN Lop l ON l.id = s.lop_id LIMIT 1")[0][0]
        dem = self.q("SELECT COUNT(*) FROM YeuCauHoTro y JOIN SinhVien s ON s.id = y.sinh_vien_id "
                     "JOIN Lop l ON l.id = s.lop_id WHERE l.nganh_id = ?", nganh)[0][0]
        d = c.get("/dashboard/api/ho-tro?nganh_id=%d" % nganh).get_json()
        self.assertEqual(d["tong"], dem)
        self.assertEqual(len(d["theo_nganh"]), 1)
        lop = self.q("SELECT id FROM Lop WHERE nganh_id = ? LIMIT 1", nganh)[0][0]
        dem_lop = self.q("SELECT COUNT(*) FROM YeuCauHoTro y JOIN SinhVien s ON s.id = y.sinh_vien_id "
                         "WHERE s.lop_id = ?", lop)[0][0]
        self.assertEqual(c.get("/dashboard/api/ho-tro?lop_id=%d" % lop).get_json()["tong"], dem_lop)
        sv = c.get("/dashboard/api/sinh-vien?nganh_id=%d" % nganh).get_json()
        self.assertEqual(sv["tong"], self.q("SELECT COUNT(*) FROM SinhVien s JOIN Lop l ON l.id = s.lop_id "
                                            "WHERE l.nganh_id = ?", nganh)[0][0])

    def test_loc_sai_dinh_dang(self):
        c = self.login("admin")
        for q in ("tu_ngay=31-12-2026", "tu_ngay=2026-10-02&den_ngay=2026-10-01", "nganh_id=abc", "lop_id=1;drop"):
            self.assertEqual(c.get("/dashboard/api/ho-tro?" + q).status_code, 400, q)
        self.assertEqual(c.get("/dashboard/api/chi-tiet?trang_thai=khong_co").status_code, 400)

    def test_khong_co_du_lieu(self):
        self.xoa_yeu_cau()
        d = self.login("admin").get("/dashboard/api/ho-tro").get_json()
        self.assertEqual(d["tong"], 0)
        self.assertIsNone(d["ty_le_giai_quyet"])
        self.assertIsNone(d["thoi_gian"]["giai_quyet_tb_gio"])
        self.assertEqual(d["sinh_vien_gui_yeu_cau"]["da_gui"], 0)
        self.assertEqual(d["sinh_vien_gui_yeu_cau"]["ty_le"], 0.0)
        self.assertEqual(d["theo_thang"], [])

    def test_sinh_vien_da_gui_yeu_cau(self):
        self.xoa_yeu_cau()
        sv = [r[0] for r in self.q("SELECT id FROM SinhVien ORDER BY id LIMIT 2")]
        self.them_yeu_cau("2026-10-01 08:00:00", sv_id=sv[0])
        self.them_yeu_cau("2026-10-02 08:00:00", sv_id=sv[0])
        self.them_yeu_cau("2026-10-03 08:00:00", sv_id=sv[1])
        d = self.login("admin").get("/dashboard/api/ho-tro").get_json()["sinh_vien_gui_yeu_cau"]
        self.assertEqual(d["da_gui"], 2)
        self.assertEqual(d["tong_sinh_vien"], self.q("SELECT COUNT(*) FROM SinhVien")[0][0])

    # ------------------------------------------------------------ thời gian xử lý
    def test_thoi_gian_xu_ly_theo_loai_va_thang(self):
        self.xoa_yeu_cau()
        # A (loại 1): tiếp nhận sau 2 giờ, giải quyết sau 12 giờ, đúng hạn. B (loại 2): sau 4 giờ và 48 giờ, trễ.
        self.them_yeu_cau("2026-10-01 08:00:00", "da_giai_quyet", "2026-10-01 20:00:00", "2026-10-01 10:00:00", loai=1)
        self.them_yeu_cau("2026-10-02 08:00:00", "da_giai_quyet", "2026-10-04 08:00:00", "2026-10-02 12:00:00", loai=2)
        d = self.login("admin").get("/dashboard/api/ho-tro").get_json()
        tg = d["thoi_gian"]
        self.assertEqual(tg["tiep_nhan_tb_gio"], 3.0)
        self.assertEqual(tg["giai_quyet_tb_gio"], 30.0)
        self.assertEqual(tg["nhanh_nhat_gio"], 12.0)
        self.assertEqual(tg["cham_nhat_gio"], 48.0)
        self.assertEqual(tg["ty_le_dung_han"], 50.0)
        self.assertEqual({x["id"]: x["gio"] for x in tg["theo_loai"]}, {1: 12.0, 2: 48.0})
        self.assertEqual(d["theo_thang"], [{"thang": "2026-10", "so": 2, "gio_giai_quyet_tb": 30.0}])

    def test_qua_han(self):
        self.xoa_yeu_cau()
        cu = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        moi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.them_yeu_cau(cu)
        self.them_yeu_cau(moi)
        self.them_yeu_cau(cu, "da_giai_quyet", moi)
        c = self.login("admin")
        self.assertEqual(c.get("/dashboard/api/ho-tro").get_json()["qua_han"], 1)
        self.assertEqual(c.get("/dashboard/api/chi-tiet?qua_han=1").get_json()["tong"], 1)

    # ------------------------------------------------------------ danh sách truy xuất khớp biểu đồ
    def test_chi_tiet_khop_bieu_do_va_khong_lo_ca_nhan(self):
        c = self.login("admin")
        d = c.get("/dashboard/api/ho-tro?tu_ngay=2026-07-01&den_ngay=2026-09-30").get_json()
        for tt, so_luong in d["theo_trang_thai"].items():
            r = c.get("/dashboard/api/chi-tiet?tu_ngay=2026-07-01&den_ngay=2026-09-30&trang_thai=" + tt)
            self.assertEqual(r.get_json()["tong"], so_luong, tt)
        for loai in d["theo_loai"]:
            r = c.get("/dashboard/api/chi-tiet?tu_ngay=2026-07-01&den_ngay=2026-09-30&loai=%d" % loai["id"])
            self.assertEqual(r.get_json()["tong"], loai["so"])
        r = c.get("/dashboard/api/chi-tiet")
        text = r.get_data(as_text=True)
        for ho_ten in [row[0] for row in self.q("SELECT ho_ten FROM SinhVien LIMIT 8")]:
            self.assertNotIn(ho_ten, text)
        muc = r.get_json()["muc"][0]
        self.assertTrue(muc["url"].startswith("/support/"))

    def test_chi_tiet_phan_trang(self):
        c = self.login("admin")
        p1 = c.get("/dashboard/api/chi-tiet").get_json()
        p2 = c.get("/dashboard/api/chi-tiet?page=2").get_json()
        self.assertEqual(len(p1["muc"]), 10)
        self.assertEqual(p1["so_trang"], 8)
        self.assertNotEqual(p1["muc"][0]["id"], p2["muc"][0]["id"])
        self.assertEqual(c.get("/dashboard/api/chi-tiet?page=999").get_json()["trang"], 8)

    # ------------------------------------------------------------ thống kê hệ thống
    def test_thong_ke_he_thong(self):
        d = self.login("admin").get("/dashboard/api/he-thong").get_json()
        self.assertEqual(sum(x["so"] for x in d["tai_khoan_theo_vai_tro"]), self.q("SELECT COUNT(*) FROM TaiKhoan")[0][0])
        self.assertEqual(sum(x["so"] for x in d["yeu_cau_theo_nhan_vien"]), self.q("SELECT COUNT(*) FROM YeuCauHoTro")[0][0])
        self.assertEqual(d["phan_hoi"]["tong"], self.q("SELECT COUNT(*) FROM PhanHoi")[0][0])

    # ------------------------------------------------------------ phạm vi của nhân viên
    def test_pham_vi_nhan_vien(self):
        self.xoa_yeu_cau()
        self.them_yeu_cau("2026-10-01 08:00:00", loai=1)
        self.them_yeu_cau("2026-10-02 08:00:00", loai=1)
        self.them_yeu_cau("2026-10-03 08:00:00", loai=2)
        staff = self.login("staff")
        self.assertEqual(staff.get("/dashboard/api/ho-tro").get_json()["tong"], 3)   # chưa giao: xem tất cả

        tk = self.q("SELECT id FROM TaiKhoan WHERE username = 'staff'")[0][0]
        r = self.login("admin").post("/dashboard/pham-vi", data={"csrf": CSRF, "loai_%d" % tk: ["1"]})
        self.assertEqual(r.status_code, 302)

        d = staff.get("/dashboard/api/ho-tro").get_json()
        self.assertEqual(d["tong"], 2)
        self.assertEqual([x["id"] for x in d["theo_loai"]], [1])
        self.assertEqual(staff.get("/dashboard/api/chi-tiet").get_json()["tong"], 2)
        self.assertEqual(staff.get("/dashboard/api/chi-tiet?loai=2").get_json()["tong"], 0)
        self.assertEqual(self.login("admin").get("/dashboard/api/ho-tro").get_json()["tong"], 3)
        # nhân viên khác chưa được giao vẫn xem tất cả
        self.assertEqual(self.login("staff2").get("/dashboard/api/ho-tro").get_json()["tong"], 3)

    # ------------------------------------------------------------ CSRF
    def test_post_thieu_csrf_bi_chan(self):
        admin = self.login("admin")
        self.assertEqual(admin.post("/dashboard/pham-vi", data={}).status_code, 400)
        self.assertEqual(admin.post("/dashboard/chi-tieu/HT01/chuyen", data={"hanh_dong": "xac_nhan_nguon"}).status_code, 400)
        self.assertEqual(admin.post("/dashboard/chi-tieu/HT01/sua", data={"ten": "x"}).status_code, 400)
        self.assertEqual(self.chi_tieu("HT01")["trang_thai"], "nhap")

    def test_staff_khong_post_duoc(self):
        self.login("admin").get("/dashboard/")            # tạo bảng chỉ tiêu
        r = self.chuyen(self.login("staff"), "HT01", "xac_nhan_nguon")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.chi_tieu("HT01")["trang_thai"], "nhap")

    # ------------------------------------------------------------ quy trình chỉ tiêu
    def test_danh_muc_duoc_nap_san(self):
        self.login("admin").get("/dashboard/")
        rows = self.q("SELECT ma, phien_ban, trang_thai, dau_moi FROM ChiTieu ORDER BY ma")
        self.assertEqual([r["ma"] for r in rows], ["HT01", "HT02", "HT03", "HT04", "HT05", "HT06", "SV01"])
        self.assertTrue(all(r["phien_ban"] == 1 and r["trang_thai"] == "nhap" and r["dau_moi"] for r in rows))
        self.assertEqual(self.q("SELECT COUNT(*) FROM LichSuChiTieu")[0][0], 7)

    def test_quy_trinh_cong_bo(self):
        c = self.login("admin")
        c.get("/dashboard/")
        # không được nhảy cóc
        self.chuyen(c, "HT01", "cong_bo")
        self.chuyen(c, "HT01", "kiem_tra")
        self.assertEqual(self.chi_tieu("HT01")["trang_thai"], "nhap")
        self.assertEqual(self.q("SELECT COUNT(*) FROM KetQuaChiTieu")[0][0], 0)
        # đi đúng thứ tự
        self.chuyen(c, "HT01", "xac_nhan_nguon")
        self.chuyen(c, "HT01", "kiem_tra", can_cu="đã đối chiếu")
        self.assertEqual(self.chi_tieu("HT01")["trang_thai"], "da_kiem_tra")
        self.chuyen(c, "HT01", "cong_bo", tu_ngay="2026-07-01", den_ngay="2026-09-30")
        ct = self.chi_tieu("HT01")
        self.assertEqual(ct["trang_thai"], "da_cong_bo")
        kq = self.q("SELECT * FROM KetQuaChiTieu")[0]
        dung = c.get("/dashboard/api/ho-tro?tu_ngay=2026-07-01&den_ngay=2026-09-30").get_json()["tong"]
        self.assertEqual(kq["gia_tri"], dung)
        self.assertEqual((kq["ky_tu"], kq["ky_den"], kq["phien_ban"]), ("2026-07-01", "2026-09-30", 1))
        self.assertIsNotNone(kq["nguoi_cong_bo_id"])
        # công bố thêm kỳ khác
        self.chuyen(c, "HT01", "cong_bo", tu_ngay="2026-10-01", den_ngay="2026-10-31")
        self.assertEqual(self.q("SELECT COUNT(*) FROM KetQuaChiTieu")[0][0], 2)
        hanh_dong = [r["hanh_dong"] for r in self.q("SELECT hanh_dong FROM LichSuChiTieu WHERE chi_tieu_id = ? ORDER BY id", ct["id"])]
        self.assertEqual(hanh_dong, ["tao", "xac_nhan_nguon", "kiem_tra", "cong_bo", "cong_bo"])
        self.assertEqual(c.get("/dashboard/chi-tieu/HT01").status_code, 200)
        self.assertEqual(c.get("/dashboard/chi-tieu").status_code, 200)

    def test_cong_bo_sinh_vien_khong_theo_ky(self):
        c = self.login("admin")
        c.get("/dashboard/")
        for hd in ("xac_nhan_nguon", "kiem_tra", "cong_bo"):
            self.chuyen(c, "SV01", hd)
        kq = self.q("SELECT * FROM KetQuaChiTieu")[0]
        self.assertEqual(kq["gia_tri"], self.q("SELECT COUNT(*) FROM SinhVien")[0][0])
        self.assertIsNone(kq["ky_tu"])

    def test_cong_bo_sai_ky_khong_ghi_gi(self):
        c = self.login("admin")
        c.get("/dashboard/")
        for hd in ("xac_nhan_nguon", "kiem_tra"):
            self.chuyen(c, "HT02", hd)
        self.chuyen(c, "HT02", "cong_bo", tu_ngay="2026-10-31", den_ngay="2026-10-01")
        self.assertEqual(self.q("SELECT COUNT(*) FROM KetQuaChiTieu")[0][0], 0)
        self.assertEqual(self.chi_tieu("HT02")["trang_thai"], "da_kiem_tra")

    def test_tra_ve_can_ly_do(self):
        c = self.login("admin")
        c.get("/dashboard/")
        self.chuyen(c, "HT03", "xac_nhan_nguon")
        self.chuyen(c, "HT03", "tra_ve")
        self.assertEqual(self.chi_tieu("HT03")["trang_thai"], "da_xac_nhan_nguon")
        self.chuyen(c, "HT03", "tra_ve", can_cu="nguồn chưa đúng")
        self.assertEqual(self.chi_tieu("HT03")["trang_thai"], "nhap")

    def test_sua_dinh_nghia_tao_phien_ban_moi(self):
        c = self.login("admin")
        c.get("/dashboard/")
        for hd in ("xac_nhan_nguon", "kiem_tra"):
            self.chuyen(c, "HT04", hd)
        truoc = self.chi_tieu("HT04")
        form = {k: truoc[k] or "" for k in ("ten", "cong_thuc", "don_vi", "chieu_phan_tich", "nguon", "dau_moi")}
        form.update(csrf=CSRF, ten="Giờ giải quyết trung bình (đã đổi tên)")
        c.post("/dashboard/chi-tieu/HT04/sua", data=dict(form, can_cu=""))          # thiếu căn cứ
        self.assertEqual(self.chi_tieu("HT04")["phien_ban"], 1)
        c.post("/dashboard/chi-tieu/HT04/sua", data=dict(form, can_cu="Thống nhất trong buổi họp nhóm"))
        sau = self.chi_tieu("HT04")
        self.assertEqual((sau["phien_ban"], sau["trang_thai"]), (2, "nhap"))
        ls = self.q("SELECT * FROM LichSuChiTieu WHERE chi_tieu_id = ? AND hanh_dong = 'sua_dinh_nghia'", sau["id"])[0]
        self.assertEqual(ls["can_cu"], "Thống nhất trong buổi họp nhóm")
        self.assertIn(truoc["ten"], ls["noi_dung_truoc"])
        self.assertIsNotNone(ls["nguoi_thuc_hien_id"])
        self.assertEqual(c.get("/dashboard/chi-tieu/HT04").status_code, 200)


if __name__ == "__main__":
    unittest.main()
