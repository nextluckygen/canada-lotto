/* Check my numbers: compares one line with every archived draw, entirely in the browser. */
(function () {
  "use strict";
  var LH = window.LH;
  var GAMES = {
    max: { k: 7, N: 52, slug: "lotto-max", name: "Lotto Max",
      tiers: [["7 of 7", 7, 0], ["6 of 7 + bonus", 6, 1], ["6 of 7", 6, 0], ["5 of 7 + bonus", 5, 1], ["5 of 7", 5, 0], ["4 of 7 + bonus", 4, 1], ["4 of 7", 4, 0], ["3 of 7 + bonus", 3, 1], ["3 of 7", 3, 0]] },
    "649": { k: 6, N: 49, slug: "lotto-649", name: "Lotto 6/49",
      tiers: [["6 of 6", 6, 0], ["5 of 6 + bonus", 5, 1], ["5 of 6", 5, 0], ["4 of 6", 4, -1], ["3 of 6", 3, -1], ["2 of 6 + bonus", 2, 1], ["2 of 6", 2, -2]] }
  };
  var cache = {};
  function load(g) {
    if (!cache[g]) {
      cache[g] = fetch("/data/" + GAMES[g].slug + ".json").then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
      cache[g].catch(function () { delete cache[g]; });
    }
    return cache[g];
  }
  // tier for a draw: returns tier index or -1. b = bonus on line
  function tierOf(g, m, b) {
    var t = GAMES[g].tiers;
    for (var i = 0; i < t.length; i++) {
      var need = t[i][2];
      if (t[i][1] !== m) continue;
      if (need === 1 && b) return i;
      if (need === 0 && !b) return i;
      if (need === 0 && b && g === "max" && m === 7) return i;
      if (need === -1) return i;
      if (need === -2 && !b) return i;
    }
    return -1;
  }
  function comb(n, k) { if (k < 0 || k > n) return 0; var r = 1; for (var i = 1; i <= k; i++) r = r * (n - k + i) / i; return r; }
  function pAtLeast(N, k, m) { var s = 0; for (var j = m; j <= k; j++) s += comb(k, j) * comb(N - k, k - j); return s / comb(N, k); }
  function fmtDate(iso) {
    var d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString("en-CA", { weekday: "short", year: "numeric", month: "short", day: "numeric" });
  }
  function eraN(data, iso) {
    for (var i = 0; i < data.eras.length; i++) { var e = data.eras[i]; if (iso >= e.start && (!e.end || iso <= e.end)) return e.N; }
    return data.eras[0].N;
  }

  function init() {
    var box = document.getElementById("checker");
    if (!box) return;
    var res = document.getElementById("results");
    var game = "max", line = [];
    var picks = box.querySelectorAll(".pick");
    var typed = box.querySelector("[data-typed]");
    var scope = box.querySelector("[data-scope]");
    var minSel = box.querySelector("[data-min]");
    var run = box.querySelector("[data-run]");
    var save = box.querySelector("[data-save]");
    var msg = box.querySelector("[data-msg]");
    var label = box.querySelector("[data-count-label]");

    function sync(fromTyped) {
      var g = GAMES[game];
      picks.forEach(function (p) {
        var n = +p.getAttribute("data-n");
        p.hidden = n > g.N;
        var on = line.indexOf(n) >= 0;
        p.classList.toggle("is-on", on);
        p.setAttribute("aria-pressed", on ? "true" : "false");
      });
      if (!fromTyped) typed.value = line.slice().sort(function (a, b) { return a - b; }).join(" ");
      var left = g.k - line.length;
      label.textContent = left > 0 ? "Pick " + left + " more number" + (left === 1 ? "" : "s") + " from 1 to " + g.N + "." : "Line complete — press Check.";
      run.disabled = line.length !== g.k;
      var saved = LH.getLines()[game];
      save.checked = !!(saved && saved.join("-") === line.slice().sort(function (a, b) { return a - b; }).join("-"));
    }
    function setGame(g) {
      game = g;
      box.querySelectorAll("[data-game]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-game") === g ? "true" : "false"); });
      line = line.filter(function (n) { return n <= GAMES[g].N; }).slice(0, GAMES[g].k);
      if (g === "649") {
        scope.innerHTML = '<option value="all">All draws since 1982</option>';
        minSel.querySelector('option[value="3"]').textContent = "3 or more";
      } else {
        scope.innerHTML = '<option value="all">All draws since 2009</option><option value="cur">Current 1–52 format only</option>';
      }
      typed.placeholder = g === "649" ? "e.g. 3 11 19 24 33 40" : "e.g. 3 11 19 24 33 40 47";
      sync();
    }
    box.querySelectorAll("[data-game]").forEach(function (b) { b.addEventListener("click", function () { setGame(b.getAttribute("data-game")); }); });
    picks.forEach(function (p) {
      p.addEventListener("click", function () {
        var n = +p.getAttribute("data-n"), i = line.indexOf(n);
        if (i >= 0) line.splice(i, 1);
        else if (line.length < GAMES[game].k) line.push(n);
        else { msg.textContent = "That's " + GAMES[game].k + " numbers already — tap one to remove it first."; return; }
        msg.textContent = "";
        sync();
      });
    });
    typed.addEventListener("input", function () {
      var g = GAMES[game], seen = [];
      LH.parseNums(typed.value).forEach(function (n) { if (n >= 1 && n <= g.N && seen.indexOf(n) < 0 && seen.length < g.k) seen.push(n); });
      line = seen;
      sync(true);
    });
    box.querySelector("[data-clear]").addEventListener("click", function () {
      line = []; LH.setLine(game, null); res.hidden = true; msg.textContent = ""; sync();
    });
    save.addEventListener("change", function () {
      if (save.checked) {
        if (line.length !== GAMES[game].k) { save.checked = false; msg.textContent = "Pick a full line first, then tick Save."; return; }
        msg.textContent = LH.setLine(game, line) ? "Saved in this browser. The home page will show it against the latest draw." : "Your browser blocked local storage, so the line could not be saved.";
      } else {
        LH.setLine(game, null); msg.textContent = "Removed from this browser.";
      }
    });

    run.addEventListener("click", function () {
      var g = GAMES[game], mine = line.slice().sort(function (a, b) { return a - b; });
      if (mine.length !== g.k) return;
      if (save.checked) LH.setLine(game, mine);
      run.disabled = true; msg.textContent = "Loading draw history…";
      load(game).then(function (data) {
        run.disabled = false; msg.textContent = "";
        var draws = data.draws;
        if (game === "max" && scope.value === "cur") draws = draws.filter(function (d) { return d[0] >= data.eras[0].start; });
        var min = +minSel.value;
        var counts = g.tiers.map(function () { return 0; });
        var hits = [], best = null, expected3 = 0;
        draws.forEach(function (d) {
          var m = 0;
          for (var i = 0; i < d[1].length; i++) if (mine.indexOf(d[1][i]) >= 0) m++;
          var b = d[2] && mine.indexOf(d[2]) >= 0;
          var t = tierOf(game, m, b);
          if (t >= 0) counts[t]++;
          expected3 += pAtLeast(eraN(data, d[0]), g.k, 3);
          var score = m * 2 + (b ? 1 : 0);
          if (!best || score > best.score) best = { score: score, m: m, b: b, list: [d] };
          else if (score === best.score) best.list.push(d);
          if (m >= min) hits.push({ d: d, m: m, b: b, t: t });
        });
        render(data, mine, draws, counts, hits, best, expected3, min);
      }).catch(function () { run.disabled = false; msg.textContent = "Could not load the draw history. Check your connection and try again."; });
    });

    function lineBalls(nums, d) {
      return '<span class="balls balls-xs">' + nums.map(function (n) {
        var hit = d[1].indexOf(n) >= 0, bon = n === d[2];
        return LH.ballHTML(n, "xs", hit ? "hit" : (bon ? "hit" : "miss"));
      }).join("") + "</span>";
    }
    function render(data, mine, draws, counts, hits, best, expected3, min) {
      var g = GAMES[game];
      var first = draws.length ? fmtDate(draws[0][0]) : "—";
      var n3 = 0;
      draws.forEach(function () {});
      g.tiers.forEach(function (t, i) { if (t[1] >= 3) n3 += counts[i]; });
      res.hidden = false;
      res.querySelector("[data-summary]").innerHTML =
        '<p class="kicker">' + g.name + ' · your line</p><div class="mt-2"><span class="balls balls-md">' + mine.map(function (n) { return LH.ballHTML(n, "md"); }).join("") + "</span></div>" +
        '<p class="mt-3 text-lg">Checked against <strong>' + draws.length.toLocaleString("en-CA") + "</strong> draws since " + first + ". It matched 3 or more numbers in <strong>" + n3 + "</strong> draws." +
        ' <span class="muted text-base">Pure chance gives about ' + expected3.toFixed(1) + " for any line.</span></p>";
      var rows = g.tiers.map(function (t, i) {
        return '<tr><td class="font-bold">' + t[0] + '</td><td class="tnum">' + (counts[i] ? '<span class="tier-hit">' + counts[i] + "×</span>" : "0") + "</td></tr>";
      }).join("");
      res.querySelector("[data-tiers]").innerHTML = '<h2 class="section-title">Times in each prize tier</h2><div class="table-wrap"><table><thead><tr><th>Tier</th><th>Draws</th></tr></thead><tbody>' + rows +
        '</tbody></table></div><p class="text-xs muted">Tier names from the current prize table. Amounts varied by draw and older draws had different prize structures, so no dollar figures are shown.</p>';
      var bestTxt = best ? best.m + " number" + (best.m === 1 ? "" : "s") + (best.b ? " + bonus" : "") : "—";
      var bl = best ? best.list.slice(-5).reverse().map(function (d) { return '<div class="res-row"><span class="dt">' + fmtDate(d[0]) + "</span>" + lineBalls(mine, d) + "</div>"; }).join("") : "";
      res.querySelector("[data-best]").innerHTML = '<h2 class="section-title">🏆 Best result ever</h2><p class="stat-big mt-2">' + bestTxt + '</p><p class="text-sm muted">' +
        (best ? best.list.length + " time" + (best.list.length === 1 ? "" : "s") + (best.list.length > 5 ? " (latest 5 shown)" : "") : "") + "</p><div class=\"mt-2\">" + bl + "</div>";
      hits.reverse();
      var shown = hits.slice(0, 200);
      var list = shown.map(function (h) {
        var t = h.t >= 0 ? '<span class="tier-hit">' + g.tiers[h.t][0] + "</span>" : '<span class="text-sm font-bold">' + h.m + " matched</span>";
        return '<div class="res-row"><span class="dt">' + fmtDate(h.d[0]) + "</span>" + lineBalls(mine, h.d) + t + "</div>";
      }).join("");
      res.querySelector("[data-list]").innerHTML = (hits.length ? "" : '<p class="muted">No draws matched ' + min + " or more of your numbers in this range.</p>") +
        (hits.length ? '<p class="text-sm muted mb-2">' + hits.length + " draw" + (hits.length === 1 ? "" : "s") + " with " + min + "+ matches, newest first" + (hits.length > 200 ? " (first 200 shown)" : "") + ". Gold rings = numbers that matched.</p>" : "") +
        list;
      res.scrollIntoView({ behavior: LH.reduce ? "auto" : "smooth", block: "start" });
    }

    // prefill: ?game=max|649&n=1-2-3 (canonical stays the base page), else a saved line
    var q = new URLSearchParams(location.search);
    var qg = q.get("game");
    var startGame = qg === "649" ? "649" : "max";
    var saved = LH.getLines();
    if (!qg && !saved.max && saved["649"]) startGame = "649";
    setGame(startGame);
    var pre = q.get("n") ? LH.parseNums(q.get("n")) : (saved[startGame] || []);
    var gg = GAMES[startGame];
    line = pre.filter(function (n, i, a) { return n >= 1 && n <= gg.N && a.indexOf(n) === i; }).slice(0, gg.k);
    sync();
    if (line.length === gg.k && q.get("n")) run.click();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
