"""Kiểm thử toàn bộ: mọi trang theo vai trò, chatbot + duyệt FAQ, gửi ẩn danh, nâng cấp CSDL cũ."""
import os, re, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app
from models import connect, _them_cot_an_danh

bad = 0
def check(cond, msg):
    global bad
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond: bad += 1

path = os.path.join(tempfile.mkdtemp(), "t.db")
app = create_app({"DATABASE": path, "TESTING": True, "PROPAGATE_EXCEPTIONS": True})
conn = connect(path)
sv = conn.execute("SELECT sv.ho_ten, sv.ma_sv, l.ma_lop FROM SinhVien sv JOIN Lop l ON l.id = sv.lop_id WHERE sv.ma_sv='SV660001'").fetchone()
HO_TEN, MA_SV, MA_LOP = sv["ho_ten"], sv["ma_sv"], sv["ma_lop"]
conn.close()

def login(c, u, p):
    c.get("/auth/logout"); r = c.post("/auth/login", data={"username": u, "password": p}); assert r.status_code == 302

def ids(c, url, pat):
    return [int(x) for x in re.findall(pat, c.get(url).get_data(as_text=True))]

with app.test_client() as c:
    # ---------- trang chung theo vai trò
    check(c.get("/auth/login").status_code == 200, "trang đăng nhập")
    check(c.get("/chatbot/").status_code == 302 and c.get("/chatbot/faq").status_code == 302, "chưa đăng nhập: chatbot/FAQ chuyển về đăng nhập")
    login(c, "admin", "admin123")
    for u in ["/students/", "/students/1", "/students/new", "/students/1/edit", "/catalog/nganh", "/catalog/lop", "/support/manage",
              "/support/1", "/dashboard/", "/dashboard/chi-tieu", "/dashboard/chi-tieu/HT01", "/dashboard/pham-vi", "/portal/change-password",
              "/dashboard/api/ho-tro", "/dashboard/api/sinh-vien", "/dashboard/api/he-thong", "/chatbot/manage", "/chatbot/faq"]:
        check(c.get(u).status_code == 200, f"[admin] GET {u}")
    check(c.get("/chatbot/").status_code == 302, "[admin] không vào được trang chat của sinh viên")
    login(c, "staff", "staff123")
    for u in ["/students/", "/support/manage", "/support/3", "/dashboard/", "/chatbot/manage", "/chatbot/faq"]:
        check(c.get(u).status_code == 200, f"[staff] GET {u}")
    check(c.post("/chatbot/approve/1").status_code == 302, "[staff] không duyệt được FAQ (bị chuyển hướng)")

    # ---------- chatbot (sinh viên)
    login(c, MA_SV, "123456")
    for u in ["/chatbot/", "/chatbot/faq", "/portal/profile", "/portal/curriculum", "/portal/finance", "/support/my", "/support/new"]:
        check(c.get(u).status_code == 200, f"[sinh viên] GET {u}")
    ask = lambda q: c.post("/chatbot/ask", json={"question": q}).get_json()
    j = ask("Tôi quên mật khẩu rồi")
    check(not j["handoff"] and "Đổi mật khẩu" in j["answer"], "chatbot trả lời đúng FAQ 'quên mật khẩu'")
    j = ask("xin gia hạn học phí thế nào")
    check(not j["handoff"] and "yêu cầu hỗ trợ loại Học phí" in j["answer"], "chatbot khớp FAQ ở giữa danh sách (đã sửa lỗi chỉ xét FAQ cuối)")
    j = ask("làm sao xác nhận bảng điểm")
    check(not j["handoff"] and "Học vụ" in j["answer"], "chatbot khớp FAQ 'bảng điểm'")
    j = ask("Em muốn bảo lưu")
    check(j["handoff"] and "nhân viên hỗ trợ trực tiếp" in j["answer"], "FAQ bắt buộc chuyển nhân viên -> handoff")
    j = ask("hôm nay ăn gì, liên hệ abc@gmail.com hoặc 0912345678")
    check(j["handoff"] and "chưa tìm thấy" in j["answer"] and "/support/new?" in j["ticket_url"], "câu lạ -> handoff + đường dẫn Vẫn cần hỗ trợ")
    check(ask("")["answer"].startswith("Bạn vui lòng nhập"), "câu rỗng được nhắc nhập")
    check("quá dài" in ask("a" * 1001)["answer"], "câu quá dài bị từ chối")
    page = c.get(j["ticket_url"]).get_data(as_text=True)
    check("hôm nay ăn gì" in page, "form gửi yêu cầu được điền sẵn câu hỏi từ chatbot")
    conn = connect(path)
    log = conn.execute("SELECT cau_hoi FROM ChatLog WHERE cau_hoi LIKE 'hôm nay%'").fetchone()[0]
    check("[EMAIL]" in log and "[SO_DIEN_THOAI]" in log and "abc@gmail.com" not in log, "nhật ký che email và số điện thoại")
    conn.close()
    check("quên mật khẩu" in c.get("/chatbot/faq?q=mat+khau").get_data(as_text=True), "trang FAQ tìm không dấu")
    check("bảo lưu" not in c.get("/chatbot/faq").get_data(as_text=True).lower().split("<main")[1].split("</main>")[0].replace("tư vấn", ""), "FAQ chuyển-nhân-viên không hiện ở danh sách sinh viên")
    check(c.post("/chatbot/create", data={}).status_code == 302 and c.get("/chatbot/manage").status_code == 302, "sinh viên không vào được quản lý FAQ")

    # ---------- quy trình duyệt FAQ
    login(c, "staff", "staff123")
    r = c.post("/chatbot/create", data={"cau_hoi": "Học bổng nộp hồ sơ khi nào?", "cau_tra_loi": "Trước ngày 15 hàng tháng.", "tu_khoa": "học bổng, hồ sơ học bổng"})
    check(r.status_code == 302, "[staff] tạo FAQ")
    check("Học bổng nộp hồ sơ" in c.get("/chatbot/manage").get_data(as_text=True) and "Chờ duyệt" in c.get("/chatbot/manage").get_data(as_text=True), "FAQ mới ở trạng thái chờ duyệt")
    faq_id = ids(c, "/chatbot/manage", r"/chatbot/update/(\d+)")[0]
    check("Chờ duyệt" in c.get("/chatbot/manage").get_data(as_text=True), "danh sách quản lý đưa FAQ chờ duyệt lên đầu")
    check(c.post("/chatbot/create", data={"cau_hoi": "", "cau_tra_loi": "x", "tu_khoa": "y"}).status_code == 302, "[staff] FAQ thiếu thông tin bị từ chối")
    login(c, MA_SV, "123456")
    check(ask("khi nào nộp hồ sơ học bổng")["handoff"], "FAQ chờ duyệt CHƯA được chatbot dùng")
    login(c, "admin", "admin123")
    check(c.post(f"/chatbot/approve/{faq_id}").status_code == 302, "[admin] duyệt FAQ")
    login(c, MA_SV, "123456")
    j = ask("khi nào nộp hồ sơ học bổng"); check(not j["handoff"] and "15 hàng tháng" in j["answer"], "sau khi duyệt chatbot dùng được FAQ")
    login(c, "staff", "staff123")
    c.post(f"/chatbot/update/{faq_id}", data={"cau_hoi": "Học bổng nộp hồ sơ khi nào ạ?", "cau_tra_loi": "Trước ngày 20.", "tu_khoa": "học bổng"})
    login(c, MA_SV, "123456")
    check(ask("khi nào nộp hồ sơ học bổng")["handoff"], "[staff] sửa FAQ -> quay về chờ duyệt, chatbot ngừng dùng")
    login(c, "admin", "admin123")
    c.post("/chatbot/create", data={"cau_hoi": "Thư viện mở cửa mấy giờ?", "cau_tra_loi": "7h đến 21h.", "tu_khoa": "thư viện, giờ mở cửa"})
    login(c, MA_SV, "123456")
    check("7h đến 21h" in ask("thư viện mở cửa giờ nào")["answer"], "[admin] tạo FAQ được duyệt luôn")
    login(c, "admin", "admin123")
    lib_id = max(ids(c, "/chatbot/manage", r"/chatbot/update/(\d+)"))
    check(c.post(f"/chatbot/unapprove/{lib_id}").status_code == 302, "[admin] ẩn FAQ")
    login(c, MA_SV, "123456")
    check(ask("thư viện mở cửa giờ nào")["handoff"], "FAQ đã ẩn không còn được chatbot dùng")
    login(c, "admin", "admin123")
    c.post(f"/chatbot/approve/{lib_id}"); login(c, MA_SV, "123456"); ask("thư viện mở cửa giờ nào")  # tạo ChatLog tham chiếu FAQ
    login(c, "admin", "admin123")
    check(c.post(f"/chatbot/delete/{lib_id}").status_code == 302, "[admin] xóa FAQ đã có nhật ký tham chiếu không lỗi")
    check(c.post("/chatbot/delete/99999").status_code == 404, "xóa FAQ không tồn tại -> 404")
    check("hôm nay ăn gì" in c.get("/chatbot/manage").get_data(as_text=True), "quản lý hiện câu chatbot chưa trả lời được")

    # ---------- gửi ẩn danh
    login(c, MA_SV, "123456")
    page = c.get("/support/new").get_data(as_text=True)
    check('name="an_danh"' in page and "hỏi chatbot" in page, "form gửi có ô 'Gửi ẩn danh' và nhắc hỏi chatbot")
    r = c.post("/support/new", data={"loai_ho_tro_id": "5", "tieu_de": "Câu hỏi tế nhị về hỗ trợ tâm lý", "noi_dung": "Nội dung đủ dài để hợp lệ nhé.", "an_danh": "1"})
    yc = int(r.headers["Location"].rstrip("/").split("/")[-1])
    r2 = c.post("/support/new", data={"loai_ho_tro_id": "1", "tieu_de": "Yêu cầu thường", "noi_dung": "Nội dung đủ dài để hợp lệ nhé."})
    thuong = int(r2.headers["Location"].rstrip("/").split("/")[-1])
    t = c.get(f"/support/{yc}").get_data(as_text=True)
    check("Bạn đã gửi yêu cầu này" in t and HO_TEN in t, "sinh viên vẫn thấy yêu cầu ẩn danh của mình")
    c.post(f"/support/{yc}/reply", data={"noi_dung": "Em hỏi thêm một ý ạ."})
    for user, pw in (("staff", "staff123"), ("admin", "admin123")):
        login(c, user, pw)
        if user == "staff": c.post(f"/support/{yc}/reply", data={"noi_dung": "Nhà trường đã nhận."})
        t = c.get(f"/support/{yc}").get_data(as_text=True)
        check(HO_TEN not in t and MA_SV not in t and MA_LOP not in t and "Sinh viên ẩn danh" in t, f"[{user}] chi tiết ẩn danh không lộ tên/mã/lớp (cả phản hồi, lịch sử)")
        check("Câu hỏi tế nhị" not in c.get("/support/manage?q=" + MA_SV).get_data(as_text=True), f"[{user}] tìm theo mã không ra yêu cầu ẩn danh")
        check("Câu hỏi tế nhị" not in c.get("/support/manage?q=" + HO_TEN.split()[-1]).get_data(as_text=True), f"[{user}] tìm theo tên không ra yêu cầu ẩn danh")
        m = c.get("/support/manage?q=te+nhi").get_data(as_text=True)
        check("Câu hỏi tế nhị" in m and "Ẩn danh" in m, f"[{user}] vẫn tìm theo tiêu đề, hiện nhãn Ẩn danh")
        t2 = c.get(f"/support/{thuong}").get_data(as_text=True)
        check(HO_TEN in t2 and MA_SV in t2, f"[{user}] yêu cầu thường vẫn hiện đầy đủ")
        check(HO_TEN not in c.get("/dashboard/api/chi-tiet").get_data(as_text=True), f"[{user}] API dashboard không lộ tên")
    login(c, "staff", "staff123")
    check(c.post(f"/support/{yc}/status", data={"trang_thai": "da_giai_quyet"}).status_code == 302, "nhân viên đổi trạng thái yêu cầu ẩn danh được")
    t = c.get(f"/support/{thuong}").get_data(as_text=True)
    check("Đề xuất FAQ" in t, "trang chi tiết có nút Đề xuất FAQ cho nhân viên")
    login(c, MA_SV, "123456")
    check("Nhà trường đã nhận." in c.get(f"/support/{yc}").get_data(as_text=True), "sinh viên nhận phản hồi cho yêu cầu ẩn danh")
    check(c.get("/students/9999").status_code == 404 and c.get("/students/1").status_code in (200, 403), "phân quyền hồ sơ sinh viên còn hoạt động")

# ---------- nâng cấp CSDL cũ
old = os.path.join(tempfile.mkdtemp(), "old.db"); db = sqlite3.connect(old); db.row_factory = sqlite3.Row
db.executescript("CREATE TABLE YeuCauHoTro (id INTEGER PRIMARY KEY, sinh_vien_id INT, loai_ho_tro_id INT, tieu_de TEXT, noi_dung TEXT);"
                 "INSERT INTO YeuCauHoTro VALUES (1,1,1,'cũ','dữ liệu cũ');")
_them_cot_an_danh(db)
row = db.execute("SELECT tieu_de, la_an_danh FROM YeuCauHoTro").fetchone()
check(row["tieu_de"] == "cũ" and row["la_an_danh"] == 0, "CSDL cũ được thêm cột la_an_danh, dữ liệu cũ giữ nguyên")

# --- nút chatbot nổi: chỉ hiện cho sinh viên
with app.test_client() as c:
    def co_nut(u, pw, url):
        login(c, u, pw); return 'id="cbw"' in c.get(url).get_data(as_text=True)
    check(co_nut("SV660001", "123456", "/portal/profile"), "sinh viên thấy nút chatbot nổi ở trang hồ sơ")
    check(co_nut("SV660001", "123456", "/support/my"), "sinh viên thấy nút chatbot nổi ở trang yêu cầu")
    check(not co_nut("SV660001", "123456", "/chatbot/"), "trang chatbot không lặp nút nổi")
    check(not co_nut("staff", "staff123", "/students/"), "nhân viên không có nút chatbot nổi")
    check(not co_nut("admin", "admin123", "/dashboard/"), "admin không có nút chatbot nổi")

print("\nTổng lỗi:", bad); sys.exit(1 if bad else 0)
