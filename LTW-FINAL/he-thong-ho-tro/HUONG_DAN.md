# Hệ thống hỗ trợ người học — bản đầy đủ (giao diện mới + chatbot FAQ + gửi ẩn danh)

## Chạy
1. Giải nén, mở thư mục `he-thong-ho-tro` bằng PyCharm.
2. `pip install -r requirements.txt`
3. Chạy `app.py`, mở http://127.0.0.1:5001  (cổng 5001)
4. Lần đầu hệ thống tự tạo CSDL `instance/student_support.db`, nạp dữ liệu mẫu và vài FAQ mẫu.
   CSDL cũ tự được nâng cấp (thêm cột ẩn danh), không mất dữ liệu.

## Tài khoản mẫu
| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| Quản trị viên | admin | admin123 |
| Nhân viên hỗ trợ | staff | staff123 |
| Sinh viên | SV660001 | 123456 |

## Phần mới
- Giao diện mới (templates/, static/) cho mọi trang.
- Sinh viên: /chatbot/ (hỏi chatbot, nút "Vẫn cần hỗ trợ" mở form gửi yêu cầu điền sẵn), /chatbot/faq (xem FAQ).
- Nhân viên/admin: /chatbot/manage (tạo, sửa FAQ; admin duyệt, ẩn, xóa; danh sách câu chatbot chưa trả lời được).
- Gửi ẩn danh: sinh viên tick "Gửi ẩn danh" ở /support/new; nhân viên/admin không thấy tên, mã, lớp.
- Đã sửa lỗi trong chatbot.tim_faq_phu_hop (trước đây chỉ xét FAQ cuối cùng).

## Kiểm thử
python kiem_thu.py
