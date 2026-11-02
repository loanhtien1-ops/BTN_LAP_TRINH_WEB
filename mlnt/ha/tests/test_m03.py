"""Kiểm thử module M03. Chạy: python -m unittest discover -s tests -v (từ thư mục gốc dự án)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import get_db  # noqa: E402


class M03Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": os.path.join(self.tmp.name, "test.db"), "TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    # ---- tiện ích
    def post(self, url, data=None, **kw):
        with self.client.session_transaction() as s:
            s["csrf_token"] = "tok"
        return self.client.post(url, data={**(data or {}), "csrf_token": "tok"}, **kw)

    def login(self, username, password):
        return self.post("/login", {"username": username, "password": password})

    def student_form(self, **over):
        data = {"ma_sv": "SV990001", "ho_ten": "Trần Văn Test", "ngay_sinh": "2004-05-17",
                "gioi_tinh": "Nam", "email": "test@example.com", "so_dien_thoai": "0912345678",
                "dia_chi": "Hà Nội", "lop_id": "1", "trang_thai": "Đang học"}
        data.update(over)
        return data

    def count(self, sql, params=()):
        with self.app.app_context():
            return get_db().execute(sql, params).fetchone()[0]

    # ---- xác thực và phân quyền
    def test_anonymous_redirected_and_api_401(self):
        r = self.client.get("/students/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(self.client.get("/api/students").status_code, 401)

    def test_login_wrong_password(self):
        r = self.login("admin", "sai-mat-khau")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Sai tên đăng nhập", r.get_data(as_text=True))

    def test_post_without_csrf_rejected(self):
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": "admin123"}).status_code, 400)

    def test_student_permissions(self):
        self.login("SV660001", "123456")
        self.assertEqual(self.client.get("/students/").status_code, 403)
        self.assertEqual(self.client.get("/students/new").status_code, 403)
        me = self.client.get("/students/me", follow_redirects=True)
        self.assertEqual(me.status_code, 200)
        self.assertIn("SV660001", me.get_data(as_text=True))
        other = self.count("SELECT id FROM SinhVien WHERE ma_sv = 'SV660002'")
        self.assertEqual(self.client.get(f"/students/{other}").status_code, 403)
        self.assertEqual(self.post(f"/students/{other}/delete").status_code, 403)

    def test_staff_can_view_but_not_edit(self):
        self.login("staff", "staff123")
        self.assertEqual(self.client.get("/students/").status_code, 200)
        self.assertEqual(self.client.get("/students/new").status_code, 403)
        self.assertEqual(self.client.get("/catalog/nganh").status_code, 403)

    # ---- danh sách và tìm kiếm
    def test_list_and_search(self):
        self.login("admin", "admin123")
        html = self.client.get("/students/").get_data(as_text=True)
        self.assertIn("SV660001", html)
        self.assertIn("Tìm thấy 40 sinh viên", html)

        by_code = self.client.get("/students/?q=sv660001").get_data(as_text=True)
        self.assertIn("Tìm thấy 1 sinh viên", by_code)

        accent = self.client.get("/students/?q=nguyen").get_data(as_text=True)
        self.assertIn("Nguyễn", accent)

        by_class = self.client.get("/students/?q=KTPM66A").get_data(as_text=True)
        self.assertIn("KTPM66A", by_class)
        self.assertNotIn("CNTT66A</td>", by_class)

        self.assertIn("Không có sinh viên nào", self.client.get("/students/?q=zzzzzz").get_data(as_text=True))
        self.assertEqual(self.client.get("/students/?q=100%25_&page=abc").status_code, 200)

    def test_filters_and_pagination(self):
        self.login("admin", "admin123")
        self.assertIn("Tìm thấy 8 sinh viên", self.client.get("/students/?lop_id=1").get_data(as_text=True))
        self.assertIn("Tìm thấy 24 sinh viên", self.client.get("/students/?khoa_hoc=K66").get_data(as_text=True))
        self.assertIn("Tìm thấy 16 sinh viên", self.client.get("/students/?khoa_hoc=K67").get_data(as_text=True))
        page2 = self.client.get("/students/?page=2").get_data(as_text=True)
        self.assertIn("SV660017", page2)
        self.assertNotIn("SV660001<", page2)

    # ---- thêm / sửa / xóa
    def test_create_edit_delete_student(self):
        self.login("admin", "admin123")
        r = self.post("/students/new", self.student_form())
        self.assertEqual(r.status_code, 302)
        sv_id = self.count("SELECT id FROM SinhVien WHERE ma_sv = 'SV990001'")
        self.assertEqual(self.count("SELECT COUNT(*) FROM TaiKhoan WHERE username = 'SV990001'"), 1)

        dup = self.post("/students/new", self.student_form())
        self.assertEqual(dup.status_code, 200)
        self.assertIn("đã tồn tại", dup.get_data(as_text=True))

        bad = self.post("/students/new", self.student_form(ma_sv="SV990002", email="abc", so_dien_thoai="123", lop_id="999"))
        self.assertEqual(bad.status_code, 200)
        text = bad.get_data(as_text=True)
        self.assertIn("Email không hợp lệ", text)
        self.assertIn("Số điện thoại", text)
        self.assertIn("Vui lòng chọn lớp", text)

        r = self.post(f"/students/{sv_id}/edit", self.student_form(ma_sv="SV990009", ho_ten="Lê Thị Đã Sửa"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.count("SELECT COUNT(*) FROM TaiKhoan WHERE username = 'SV990009'"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM TaiKhoan WHERE username = 'SV990001'"), 0)

        r = self.post(f"/students/{sv_id}/delete")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.count("SELECT COUNT(*) FROM SinhVien WHERE id = ?", (sv_id,)), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM TaiKhoan WHERE sinh_vien_id = ?", (sv_id,)), 0)

    def test_new_student_can_login(self):
        self.login("admin", "admin123")
        self.post("/students/new", self.student_form())
        self.post("/logout")
        r = self.login("SV990001", "123456")
        self.assertEqual(r.status_code, 302)

    def test_not_found(self):
        self.login("admin", "admin123")
        self.assertEqual(self.client.get("/students/99999").status_code, 404)

    # ---- API
    def test_api(self):
        self.login("admin", "admin123")
        data = self.client.get("/api/students?per_page=5").get_json()
        self.assertEqual(data["total"], 40)
        self.assertEqual(len(data["items"]), 5)
        one = self.client.get(f"/api/students/{data['items'][0]['id']}").get_json()
        self.assertEqual(one["ma_sv"], data["items"][0]["ma_sv"])

    # ---- danh mục
    def test_catalog_crud_and_constraints(self):
        self.login("admin", "admin123")
        self.assertEqual(self.client.get("/catalog/nganh").status_code, 200)
        self.assertEqual(self.client.get("/catalog/lop").status_code, 200)

        self.post("/catalog/nganh/save", {"ma_nganh": "ATTT", "ten_nganh": "An toàn thông tin"})
        nganh_id = self.count("SELECT id FROM NganhHoc WHERE ma_nganh = 'ATTT'")
        self.post("/catalog/lop/save", {"ma_lop": "ATTT68A", "ten_lop": "ATTT 68A",
                                         "khoa_hoc": "K68", "nganh_id": str(nganh_id)})
        lop_id = self.count("SELECT id FROM Lop WHERE ma_lop = 'ATTT68A'")

        self.post(f"/catalog/nganh/{nganh_id}/delete")  # còn lớp -> không xóa được
        self.assertEqual(self.count("SELECT COUNT(*) FROM NganhHoc WHERE id = ?", (nganh_id,)), 1)

        self.post("/catalog/lop/save", {"id": str(lop_id), "ma_lop": "ATTT68B", "ten_lop": "ATTT 68B",
                                         "khoa_hoc": "K68", "nganh_id": str(nganh_id)})
        self.assertEqual(self.count("SELECT COUNT(*) FROM Lop WHERE ma_lop = 'ATTT68B'"), 1)

        self.post("/catalog/lop/1/delete")  # còn sinh viên -> không xóa được
        self.assertEqual(self.count("SELECT COUNT(*) FROM Lop WHERE id = 1"), 1)

        self.post(f"/catalog/lop/{lop_id}/delete")
        self.post(f"/catalog/nganh/{nganh_id}/delete")
        self.assertEqual(self.count("SELECT COUNT(*) FROM NganhHoc WHERE id = ?", (nganh_id,)), 0)


if __name__ == "__main__":
    unittest.main()
