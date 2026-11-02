# Hệ thống quản lý sinh viên và hỗ trợ người học — Module M03

Phần của Tiến: **Quản lý sinh viên và quá trình theo học** (Flask + SQLite + Bootstrap).
Đã gồm luôn đăng nhập/phân quyền cơ bản để Thảo (M12) và Hà (M17) ghép vào.

## Chạy trong PyCharm

1. Mở thư mục `student_support_system` bằng PyCharm, tạo virtualenv (Python 3.9+).
2. Cài thư viện: `pip install -r requirements.txt`
3. Chạy file `app.py` (chuột phải → Run) rồi mở http://127.0.0.1:5000
4. Lần chạy đầu tiên hệ thống tự tạo CSDL `instance/student_support.db` và nạp dữ liệu mẫu (40 sinh viên, 4 ngành, 5 lớp).
   Muốn tạo lại từ đầu: chạy `seed.py`.

## Tài khoản mẫu

| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| Quản trị viên (`admin`) | `admin` | `admin123` |
| Nhân viên hỗ trợ (`support_staff`) | `staff` | `staff123` |
| Sinh viên (`student`) | mã sinh viên, ví dụ `SV660001` | `123456` |

## Chức năng M03

| Chức năng | admin | support_staff | student |
|---|---|---|---|
| Xem danh sách, tìm kiếm (mã, tên, lớp; không phân biệt dấu), lọc ngành/lớp/khóa/trạng thái, phân trang | ✔ | ✔ | ✘ |
| Xem chi tiết hồ sơ | ✔ | ✔ | chỉ hồ sơ của mình |
| Thêm, sửa, xóa sinh viên (thêm sinh viên tự tạo tài khoản, mật khẩu mặc định `123456`) | ✔ | ✘ | ✘ |
| Quản lý ngành học, lớp và khóa học (`/catalog/nganh`, `/catalog/lop`) | ✔ | ✘ | ✘ |

API JSON (dành cho dashboard của Hà): `GET /api/students?q=&nganh_id=&lop_id=&khoa_hoc=&trang_thai=&page=&per_page=` và `GET /api/students/<id>`.

## Cấu trúc

```
app.py          tạo ứng dụng, đăng ký blueprint, xử lý lỗi
models.py       kết nối SQLite + SCHEMA chung (NganhHoc, Lop, SinhVien, TaiKhoan)
auth.py         đăng nhập/đăng xuất, login_required, roles_required, CSRF
students.py     M03: sinh viên (trang web + API)
catalog.py      M03: ngành, lớp, khóa
seed.py         dữ liệu mẫu
templates/      base.html, login.html, students/, catalog/
static/         css/style.css, js/main.js
tests/          test_m03.py
```

## Ghép với M12 (Thảo) và M17 (Hà)

- **Bảng dùng chung**: thêm bảng `YeuCauHoTro`, `LoaiHoTro`, `PhanHoi` vào `SCHEMA` trong `models.py`.
  Khóa ngoại tới `SinhVien(id)` nên khai báo `ON DELETE CASCADE`, nếu không việc xóa sinh viên có yêu cầu hỗ trợ sẽ bị chặn
  (hệ thống đang báo lỗi thân thiện và gợi ý đổi trạng thái sang "Thôi học").
- **Đăng ký module**: bỏ comment dòng `register_blueprint(support_bp)` và `register_blueprint(dashboard_bp)` trong `app.py`.
- **Phân quyền**: dùng lại `from auth import login_required, roles_required`; người dùng hiện tại là `g.user`
  (có `vai_tro`, `sinh_vien_id`).
- **Menu**: thêm mục của module mình vào chỗ có ghi chú trong `templates/base.html`.
- **Hà**: có thể truy vấn trực tiếp bảng `SinhVien`, `Lop`, `NganhHoc` (JOIN theo `lop_id`, `nganh_id`) thay vì gọi API.

## Kiểm thử

```
python -m unittest discover -s tests -v
```

## Lưu ý khi nộp

- Đổi `SECRET_KEY` bằng biến môi trường `SECRET_KEY` nếu triển khai thật.
- Bootstrap tải từ CDN nên cần có Internet khi mở giao diện.
