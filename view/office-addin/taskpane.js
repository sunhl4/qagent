(function () {
  var marker = window.COMPANY_AGENT_ADDIN || { token: "", host: "wps" };
  var button = document.getElementById("review");
  if (!button) return;
  button.addEventListener("click", function () {
    if (marker.host === "wps") {
      var note = document.getElementById("note");
      if (note) note.textContent = "WPS 修订走回环 apply，不调用 Word 宿主接口。";
      return;
    }
    var note = document.getElementById("note");
    if (note) note.textContent = "当前宿主未接入。";
  });
})();
