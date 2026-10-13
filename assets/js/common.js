/* lottohelper.ca shared helpers: countdowns, jackpot count-up, ball markup, saved lines. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var KEY = "lh_lines";

  // Hot / warm / cold status per game (last 50 draws, current format), precomputed at build time
  // into <body data-hwc-max="h12,w6,c3,..."> (index 0 = number 1). Same status as the server-rendered balls.
  var HWC = {}, HWC_CLASS = { h: "ball-hot", w: "ball-warm", c: "ball-cold" }, HWC_NAME = { h: "Hot", w: "Warm", c: "Cold" };
  function hwc(game) {
    if (!HWC[game]) {
      var raw = document.body ? document.body.getAttribute("data-hwc-" + game) : "";
      HWC[game] = (raw || "").split(",").filter(Boolean).map(function (t) { return { s: t.charAt(0), c: +t.slice(1) }; });
    }
    return HWC[game];
  }
  function status(n, game) { var l = hwc(game || "max"); return l[n - 1] || null; }
  function ballHTML(n, size, extra, i, game) {
    var st = game ? status(n, game) : null;
    var cls = "ball ball-" + (size || "sm") + " " + (st ? HWC_CLASS[st.s] : "ball-plain") + (extra ? " " + extra : "");
    var title = st ? ' title="' + n + " \u2014 " + HWC_NAME[st.s] + ": " + st.c + '\u00d7 in last 50 draws"' : "";
    var style = "";
    if (typeof i === "number") { cls += " roll"; style = ' style="--i:' + i + '"'; }
    var inner = size === "lg" ? "<span>" + n + "</span>" : String(n);
    return '<span class="' + cls + '"' + title + style + ">" + inner + "</span>";
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

  window.LH = { reduce: reduce, status: status, ballHTML: ballHTML, bonusHTML: bonusHTML, parseNums: parseNums,
    getLines: getLines, setLine: setLine, money: money };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
