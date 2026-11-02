document.addEventListener("DOMContentLoaded", () => {
  // Hộp thoại xác nhận cho các form có thuộc tính data-confirm (xóa...)
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Bộ lọc tự gửi khi đổi lựa chọn; đổi ngành thì đặt lại ô lớp
  document.querySelectorAll("[data-autosubmit]").forEach((el) => {
    el.addEventListener("change", () => {
      if (el.dataset.resetTarget) {
        const target = document.querySelector(el.dataset.resetTarget);
        if (target) target.value = "";
      }
      el.form.submit();
    });
  });

  // Mã sinh viên luôn viết hoa khi nhập
  const maSv = document.getElementById("ma_sv");
  if (maSv) {
    maSv.addEventListener("input", () => {
      maSv.value = maSv.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    });
  }

  // Modal thêm/sửa ngành, lớp: điền sẵn dữ liệu từ nút bấm
  const modal = document.getElementById("catalogModal");
  if (modal) {
    modal.addEventListener("show.bs.modal", (event) => {
      const button = event.relatedTarget;
      const data = button && button.dataset.fill ? JSON.parse(button.dataset.fill) : {};
      const title = modal.querySelector("[data-modal-title]");
      if (title) title.textContent = (button && button.dataset.title) || "";
      modal.querySelectorAll("input[name], select[name]").forEach((el) => {
        if (el.name === "csrf_token") return;
        el.value = data[el.name] ?? "";
      });
    });
  }
});
