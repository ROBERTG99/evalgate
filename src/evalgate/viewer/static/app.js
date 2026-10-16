// Progressive enhancement only: every page works without this file.
(function () {
  "use strict";
  var root = document.documentElement;
  try {
    var saved = window.localStorage.getItem("evalgate-theme");
    if (saved === "light" || saved === "dark") { root.setAttribute("data-theme", saved); }
  } catch (e) { /* storage unavailable */ }
  document.addEventListener("DOMContentLoaded", function () {
    // Loading pages: reload until the result is ready (a meta refresh would fail WCAG 2.2.1).
    var refresh = document.querySelector("[data-auto-refresh]");
    if (refresh) {
      window.setTimeout(function () { window.location.reload(); }, Number(refresh.getAttribute("data-auto-refresh")));
    }
    var button = document.querySelector("[data-theme-toggle]");
    if (!button) { return; }
    var current = function () {
      var t = root.getAttribute("data-theme");
      if (t) { return t; }
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    };
    var label = function () { button.textContent = current() === "dark" ? "Light theme" : "Dark theme"; };
    button.hidden = false;
    label();
    button.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { window.localStorage.setItem("evalgate-theme", next); } catch (e) { /* ignore */ }
      label();
    });
  });
}());
