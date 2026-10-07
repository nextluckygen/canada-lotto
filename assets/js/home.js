/* Home page: "your numbers vs the latest draw" and the Lucky Numbers Generator (entertainment only). */
(function () {
  "use strict";
  var LH = window.LH;

  function myLine() {
    var box = document.getElementById("my-line");
    if (!box) return;
    var lines = LH.getLines();
    var out = [];
    [["max", "Lotto Max"], ["649", "Lotto 6/49"]].forEach(function (g) {
      var line = lines[g[0]];
      var raw = box.getAttribute("data-" + g[0]);
      if (!line || !line.length || !raw) return;
      var parts = raw.split("|");
      var nums = parts[1].split("-").map(Number);
      var bonus = Number(parts[2]) || 0;
      var hits = 0, bonusHit = false;
      var balls = line.map(function (n) {
        var hit = nums.indexOf(n) >= 0;
        if (hit) hits++;
        if (n === bonus) bonusHit = true;
        return LH.ballHTML(n, "sm", hit ? "hit" : (n === bonus ? "hit" : "miss"));
      }).join("");
      var d = new Date(parts[0] + "T12:00:00");
      var when = d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" });
      out.push('<div class="flex flex-wrap items-center gap-3 py-1"><span class="badge ' + (g[0] === "max" ? "badge-max" : "badge-649") + '">' + g[1] +
        '</span><span class="balls balls-sm">' + balls + '</span><span class="font-bold text-white">' + hits + " of " + line.length +
        (bonusHit ? " + bonus" : "") + '</span><span class="text-xs text-indigo-200">vs ' + when + ' draw · <a href="/check-my-numbers.html?game=' + g[0] +
        "&amp;n=" + line.join("-") + '">all-time check →</a></span></div>');
    });
    if (out.length) box.querySelector("[data-myline]").innerHTML = out.join("");
  }

  // ---------------- Lucky Numbers Generator (just for fun) ----------------
  function rnd(n) { // uniform integer 0..n-1
    var a = new Uint32Array(1), lim = Math.floor(4294967296 / n) * n;
    do { crypto.getRandomValues(a); } while (a[0] >= lim);
    return a[0] % n;
  }
  function pickFrom(pool, count, taken) {
    var p = pool.filter(function (x) { return taken.indexOf(x) < 0; });
    var out = [];
    while (out.length < count && p.length) { out.push(p.splice(rnd(p.length), 1)[0]); }
    return out;
  }
  function popular(line, N) {
    var s = line.slice().sort(function (a, b) { return a - b; });
    if (s[s.length - 1] <= 31) return true;
    for (var i = 2; i < s.length; i++) if (s[i] - s[i - 1] === 1 && s[i - 1] - s[i - 2] === 1) return true;
    var d = s[1] - s[0], ap = true;
    for (var j = 2; j < s.length; j++) if (s[j] - s[j - 1] !== d) ap = false;
    if (ap) return true;
    var digits = {};
    for (var k = 0; k < s.length; k++) { var t = s[k] % 10; digits[t] = (digits[t] || 0) + 1; if (digits[t] >= 4) return true; }
    if (s.every(function (x) { return x % 5 === 0; })) return true;
    return false;
  }
  function oddOk(line, mode, k) {
    var odd = line.filter(function (x) { return x % 2; }).length;
    if (mode === "bal") return odd === Math.floor(k / 2) || odd === Math.ceil(k / 2);
    if (mode === "odd") return odd >= k - 2;
    if (mode === "even") return odd <= 2;
    return true;
  }

  function generator() {
    var box = document.getElementById("generator");
    if (!box) return;
    var game = "max";
    var out = box.querySelector("[data-gen-out]");
    var go = box.querySelector("[data-gen-go]");
    var check = box.querySelector("[data-gen-check]");
    function cfg() {
      var p = box.getAttribute("data-" + game).split(",");
      return { N: +p[0], k: +p[1], hot: p[2].split("-").map(Number), cold: p[3].split("-").map(Number) };
    }
    function opt(name) { return box.querySelector('[data-opt="' + name + '"]'); }
    function blanks() {
      var k = cfg().k, h = "";
      for (var i = 0; i < k; i++) h += '<span class="ball ball-md ball-blank">?</span>';
      out.innerHTML = h;
      check.href = "/check-my-numbers.html";
    }
    box.querySelectorAll("[data-game]").forEach(function (b) {
      b.addEventListener("click", function () {
        game = b.getAttribute("data-game");
        box.querySelectorAll("[data-game]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        blanks();
      });
    });
    go.addEventListener("click", function () {
      var c = cfg(), N = c.N, k = c.k;
      var exc = LH.parseNums(opt("exc").value).filter(function (x) { return x >= 1 && x <= N; });
      var inc = LH.parseNums(opt("inc").value).filter(function (x, i, a) { return x >= 1 && x <= N && exc.indexOf(x) < 0 && a.indexOf(x) === i; }).slice(0, k);
      var pool = [];
      for (var n = 1; n <= N; n++) if (exc.indexOf(n) < 0) pool.push(n);
      if (pool.length < k) { out.innerHTML = '<span class="text-sm text-amber-200">Too many numbers excluded — leave at least ' + k + " available.</span>"; return; }
      var hc = opt("hc").value, oe = opt("oe").value, avoid = opt("pop").checked;
      var hot = c.hot.filter(function (x) { return pool.indexOf(x) >= 0; });
      var cold = c.cold.filter(function (x) { return pool.indexOf(x) >= 0; });
      var line = null, relaxed = false;
      for (var tries = 0; tries < 4000; tries++) {
        var l = inc.slice();
        var free = k - l.length;
        if (hc === "hot") l = l.concat(pickFrom(hot, Math.ceil(free * 0.6), l));
        else if (hc === "cold") l = l.concat(pickFrom(cold, Math.ceil(free * 0.6), l));
        else if (hc === "mix") { l = l.concat(pickFrom(hot, Math.floor(free / 2), l)); l = l.concat(pickFrom(cold, Math.ceil(free / 2), l)); }
        l = l.concat(pickFrom(pool, k - l.length, l));
        var strict = tries < 3000;
        if (strict && !oddOk(l, oe, k)) continue;
        if (strict && avoid && popular(l, N)) continue;
        line = l; relaxed = !strict; break;
      }
      if (!line) return;
      line.sort(function (a, b) { return a - b; });
      out.innerHTML = line.map(function (x, i) { return LH.ballHTML(x, "md", "", LH.reduce ? undefined : i); }).join("") +
        (relaxed ? '<span class="text-xs text-amber-200 ml-2">Options relaxed to fit.</span>' : "");
      check.href = "/check-my-numbers.html?game=" + game + "&n=" + line.join("-");
    });
  }

  function init() { myLine(); generator(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
