/**
 * Shared header profile dropdown behavior.
 * Call initHeaderDropdown() after DOM ready on pages that have #headerProfileBtn and #headerDropdown.
 */
(function () {
  function initHeaderDropdown() {
    var btn = document.getElementById("headerProfileBtn");
    var dropdown = document.getElementById("headerDropdown");
    if (!btn || !dropdown) return;

    function open() {
      dropdown.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
    }
    function close() {
      dropdown.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
    }
    function toggle() {
      if (dropdown.classList.contains("is-open")) close();
      else open();
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggle();
    });

    document.addEventListener("click", function (e) {
      if (!btn.contains(e.target) && !dropdown.contains(e.target)) close();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHeaderDropdown);
  } else {
    initHeaderDropdown();
  }
})();
