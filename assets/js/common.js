/* lottohelper.ca shared helpers: countdowns, jackpot count-up, ball markup, saved lines. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var RANGE = ["ball-r1", "ball-r2", "ball-r3", "ball-r4", "ball-r5", "ball-r6"];
  var KEY = "lh_lines";

  function rangeClass(n) { return RANGE[Math.min(Math.floor((n - 1) / 10), 5)]; }
  function ballHTML(n, size, extra, i) {
    var cls = "ball ball-" + (size || "sm") + " " + rangeClass(n) + (extra ? " " + extra : "");
    var style = "";
    if (typeof i === "number") { cls += " roll"; style = ' style="--i:' + i + '"'; }
    var inner = size === "lg" ? "<span>" + n + "</span>" : String(n);
    return '<span class="' + cls + '"' + style + ">" + inner + "</span>";
  }
  function bonusHTML(n, size, extra) {
    return '<span class="ball ball-' + (size || "sm") + " ball-bonus" + (extra ? " " + extra : "") + '" title="Bonus number">' + n + "</span>";
  }
  function parseNums(str) {
    return (String(str || "").match(/\d+/g) || []).map(Number);
  }
  function getLines() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; }
  }
  function setLine(game, nums) {
    try {
      var l = getLines();
      if (nums && nums.length) { l[game] = nums.slice().sort(function (a, b) { return a - b; }); } else { delete l[game]; }
      localStorage.setItem(KEY, JSON.stringify(l));
      return true;
    } catch (e) { return false; }
  }
  function money(n) {
    if (n >= 1e6 && n % 1e6 === 0) return "$" + (n / 1e6) + "M";
    return "$" + Math.round(n).toLocaleString("en-CA");
  }
  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function tickCountdowns() {
    var now = Date.now();
    document.querySelectorAll(".cd[data-target]").forEach(function (el) {
      var t = Date.parse(el.getAttribute("data-target"));
      if (isNaN(t)) return;
      var s = Math.floor((t - now) / 1000);
      if (s <= 0) {
        el.textContent = s > -3 * 3600 ? "Draw tonight · results soon" : "Results being checked";
        return;
      }
      var d = Math.floor(s / 86400); s -= d * 86400;
      var h = Math.floor(s / 3600); s -= h * 3600;
      var m = Math.floor(s / 60); s -= m * 60;
      el.textContent = "Ticket sales close in " + (d ? d + "d " : "") + pad(h) + "h " + pad(m) + "m " + pad(s) + "s";
    });
  }

  function countUp(el) {
    var target = Number(el.getAttribute("data-count"));
    if (!target || reduce) return;
    var start = null, from = Math.max(1e6, target * 0.5), dur = 1100;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      var v = from + (target - from) * e;
      el.textContent = p < 1 ? "$" + Math.round(v / 1e6) + "M" : money(target);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function init() {
    tickCountdowns();
    setInterval(tickCountdowns, 1000);
    var els = document.querySelectorAll("[data-count]");
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { countUp(en.target); io.unobserve(en.target); } });
      });
      els.forEach(function (el) { io.observe(el); });
    }
    // close the mobile menu after picking a link
    document.querySelectorAll(".menu-panel a").forEach(function (a) {
      a.addEventListener("click", function () { var d = a.closest("details"); if (d) d.open = false; });
    });
  }

  window.LH = { reduce: reduce, rangeClass: rangeClass, ballHTML: ballHTML, bonusHTML: bonusHTML, parseNums: parseNums,
    getLines: getLines, setLine: setLine, money: money };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
