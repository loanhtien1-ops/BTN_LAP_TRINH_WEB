// Nút chat nổi cho sinh viên: hỏi chatbot ngay trên mọi trang, không cần mở trang riêng.
(function () {
  var root = document.getElementById("cbw");
  if (!root) return;
  var askUrl = root.getAttribute("data-ask"), pageUrl = root.getAttribute("data-page");
  var fab = root.querySelector(".cbw-fab"), panel = root.querySelector(".cbw-panel"), log = root.querySelector(".cbw-log"),
      form = root.querySelector("form"), input = root.querySelector("input");

  function bubble(text, who) {
    var m = document.createElement("div"); m.className = "cbw-msg " + who;
    var b = document.createElement("div"); b.className = "cbw-bubble"; b.textContent = text;
    m.appendChild(b); log.appendChild(m); log.scrollTop = log.scrollHeight; return b;
  }
  function open(v) {
    panel.hidden = !v; fab.setAttribute("aria-expanded", v ? "true" : "false");
    if (v) { if (!log.children.length) bubble("Xin chào! Bạn muốn hỏi gì về học vụ, học phí, tài khoản hay kỹ thuật?", "bot"); setTimeout(function () { input.focus(); }, 50); }
  }
  fab.addEventListener("click", function () { open(panel.hidden); });
  root.querySelector(".cbw-close").addEventListener("click", function () { open(false); });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim(); if (!text) return;
    bubble(text, "me"); input.value = "";
    fetch(askUrl, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question: text})})
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var b = bubble(j.answer, "bot");
        if (j.ticket_url) {
          var a = document.createElement("a"); a.href = j.ticket_url; a.className = "cbw-help" + (j.handoff ? " strong" : ""); a.textContent = "Vẫn cần hỗ trợ →";
          b.appendChild(document.createElement("br")); b.appendChild(a);
        }
      })
      .catch(function () { bubble("Có lỗi kết nối, bạn thử lại sau nhé.", "bot"); });
  });
})();
