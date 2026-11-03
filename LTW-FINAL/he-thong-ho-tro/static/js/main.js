// Giao diện mới: chỉ xử lý hành vi giao diện, không đụng tới logic nghiệp vụ.
(function () {
  // Mở / đóng menu trên điện thoại
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-nav-toggle]");
    if (t) { document.body.classList.toggle("nav-open"); return; }
    if (document.body.classList.contains("nav-open") && !e.target.closest(".sidebar")) {
      document.body.classList.remove("nav-open");
    }
    // Đóng thông báo
    var x = e.target.closest("[data-dismiss]");
    if (x) { x.closest(".flash").remove(); }
    // Mở hộp thoại: <button data-dialog="id">
    var d = e.target.closest("[data-dialog]");
    if (d) {
      var dlg = document.getElementById(d.getAttribute("data-dialog"));
      if (dlg) {
        // Điền dữ liệu vào form trong hộp thoại: data-fill='{"id":1,"ten":"..."}'
        var form = dlg.querySelector("form");
        var fill = d.getAttribute("data-fill");
        if (form) {
          form.reset();
          if (fill) {
            var obj = JSON.parse(fill);
            Object.keys(obj).forEach(function (k) {
              var el = form.elements[k];
              if (!el) return;
              if (el.type === "checkbox") el.checked = !!obj[k];
              else el.value = obj[k] == null ? "" : obj[k];
            });
          }
        }
        if (form && d.getAttribute("data-action")) form.action = d.getAttribute("data-action");
        var title = dlg.querySelector("[data-title]");
        if (title && d.getAttribute("data-title")) title.textContent = d.getAttribute("data-title");
        dlg.showModal();
      }
    }
    var c = e.target.closest("[data-close]");
    if (c) { c.closest("dialog").close(); }
  });

  // Xác nhận trước khi gửi form: <form data-confirm="Bạn chắc chứ?">
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Click nền hộp thoại để đóng
  document.querySelectorAll("dialog").forEach(function (dlg) {
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
  });

  // Tự gửi form lọc khi đổi ô chọn: <select data-autosubmit>
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });
})();
