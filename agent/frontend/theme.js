(function () {
  "use strict";

  var STORAGE_KEY = "notebooklm:theme";

  function selectedTheme() {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  }

  function updateButton(theme) {
    var button = document.getElementById("marketThemeToggle");
    if (!button) return;
    var isDark = theme === "dark";
    var label = isDark ? "切换浅色模式" : "切换深色模式";
    button.innerHTML = isDark ? '<i class="fa-solid fa-sun" aria-hidden="true"></i>' : '<i class="fa-solid fa-moon" aria-hidden="true"></i>';
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", String(isDark));
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
    if (document.body) document.body.dataset.theme = document.documentElement.dataset.theme;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === "dark" ? "#0d1524" : "#0b57d0";
    updateButton(theme);
  }

  // Apply before CSS paints to avoid a light flash when the saved theme is dark.
  apply(selectedTheme());
  document.addEventListener("DOMContentLoaded", function () {
    apply(selectedTheme());
    var button = document.getElementById("marketThemeToggle");
    if (!button) return;
    button.addEventListener("click", function () {
      var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      apply(next);
    });
  });
})();
