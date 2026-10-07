/* Results pages: stats window picker and the lazy-loaded year browser. */
(function () {
  "use strict";
  var LH = window.LH;

  function picker() {
    var pickers = document.querySelectorAll("[data-winpick]");
    pickers.forEach(function (p) {
      p.addEventListener("click", function (ev) {
        var b = ev.target.closest("button[data-win]");
        if (!b) return;
        var key = b.getAttribute("data-win");
        document.querySelectorAll("[data-winpick] button[data-win]").forEach(function (x) {
          x.setAttribute("aria-pressed", x.getAttribute("data-win") === key ? "true" : "false");
        });
        document.querySelectorAll("[data-panel]").forEach(function (panel) {
          panel.hidden = panel.getAttribute("data-panel") !== key;
        });
      });
    });
  }

  var cache = null;
  function load(slug) {
    if (!cache) {
      cache = fetch("/data/" + slug + ".json").then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
    }
    return cache;
  }
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function table(data, year) {
    var isMax = data.game === "lotto_max";
    var rows = data.draws.filter(function (d) { return d[0].slice(0, 4) === String(year); }).reverse();
    var html = [], month = null;
    rows.forEach(function (d) {
      var y = +d[0].slice(0, 4), m = +d[0].slice(5, 7), day = +d[0].slice(8, 10);
      var dt = new Date(Date.UTC(y, m - 1, day));
      if (m !== month) { month = m; html.push('<tr class="mh"><th colspan="3">' + MONTHS[m - 1] + " " + y + "</th></tr>"); }
      var balls = d[1].map(function (n) { return LH.ballHTML(n, "sm"); }).join("") + (d[2] ? '<span class="plus" aria-hidden="true">+</span>' + LH.bonusHTML(d[2], "sm") : "");
      var last = "—";
      if (!isMax && d[3]) last = d[3] === "G" ? '<span class="gb-ico"><span class="ball ball-xs ball-gold">G</span> Gold</span>' : '<span class="gb-ico"><span class="ball ball-xs ball-white">W</span> White</span>';
      html.push('<tr class="r"><td class="c-date" data-label="Date">' + DAYS[dt.getUTCDay()] + ", " + MONTHS[m - 1].slice(0, 3) + " " + day + ", " + y +
        '</td><td class="c-nums" data-label="Numbers"><span class="balls balls-sm">' + balls + '</span></td><td data-label="' + (isMax ? "Format" : "Gold Ball") + '"' +
        (!isMax && last === "—" ? ' class="empty"' : "") + ">" + (isMax ? "Numbers 1–" + eraN(data, d[0]) : last) + "</td></tr>");
    });
    return '<p class="text-sm muted mb-2">' + rows.length + " draws in " + year + ', newest first.</p><table class="draw-table"><thead><tr><th>Date</th><th>Winning numbers + bonus</th><th>' +
      (isMax ? "Format" : "Gold Ball") + "</th></tr></thead><tbody>" + html.join("") + "</tbody></table>";
  }
  function eraN(data, iso) {
    for (var i = 0; i < data.eras.length; i++) {
      var e = data.eras[i];
      if (iso >= e.start && (!e.end || iso <= e.end)) return e.N;
    }
    return "";
  }

  function years() {
    var sec = document.querySelector("[data-archive]");
    if (!sec) return;
    var slug = sec.getAttribute("data-archive");
    var out = sec.querySelector("[data-year-out]");
    sec.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-year]");
      if (!b) return;
      sec.querySelectorAll("button[data-year]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      out.innerHTML = '<p class="text-sm muted">Loading…</p>';
      load(slug).then(function (data) {
        out.innerHTML = table(data, b.getAttribute("data-year"));
      }).catch(function () {
        cache = null;
        out.innerHTML = '<p class="notice">Could not load the draw data. Please try again.</p>';
      });
    });
  }

  function init() { picker(); years(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
