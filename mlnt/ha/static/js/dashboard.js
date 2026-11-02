/* M17 - Dashboard: gọi API thống kê rồi vẽ biểu đồ bằng Chart.js. */
(function () {
  "use strict";

  var root = document.getElementById("dash");
  if (!root || typeof Chart === "undefined") {
    var err = document.getElementById("dash-error");
    if (err) { err.textContent = "Không tải được thư viện biểu đồ. Hãy kiểm tra kết nối Internet rồi tải lại trang."; err.classList.remove("d-none"); }
    return;
  }

  var MAU_TRANG_THAI = { cho_xu_ly: "#f0a500", dang_xu_ly: "#1976d2", da_giai_quyet: "#2e7d32" };
  var TEN_TRANG_THAI = { cho_xu_ly: "Chờ xử lý", dang_xu_ly: "Đang xử lý", da_giai_quyet: "Đã giải quyết" };
  var MAU_CHINH = "#0d47a1";
  var MAU_PHU = ["#0d47a1", "#1976d2", "#64b5f6", "#90a4ae", "#f0a500", "#2e7d32"];
  var so = new Intl.NumberFormat("vi-VN");
  var charts = {};
  var chiTieu = JSON.parse(document.getElementById("chi-tieu-data").textContent);
  var dsLoc = null;       // bộ lọc của danh sách truy xuất đang mở (trạng thái, loại, quá hạn)
  var dsTrang = 1;

  function $(id) { return document.getElementById(id); }
  function gio(v) { return v === null || v === undefined ? "—" : so.format(v) + " giờ"; }
  function phanTram(v) { return v === null || v === undefined ? "—" : so.format(v) + "%"; }

  function ve(id, config) {
    if (charts[id]) { charts[id].destroy(); }
    charts[id] = new Chart($(id), config);
  }

  function baoLoi(message) {
    var box = $("dash-error");
    box.textContent = message;
    box.classList.toggle("d-none", !message);
  }

  function layParams() {
    var p = new URLSearchParams();
    ["tu_ngay", "den_ngay", "nganh_id", "lop_id"].forEach(function (k) {
      var v = $(k).value;
      if (v) { p.set(k, v); }
    });
    return p;
  }

  function layJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) {
        var type = res.headers.get("content-type") || "";
        if (type.indexOf("application/json") === -1) {
          throw new Error("Bạn không có quyền xem số liệu này hoặc phiên đăng nhập đã hết hạn.");
        }
        return res.json().then(function (data) {
          if (!res.ok) { throw new Error(data.error || "Không lấy được số liệu."); }
          return data;
        });
      });
  }

  function dinhDangNgayGio(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(s || "");
    return m ? m[3] + "/" + m[2] + "/" + m[1] + " " + m[4] + ":" + m[5] : "";
  }

  function dinhDangNgay(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    return m ? m[3] + "/" + m[2] + "/" + m[1] : "";
  }

  function vanBanKhoang(pv) {
    var parts = [];
    if (pv.tu_ngay || pv.den_ngay) {
      parts.push("ngày tạo từ " + (dinhDangNgay(pv.tu_ngay) || "đầu") + " đến " + (dinhDangNgay(pv.den_ngay) || "nay"));
    } else {
      parts.push("tất cả thời gian");
    }
    var nganh = $("nganh_id"), lop = $("lop_id");
    if (pv.nganh_id) { parts.push("ngành " + nganh.options[nganh.selectedIndex].text); }
    if (pv.lop_id) { parts.push("lớp " + lop.options[lop.selectedIndex].text); }
    return parts.join(", ");
  }

  function dong(tbody, cells, canPhai) {
    var tr = document.createElement("tr");
    cells.forEach(function (text, i) {
      var td = document.createElement("td");
      td.textContent = text;
      if (canPhai && canPhai.indexOf(i) !== -1) { td.className = "text-end"; }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }

  // ------------------------------------------------------------ danh sách truy xuất
  function nhanBoLoc(loc) {
    var parts = [];
    if (loc.trang_thai) { parts.push(TEN_TRANG_THAI[loc.trang_thai]); }
    if (loc.loai) { parts.push("loại: " + loc.loaiTen); }
    if (loc.qua_han) { parts.push("quá hạn"); }
    return parts.length ? parts.join(", ") : "tất cả yêu cầu";
  }

  function taiDanhSach() {
    if (!dsLoc) { return; }
    var p = layParams();
    if (dsLoc.trang_thai) { p.set("trang_thai", dsLoc.trang_thai); }
    if (dsLoc.loai) { p.set("loai", dsLoc.loai); }
    if (dsLoc.qua_han) { p.set("qua_han", "1"); }
    p.set("page", dsTrang);
    layJson(root.dataset.apiChiTiet + "?" + p.toString()).then(function (d) {
      $("panel-ds").classList.remove("d-none");
      $("ds-tieu-de").textContent = "Danh sách yêu cầu: " + nhanBoLoc(dsLoc) + " (" + so.format(d.tong) + ")";
      var body = $("ds-body");
      body.textContent = "";
      if (!d.muc.length) { dong(body, ["Không có yêu cầu nào khớp bộ lọc."]); }
      d.muc.forEach(function (m) {
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        var a = document.createElement("a");
        a.href = m.url; a.textContent = "#" + m.id;
        td.appendChild(a); tr.appendChild(td);
        [m.loai, m.ten_trang_thai, m.uu_tien, m.lop, dinhDangNgayGio(m.ngay_tao),
         m.gio_giai_quyet === null ? "—" : gio(m.gio_giai_quyet)].forEach(function (text) {
          var c = document.createElement("td"); c.textContent = text; tr.appendChild(c);
        });
        body.appendChild(tr);
      });
      dsTrang = d.trang;
      $("ds-trang").textContent = "Trang " + d.trang + " / " + d.so_trang;
      $("ds-truoc").disabled = d.trang <= 1;
      $("ds-sau").disabled = d.trang >= d.so_trang;
    }).catch(function (e) { baoLoi(e.message); });
  }

  function moDanhSach(loc) {
    dsLoc = loc; dsTrang = 1;
    taiDanhSach();
    $("panel-ds").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ------------------------------------------------------------ phần hỗ trợ
  function veHoTro(d) {
    $("so-tong").textContent = so.format(d.tong);
    $("so-cho").textContent = so.format(d.theo_trang_thai.cho_xu_ly);
    $("so-tyle").textContent = phanTram(d.ty_le_giai_quyet);
    $("so-quahan").textContent = so.format(d.qua_han);
    var sv = d.sinh_vien_gui_yeu_cau;
    $("so-svgui").textContent = so.format(sv.da_gui);
    $("so-svgui-ct").textContent = "trên " + so.format(sv.tong_sinh_vien) + " sinh viên" + (sv.ty_le === null ? "" : " (" + phanTram(sv.ty_le) + ")");

    var tg = d.thoi_gian;
    $("tg-tiepnhan").textContent = gio(tg.tiep_nhan_tb_gio);
    $("tg-giaiquyet").textContent = gio(tg.giai_quyet_tb_gio);
    $("tg-khoang").textContent = tg.nhanh_nhat_gio === null ? "—" : gio(tg.nhanh_nhat_gio) + " / " + gio(tg.cham_nhat_gio);
    $("tg-dunghan").textContent = phanTram(tg.ty_le_dung_han);

    $("dash-meta").textContent = "Phạm vi tính: " + vanBanKhoang(d.pham_vi) + ". Cập nhật lúc " +
      dinhDangNgayGio(d.thoi_diem_tinh) + ". Nguồn: " + d.nguon.join(", ") + ".";

    var trong = d.tong === 0;
    $("dash-trong").classList.toggle("d-none", !trong);
    $("dash-charts").classList.toggle("d-none", trong);
    if (trong) { return; }

    var keys = Object.keys(d.theo_trang_thai);
    ve("ch-trang-thai", {
      type: "doughnut",
      data: {
        labels: keys.map(function (k) { return TEN_TRANG_THAI[k]; }),
        datasets: [{ data: keys.map(function (k) { return d.theo_trang_thai[k]; }),
                     backgroundColor: keys.map(function (k) { return MAU_TRANG_THAI[k]; }) }]
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        onHover: function (e, els) { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
        onClick: function (e, els) { if (els.length) { moDanhSach({ trang_thai: keys[els[0].index] }); } }
      }
    });

    ve("ch-loai", {
      type: "bar",
      data: {
        labels: d.theo_loai.map(function (x) { return x.ten; }),
        datasets: [{ label: "Số yêu cầu", data: d.theo_loai.map(function (x) { return x.so; }), backgroundColor: MAU_CHINH }]
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        onHover: function (e, els) { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
        onClick: function (e, els) {
          if (els.length) {
            var x = d.theo_loai[els[0].index];
            moDanhSach({ loai: x.id, loaiTen: x.ten });
          }
        }
      }
    });

    ve("ch-thang", {
      type: "line",
      data: {
        labels: d.theo_thang.map(function (x) { var p = x.thang.split("-"); return p[1] + "/" + p[0]; }),
        datasets: [
          { label: "Số yêu cầu", data: d.theo_thang.map(function (x) { return x.so; }), yAxisID: "y",
            borderColor: MAU_CHINH, backgroundColor: MAU_CHINH, tension: 0.25, pointRadius: 4 },
          { label: "Giờ giải quyết TB", data: d.theo_thang.map(function (x) { return x.gio_giai_quyet_tb; }), yAxisID: "y1",
            borderColor: "#f0a500", backgroundColor: "#f0a500", borderDash: [6, 4], tension: 0.25, pointRadius: 3, spanGaps: true }
        ]
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Yêu cầu" } },
          y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Giờ" } }
        }
      }
    });

    veCotNgang("ch-gio-loai", d.thoi_gian.theo_loai.map(function (x) { return { ten: x.ten, so: x.gio }; }), "Giờ");
    veCotNgang("ch-yc-nganh", d.theo_nganh, "Yêu cầu");
    veCotNgang("ch-yc-lop", d.theo_lop, "Yêu cầu");
  }

  function veCotNgang(id, items, nhan) {
    ve(id, {
      type: "bar",
      data: {
        labels: items.map(function (x) { return x.ma || x.ten; }),
        datasets: [{ label: nhan, data: items.map(function (x) { return x.so; }), backgroundColor: MAU_CHINH }]
      },
      options: {
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: { legend: { display: false },
                   tooltip: { callbacks: { title: function (c) { return items[c[0].dataIndex].ten; } } } },
        scales: { x: { beginAtZero: true } }
      }
    });
  }

  // ------------------------------------------------------------ phần sinh viên (admin)
  function veCot(id, items, ngang) {
    ve(id, {
      type: "bar",
      data: {
        labels: items.map(function (x) { return x.ma || x.ten; }),
        datasets: [{ label: "Sinh viên", data: items.map(function (x) { return x.so; }), backgroundColor: MAU_CHINH }]
      },
      options: {
        maintainAspectRatio: false,
        indexAxis: ngang ? "y" : "x",
        plugins: { legend: { display: false },
                   tooltip: { callbacks: { title: function (c) { return items[c[0].dataIndex].ten; } } } },
        scales: { [ngang ? "x" : "y"]: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  }

  function veSinhVien(d) {
    $("sv-tong").textContent = so.format(d.tong);
    $("sv-meta").textContent = "Phạm vi tính: " + d.pham_vi.tinh_theo + ". Cập nhật lúc " +
      dinhDangNgayGio(d.thoi_diem_tinh) + ". Nguồn: " + d.nguon.join(", ") + ".";
    ve("ch-sv-hoc", {
      type: "doughnut",
      data: {
        labels: d.theo_trang_thai_hoc.map(function (x) { return x.ten; }),
        datasets: [{ data: d.theo_trang_thai_hoc.map(function (x) { return x.so; }), backgroundColor: MAU_PHU }]
      },
      options: { maintainAspectRatio: false, plugins: { legend: { position: "right", labels: { boxWidth: 12 } } } }
    });
    veCot("ch-sv-lop", d.theo_lop, false);
    veCot("ch-sv-nganh", d.theo_nganh, true);
    veCot("ch-sv-khoa", d.theo_khoa, false);
  }

  // ------------------------------------------------------------ thống kê hệ thống (admin)
  function veHeThong(d) {
    $("ht-meta").textContent = "Phạm vi tính: " + d.pham_vi.ghi_chu_pham_vi + " Cập nhật lúc " +
      dinhDangNgayGio(d.thoi_diem_tinh) + ". Nguồn: " + d.nguon.join(", ") + ".";
    var tk = $("ht-taikhoan"); tk.textContent = "";
    d.tai_khoan_theo_vai_tro.forEach(function (x) { dong(tk, [x.ten, so.format(x.so)], [1]); });
    var ph = $("ht-phanhoi"); ph.textContent = "";
    dong(ph, ["Phản hồi gửi sinh viên", so.format(d.phan_hoi.cong_khai)], [1]);
    dong(ph, ["Ghi chú nội bộ", so.format(d.phan_hoi.noi_bo)], [1]);
    dong(ph, ["Tổng phản hồi", so.format(d.phan_hoi.tong)], [1]);
    dong(ph, ["Lần đổi trạng thái đã ghi", so.format(d.so_lan_doi_trang_thai)], [1]);
    var nv = $("ht-nhanvien"); nv.textContent = "";
    d.yeu_cau_theo_nhan_vien.forEach(function (x) { dong(nv, [x.ten, so.format(x.so), so.format(x.da_giai_quyet)], [1, 2]); });
  }

  // ------------------------------------------------------------ tải dữ liệu
  function taiDuLieu() {
    baoLoi("");
    var qs = layParams().toString();
    var q = qs ? "?" + qs : "";
    layJson(root.dataset.apiHoTro + q).then(veHoTro).catch(function (e) { baoLoi(e.message); });
    if (root.dataset.apiSinhVien) {
      layJson(root.dataset.apiSinhVien + q).then(veSinhVien).catch(function (e) { baoLoi(e.message); });
      layJson(root.dataset.apiHeThong + q).then(veHeThong).catch(function (e) { baoLoi(e.message); });
    }
    if (dsLoc) { dsTrang = 1; taiDanhSach(); }
  }

  // ------------------------------------------------------------ nguồn và công thức
  function moNguon(ma) {
    var c = chiTieu.filter(function (x) { return x.ma === ma; })[0];
    if (!c) { return; }
    $("modal-nguon-title").textContent = c.ma + ": " + c.ten;
    var body = $("modal-nguon-body");
    body.textContent = "";
    [["Công thức", c.cong_thuc], ["Đơn vị tính", c.don_vi], ["Chiều phân tích", c.chieu_phan_tich || "—"],
     ["Nguồn dữ liệu", c.nguon], ["Đầu mối dữ liệu", c.dau_moi],
     ["Phiên bản", c.phien_ban + " (" + c.ten_trang_thai + ")"],
     ["Lưu ý", "Chỉ số nội bộ, không đồng nhất với HEDI. Số trên trang này tính trực tiếp từ dữ liệu hiện có."]].forEach(function (row) {
      var dt = document.createElement("dt"); dt.textContent = row[0];
      var dd = document.createElement("dd"); dd.textContent = row[1];
      body.appendChild(dt); body.appendChild(dd);
    });
    $("modal-nguon-link").href = root.dataset.apiHoTro.replace("/api/ho-tro", "/chi-tieu/") + encodeURIComponent(c.ma);
    bootstrap.Modal.getOrCreateInstance($("modal-nguon")).show();
  }

  // ------------------------------------------------------------ lọc ngành và lớp
  function locLopTheoNganh() {
    var nganh = $("nganh_id").value, lop = $("lop_id");
    Array.prototype.forEach.call(lop.options, function (o) {
      var an = nganh && o.value && o.dataset.nganh !== nganh;
      o.hidden = an; o.disabled = an;
    });
    if (lop.selectedOptions[0] && lop.selectedOptions[0].disabled) { lop.value = ""; }
  }

  document.querySelectorAll(".btn-nguon").forEach(function (btn) {
    btn.addEventListener("click", function () { moNguon(btn.dataset.ma); });
  });
  document.querySelectorAll(".btn-ds").forEach(function (btn) {
    btn.addEventListener("click", function () { moDanhSach(JSON.parse(btn.dataset.loc)); });
  });
  $("ds-dong").addEventListener("click", function () { dsLoc = null; $("panel-ds").classList.add("d-none"); });
  $("ds-truoc").addEventListener("click", function () { dsTrang -= 1; taiDanhSach(); });
  $("ds-sau").addEventListener("click", function () { dsTrang += 1; taiDanhSach(); });
  $("nganh_id").addEventListener("change", locLopTheoNganh);
  $("loc-form").addEventListener("submit", function (e) { e.preventDefault(); taiDuLieu(); });
  $("btn-reset").addEventListener("click", function () {
    ["tu_ngay", "den_ngay", "nganh_id", "lop_id"].forEach(function (k) { $(k).value = ""; });
    locLopTheoNganh();
    taiDuLieu();
  });

  taiDuLieu();
})();
